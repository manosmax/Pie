import argparse
import json
import logging
import os
import threading
import time
import uuid
from datetime import datetime, timezone
from queue import Empty, Full, Queue

import paho.mqtt.client as mqtt
from pirlib import PirInterpreter, PirSampler

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# State persistence helpers
# ---------------------------------------------------------------------------

STATE_FILE = os.path.join(os.path.dirname(__file__), "data", "edge_state.json")

def load_persisted_state() -> dict:
    """Load fill-level and last-emptied from disk so restarts don't reset state."""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
            print(f"[STATE] Loaded persisted state: {saved}")
            return saved
        except Exception as e:
            print(f"[STATE] Could not load state file: {e}")
    return {"item_count": 0, "fill_level": 0, "last_emptied": "Unknown"}

def save_state(state: dict, lock: threading.Lock) -> None:
    """Flush the mutable parts of state to disk atomically."""
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with lock:
        snapshot = {
            "item_count":   state["item_count"],
            "fill_level":   state["fill_level"],
            "last_emptied": state["last_emptied"],
        }
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(snapshot, f)
    os.replace(tmp, STATE_FILE)   # atomic on POSIX

# ---------------------------------------------------------------------------
# Discovery & utilities
# ---------------------------------------------------------------------------

def send_discovery(client, bin_id, sensor_id, pir_topic, fill_topic, emptied_topic):
    """Sends MQTT Discovery JSON to Home Assistant."""
    device_info = {
        "identifiers": [bin_id],
        "name": f"Smart Waste Bin {bin_id}",
        "model": "IoT-Bin-v2",
        "manufacturer": "Team 08"
    }

    pir_config = {
        "name": f"Waste Bin {bin_id} Motion",
        "state_topic": pir_topic,
        "payload_on": "detected",
        "payload_off": "clear",
        "device_class": "motion",
        "unique_id": f"{bin_id}_{sensor_id}_motion",
        "off_delay": 6,
        "device": device_info
    }

    fill_config = {
        "name": f"Waste Bin {bin_id} Fill Level",
        "state_topic": fill_topic,
        "unit_of_measurement": "%",
        "icon": "mdi:delete-variant",
        "state_class": "measurement",
        "unique_id": f"{bin_id}_fill_level",
        "device": device_info
    }

    emptied_config = {
        "name": f"Waste Bin {bin_id} Last Emptied",
        "state_topic": emptied_topic,
        "device_class": "timestamp",
        "unique_id": f"{bin_id}_last_emptied",
        "icon": "mdi:clock-check-outline",
        "device": device_info
    }

    client.publish(f"homeassistant/binary_sensor/{bin_id}_{sensor_id}/config", json.dumps(pir_config), qos=1, retain=True)
    client.publish(f"homeassistant/sensor/{bin_id}_fill/config",              json.dumps(fill_config), qos=1, retain=True)
    client.publish(f"homeassistant/sensor/{bin_id}_emptied/config",           json.dumps(emptied_config), qos=1, retain=True)
    print("[HA] Discovery sent for Motion, Fill Level, and Emptied Timestamp.")

def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="PIR producer — reads sensor, publishes to MQTT")
    p.add_argument("--device-id",       default="urn:dev:team08:pir-01")
    p.add_argument("--bin-id",          default="bin-01")
    p.add_argument("--sensor-id",       default="pir-01")
    p.add_argument("--pin",              type=int,   default=17)
    p.add_argument("--sample-interval", type=float, default=0.1)
    p.add_argument("--cooldown",         type=float, default=5.0)
    p.add_argument("--min-high",         type=float, default=0.2)
    p.add_argument("--queue-size",       type=int,   default=100)
    p.add_argument("--duration",         type=float, default=600.0)
    p.add_argument("--host",             default="localhost")
    p.add_argument("--port",             type=int,   default=1883)
    p.add_argument("--qos",              type=int,   default=1)
    p.add_argument("--topic",            default="smartbin/bin-01/pir-01/events")
    p.add_argument("--verbose",          action="store_true")
    return p.parse_args()

