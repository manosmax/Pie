import argparse
import json
import logging
import threading
import time
import uuid
import os
from datetime import datetime, timezone
from queue import Empty, Full, Queue

import paho.mqtt.client as mqtt
from pirlib import PirInterpreter, PirSampler

# --- Configuration & Persistence ---
STATE_FILE = "/app/data/sensor_state.json"
BIN_CAPACITY = 50
state_lock = threading.Lock()

logger = logging.getLogger(__name__)

JSONLD_CONTEXT = {
    "@vocab":   "https://schema.org/",
    "sosa":     "http://www.w3.org/ns/sosa/",
    "ssn":      "http://www.w3.org/ns/ssn/",
    "xsd":      "http://www.w3.org/2001/XMLSchema#",
    "pipeline": "https://github.com/manosmax/Pie/blob/main/docs/ontology.md#",
    "event_time":   {"@id": "sosa:resultTime",    "@type": "xsd:dateTime"},
    "fill_level":   {"@id": "pipeline:fillLevel", "@type": "xsd:integer"},
    "last_emptied": {"@id": "pipeline:lastEmptiedAt", "@type": "xsd:dateTime"}
}

def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")

def save_state(state: dict) -> None:
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)

def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load state: {e}")
    return {"item_count": 0, "fill_level": 0, "last_emptied": "Never"}

def send_discovery(client: mqtt.Client, bin_id: str, sensor_id: str, topics: dict) -> None:
    device_info = {
        "identifiers": [bin_id],
        "name": f"Smart Waste Bin {bin_id}",
        "model": "IoT-Bin-v2",
        "manufacturer": "Team 08"
    }

    configs = [
        ("binary_sensor", "motion", {
            "device_class": "motion",
            "state_topic": topics["pir"],
            "payload_on": "detected",
            "payload_off": "clear",
            "off_delay": 6,
        }),
        ("sensor", "fill", {
            "unit_of_measurement": "%",
            "state_topic": topics["fill"],
            "state_class": "measurement",
            "icon": "mdi:delete-variant",
        }),
        ("sensor", "emptied", {
            "device_class": "timestamp",
            "state_topic": topics["emptied"],
            "icon": "mdi:clock-check-outline",
        }),
    ]

    for component, suffix, config in configs:
        config.update({
            "name": f"Waste Bin {bin_id} {suffix.capitalize()}",
            "unique_id": f"{bin_id}_{suffix}",
            "device": device_info,
        })
        client.publish(
            f"homeassistant/{component}/{bin_id}_{suffix}/config",
            json.dumps(config),
            qos=1,
            retain=True,
        )

# ---------------------------------------------------------------------------
# Producer loop — reads PIR sensor, enqueues events
# ---------------------------------------------------------------------------

def producer_loop(
    event_q: Queue,
    sampler: PirSampler,
    interp: PirInterpreter,
    args: argparse.Namespace,
    state: dict,
    stop_flag: dict,
) -> None:
    run_id = str(uuid.uuid4())
    seq = 0
    while not stop_flag["stop"]:
        t = time.monotonic()
        raw = sampler.read()
        for _ in interp.update(raw, t):
            seq += 1
            with state_lock:
                state["item_count"] += 1
                state["fill_level"] = min(
                    int((state["item_count"] / BIN_CAPACITY) * 100), 100
                )
                save_state(state)

                record = {
                    "@context": JSONLD_CONTEXT,
                    "@id": f"urn:event:{run_id}:{seq}",
                    "@type": "sosa:Observation",
                    "event_time": utc_now_iso(),
                    "device_id": args.device_id,
                    "fill_level": state["fill_level"],
                    "item_count": state["item_count"],
                    "last_emptied": state["last_emptied"],
                }
            try:
                event_q.put_nowait(record)
            except Full:
                logger.warning("Queue full — dropping event")
        time.sleep(args.sample_interval)

# ---------------------------------------------------------------------------
# Publisher loop — sends events to MQTT, handles "emptied" commands
# ---------------------------------------------------------------------------