# ---------------------------------------------------------------------------
# Shared Constants
# ---------------------------------------------------------------------------

BIN_CAPACITY = 50
JSONLD_CONTEXT = {
    "@vocab":   "https://schema.org/",
    "sosa":     "http://www.w3.org/ns/sosa/",
    "ssn":      "http://www.w3.org/ns/ssn/",
    "xsd":      "http://www.w3.org/2001/XMLSchema#",
    "pipeline": "https://github.com/manosmax/Pie/blob/main/docs/ontology.md#",
    "event_time":   {"@id": "sosa:resultTime",        "@type": "xsd:dateTime"},
    "device_id":    {"@id": "sosa:madeBySensor",      "@type": "@id"},
    "mounted_on":   {"@id": "sosa:isHostedBy",        "@type": "@id"},
    "fill_level":   {"@id": "pipeline:fillLevel",     "@type": "xsd:integer"},
    "last_emptied": {"@id": "pipeline:lastEmptiedAt", "@type": "xsd:dateTime"}
}

# ---------------------------------------------------------------------------
# Core Loops
# ---------------------------------------------------------------------------

def producer_loop(
    event_q: Queue,
    sampler: PirSampler,
    interp: PirInterpreter,
    args: argparse.Namespace,
    state: dict,
    state_lock: threading.Lock,   # FIX: explicit lock passed in
    stop_flag: dict,
) -> None:
    run_id = str(uuid.uuid4())
    seq = 0

    while not stop_flag["stop"]:
        t = time.monotonic()
        raw = sampler.read()

        for _ in interp.update(raw, t):
            seq += 1

            # FIX 1: Acquire the lock whenever reading or writing shared state
            # so that the on_message callback (running in the MQTT network thread)
            # can never corrupt these values mid-update.
            with state_lock:
                state["item_count"] += 1
                state["fill_level"] = min(int((state["item_count"] / BIN_CAPACITY) * 100), 100)
                snapshot_count    = state["item_count"]
                snapshot_fill     = state["fill_level"]
                snapshot_emptied  = state["last_emptied"]

            record = {
                "@context": JSONLD_CONTEXT,
                "@id": f"urn:event:{run_id}:{seq}",
                "@type": "sosa:Observation",
                "event_time":   utc_now_iso(),
                "device_id":    args.device_id,
                "event_type":   "urn:prop:team08:motion",
                "motion_state": "detected",
                "seq":          seq,
                "run_id":       run_id,
                "mounted_on":   f"urn:wastebin:{args.bin_id}",
                "item_count":   snapshot_count,
                "fill_level":   snapshot_fill,
                "last_emptied": snapshot_emptied,
            }
            try:
                event_q.put_nowait(record)
                with state_lock:
                    state["produced"] += 1
            except Full:
                with state_lock:
                    state["dropped"] += 1

        time.sleep(args.sample_interval)


def publisher_loop(
    event_q: Queue,
    args: argparse.Namespace,
    state: dict,
    state_lock: threading.Lock,   # FIX: lock passed in
    stop_flag: dict,
) -> None:
    topic        = args.topic
    qos          = args.qos
    ha_pir_topic     = f"smartbin/{args.bin_id}/{args.sensor_id}/motion"
    ha_fill_topic    = f"smartbin/{args.bin_id}/fill-level/state"
    ha_emptied_topic = f"smartbin/{args.bin_id}/last-emptied/state"
    cmd_topic        = f"smartbin/{args.bin_id}/command"

    client = mqtt.Client()

    def on_connect(client, userdata, flags, rc):
        if rc == 0:
            # FIX 2: Subscribe with retain=False by default, but the broker will
            # re-deliver the last retained "emptied" command on reconnect if we
            # use a persistent session.  Re-subscribing here ensures we never
            # miss a command issued while the edge device was offline.
            client.subscribe(cmd_topic, qos=qos)
            send_discovery(client, args.bin_id, args.sensor_id,
                           ha_pir_topic, ha_fill_topic, ha_emptied_topic)

            # Re-publish current fill level and last-emptied so HA is in sync
            # after a reconnect.
            with state_lock:
                current_fill    = state["fill_level"]
                current_emptied = state["last_emptied"]
            client.publish(ha_fill_topic,    str(current_fill),    qos=qos, retain=True)
            if current_emptied != "Unknown":
                client.publish(ha_emptied_topic, current_emptied, qos=qos, retain=True)
        else:
            print(f"[PUB] Connection failed: {rc}")

    def on_message(client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode())
            if payload.get("action") != "emptied":
                return

            emptied_time = payload.get("emptied_at") or utc_now_iso()
            print(f"[CMD] Bin emptied at {emptied_time}. Resetting levels.")

            # FIX 3: Hold the lock while updating shared state so the producer
            # thread cannot read a half-updated state dict.
            with state_lock:
                state["item_count"]  = 0
                state["fill_level"]  = 0
                state["last_emptied"] = emptied_time

            # FIX 4: Persist the new state to disk immediately so a power-cycle
            # or process restart doesn't reset the bin back to "unknown".
            save_state(state, state_lock)

            # Notify Home Assistant immediately
            client.publish(ha_fill_topic,    "0",          qos=qos, retain=True)
            client.publish(ha_emptied_topic, emptied_time, qos=qos, retain=True)

        except Exception as e:
            logger.error(f"Error processing command: {e}")

    client.on_connect = on_connect
    client.on_message = on_message
    client.will_set(f"{topic}/status", "offline", qos=qos, retain=True)

    client.connect(args.host, args.port, keepalive=60)
    client.loop_start()
    client.publish(f"{topic}/status", "online", qos=qos, retain=True)

    while not stop_flag["stop"] or not event_q.empty():
        try:
            record = event_q.get(timeout=0.5)
        except Empty:
            continue

        client.publish(topic, json.dumps(record, default=str), qos=qos)
        client.publish(ha_pir_topic, "detected", qos=qos)

        with state_lock:
            current_fill = state["fill_level"]
        client.publish(ha_fill_topic, str(current_fill), qos=qos)

        with state_lock:
            state["published"] += 1
        event_q.task_done()

    client.loop_stop()
    client.disconnect()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    args = parse_args()

    event_q: Queue = Queue(maxsize=args.queue_size)

    # FIX 5: Load persisted state on startup so item_count / fill_level /
    # last_emptied survive a process restart.
    persisted = load_persisted_state()
    state = {
        "produced":    0,
        "published":   0,
        "dropped":     0,
        "item_count":  persisted["item_count"],
        "fill_level":  persisted["fill_level"],
        "last_emptied": persisted["last_emptied"],
    }

    # FIX 6: Single shared lock protecting all reads/writes of state.
    state_lock = threading.Lock()
    stop_flag  = {"stop": False}

    sampler = PirSampler(pin=args.pin)
    interp  = PirInterpreter(cooldown_s=args.cooldown, min_high_s=args.min_high)

    producer_t = threading.Thread(
        target=producer_loop,
        args=(event_q, sampler, interp, args, state, state_lock, stop_flag),
        daemon=True,
    )
    publisher_t = threading.Thread(
        target=publisher_loop,
        args=(event_q, args, state, state_lock, stop_flag),
        daemon=True,
    )

    producer_t.start()
    publisher_t.start()

    try:
        while not stop_flag["stop"]:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        stop_flag["stop"] = True
        producer_t.join()
        publisher_t.join()
        sampler.cleanup()
        # Persist final state on clean shutdown
        save_state(state, state_lock)


if __name__ == "__main__":
    main()