def publisher_loop(
    event_q: Queue,
    args: argparse.Namespace,
    state: dict,
    stop_flag: dict,
) -> None:
    topics = {
        "pir":     f"smartbin/{args.bin_id}/{args.sensor_id}/motion",
        "fill":    f"smartbin/{args.bin_id}/fill-level/state",
        "emptied": f"smartbin/{args.bin_id}/last-emptied/state",
        "cmd":     f"smartbin/{args.bin_id}/command",
    }

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)

    def on_connect(c: mqtt.Client, userdata, flags, reason_code: int, properties) -> None:
        if reason_code == 0:
            print(f"[MQTT publisher] Connected (bin={args.bin_id})")
            # Subscribe to the command topic so we receive empty-bin requests.
            c.subscribe(topics["cmd"], qos=1)
            send_discovery(c, args.bin_id, args.sensor_id, topics)
        else:
            logger.error(f"[MQTT publisher] Connection failed rc={reason_code}")

    def on_message(client: mqtt.Client, userdata, msg: mqtt.MQTTMessage) -> None:
        """Handle commands published by the API (e.g. action=emptied)."""
        try:
            payload = json.loads(msg.payload.decode())
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            logger.error(f"on_message: bad payload: {exc}")
            return

        action = payload.get("action")

        if action == "emptied":
            emptied_at = payload.get("emptied_at") or utc_now_iso()
            emptied_by = payload.get("emptied_by", "unknown")

            with state_lock:
                # FIX: only reset if there is something to reset, avoiding
                # spurious MQTT retained-message resets on reconnect.
                if state["fill_level"] == 0 and state["item_count"] == 0:
                    print(f"[CMD] Bin {args.bin_id} already empty — ignoring duplicate command.")
                    return

                state["item_count"] = 0
                state["fill_level"] = 0
                state["last_emptied"] = emptied_at
                save_state(state)

            # Immediately publish the updated state so dashboards reflect 0 %.
            client.publish(topics["fill"],    "0",        retain=True)
            client.publish(topics["emptied"], emptied_at, retain=True)

            print(
                f"[CMD] Bin {args.bin_id} emptied by '{emptied_by}' at {emptied_at}. "
                "Fill level reset to 0."
            )
        else:
            logger.warning(f"on_message: unknown action '{action}'")

    client.on_connect = on_connect
    client.on_message = on_message

    # Reconnect automatically if the broker restarts.
    client.reconnect_delay_set(min_delay=1, max_delay=30)
    client.connect(args.host, args.port, keepalive=60)
    client.loop_start()

    # Main publish loop — drains the event queue and forwards to MQTT.
    while not stop_flag["stop"] or not event_q.empty():
        try:
            record = event_q.get(timeout=0.5)
        except Empty:
            continue

        client.publish(args.topic, json.dumps(record))
        client.publish(topics["pir"],  "detected")
        client.publish(topics["fill"], str(record["fill_level"]))
        event_q.task_done()

    client.loop_stop()
    client.disconnect()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Smart Wastebin PIR producer")
    parser.add_argument("--bin-id",          default="bin-01")
    parser.add_argument("--device-id",       default="urn:dev:team08:pir-01")
    parser.add_argument("--sensor-id",       default="pir-01")
    parser.add_argument("--host",            default="mosquitto")
    parser.add_argument("--port",            type=int,   default=1883)
    parser.add_argument("--pin",             type=int,   default=17)
    parser.add_argument("--sample-interval", type=float, default=0.1)
    parser.add_argument("--cooldown",        type=float, default=5.0)
    parser.add_argument("--min-high",        type=float, default=0.2)
    parser.add_argument("--topic",           default="smartbin/events")
    parser.add_argument("--verbose",         action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    state     = load_state()
    event_q   = Queue(maxsize=100)
    stop_flag = {"stop": False}

    sampler = PirSampler(pin=args.pin)
    interp  = PirInterpreter(cooldown_s=args.cooldown, min_high_s=args.min_high)

    t_producer  = threading.Thread(
        target=producer_loop,
        args=(event_q, sampler, interp, args, state, stop_flag),
        daemon=True,
    )
    t_publisher = threading.Thread(
        target=publisher_loop,
        args=(event_q, args, state, stop_flag),
        daemon=True,
    )

    t_producer.start()
    t_publisher.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[MAIN] Shutting down…")
        stop_flag["stop"] = True
        sampler.cleanup()
        t_producer.join(timeout=5)
        t_publisher.join(timeout=5)


if __name__ == "__main__":
    main()