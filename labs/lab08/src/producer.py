import argparse
import json
import logging
import threading
import time
import uuid
from datetime import datetime, timezone
from queue import Empty, Full, Queue

import paho.mqtt.client as mqtt
from pirlib import PirInterpreter, PirSampler

logger = logging.getLogger(__name__)

# --- Helper Functions ---

def send_discovery(client, bin_id, sensor_id, pir_topic, fill_topic, emptied_topic):
    """Sends the MQTT Discovery JSON to Home Assistant including the new Timestamp sensor."""
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

    # New: Timestamp sensor for when the bin was last emptied
    emptied_config = {
        "name": f"Waste Bin {bin_id} Last Emptied",
        "state_topic": emptied_topic,
        "device_class": "timestamp",
        "unique_id": f"{bin_id}_last_emptied",
        "icon": "mdi:clock-check-outline",
        "device": device_info
    }

    client.publish(f"homeassistant/binary_sensor/{bin_id}_{sensor_id}/config", json.dumps(pir_config), qos=1, retain=True)
    client.publish(f"homeassistant/sensor/{bin_id}_fill/config", json.dumps(fill_config), qos=1, retain=True)
    client.publish(f"homeassistant/sensor/{bin_id}_emptied/config", json.dumps(emptied_config), qos=1, retain=True)
    
    print("[HA] Discovery sent for Motion, Fill Level, and Emptied Timestamp.")

def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="PIR producer — reads sensor, publishes to MQTT")
    p.add_argument("--device-id",      default="urn:dev:team08:pir-01")
    p.add_argument("--bin-id",         default="bin-01")
    p.add_argument("--sensor-id",      default="pir-01")
    p.add_argument("--pin",             type=int,   default=17)
    p.add_argument("--sample-interval", type=float, default=0.1)
    p.add_argument("--cooldown",        type=float, default=5.0)
    p.add_argument("--min-high",        type=float, default=0.2)
    p.add_argument("--queue-size",      type=int,   default=100)
    p.add_argument("--duration",        type=float, default=600.0)
    p.add_argument("--host",            default="localhost")
    p.add_argument("--port",            type=int,   default=1883)
    p.add_argument("--qos",             type=int,   default=1)
    p.add_argument("--topic",           default="smartbin/bin-01/pir-01/events")
    p.add_argument("--verbose",         action="store_true")
    return p.parse_args()

# --- Shared Constants ---
BIN_CAPACITY = 50
JSONLD_CONTEXT = {
    "@vocab":   "https://schema.org/",
    "sosa":     "http://www.w3.org/ns/sosa/",
    "ssn":      "http://www.w3.org/ns/ssn/",
    "xsd":      "http://www.w3.org/2001/XMLSchema#",
    "pipeline": "https://github.com/manosmax/Pie/blob/main/docs/ontology.md#",
    "event_time":          {"@id": "sosa:resultTime",         "@type": "xsd:dateTime"},
    "device_id":           {"@id": "sosa:madeBySensor",       "@type": "@id"},
    "mounted_on":          {"@id": "sosa:isHostedBy",         "@type": "@id"},
    "fill_level":          {"@id": "pipeline:fillLevel",      "@type": "xsd:integer"},
    "last_emptied":        {"@id": "pipeline:lastEmptiedAt",  "@type": "xsd:dateTime"}
}

# --- Core Loops ---

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
            state["item_count"] += 1
            state["fill_level"] = min(int((state["item_count"] / BIN_CAPACITY) * 100), 100)

            record = {
                "@context": JSONLD_CONTEXT,
                "@id": f"urn:event:{run_id}:{seq}",
                "@type": "sosa:Observation",
                "event_time": utc_now_iso(),
                "device_id": args.device_id,
                "event_type": "urn:prop:team08:motion",
                "motion_state": "detected",
                "seq": seq,
                "run_id": run_id,
                "mounted_on": f"urn:wastebin:{args.bin_id}",
                "item_count": state["item_count"],
                "fill_level": state["fill_level"],
                "last_emptied": state["last_emptied"] # Include the last known emptied time
            }
            try:
                event_q.put_nowait(record)
                state["produced"] += 1
            except Full:
                state["dropped"] += 1

        time.sleep(args.sample_interval)

def publisher_loop(
    event_q: Queue,
    args: argparse.Namespace,
    state: dict,
    stop_flag: dict,
) -> None:
    topic, qos = args.topic, args.qos
    ha_pir_topic     = f"smartbin/{args.bin_id}/{args.sensor_id}/motion"
    ha_fill_topic    = f"smartbin/{args.bin_id}/fill-level/state"
    ha_emptied_topic = f"smartbin/{args.bin_id}/last-emptied/state"
    cmd_topic        = f"smartbin/{args.bin_id}/command"

    client = mqtt.Client()

    def on_connect(client, userdata, flags, rc):
        if rc == 0:
            client.subscribe(cmd_topic, qos=qos)
            send_discovery(client, args.bin_id, args.sensor_id, ha_pir_topic, ha_fill_topic, ha_emptied_topic)
        else:
            print(f"[PUB] Connection failed: {rc}")

    def on_message(client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode())
            if payload.get("action") == "emptied":
                # Use provided time from API or current time
                emptied_time = payload.get("emptied_at") or utc_now_iso()
                
                print(f"[CMD] Bin emptied at {emptied_time}. Resetting levels.")
                
                # Update internal state
                state["item_count"] = 0
                state["fill_level"] = 0
                state["last_emptied"] = emptied_time
                
                # Update Home Assistant immediately
                client.publish(ha_fill_topic, "0", qos=qos, retain=True)
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
        client.publish(ha_fill_topic, str(state["fill_level"]), qos=qos)

        state["published"] += 1
        event_q.task_done()

    client.loop_stop()
    client.disconnect()

def main() -> None:
    logging.basicConfig(level=logging.INFO)
    args = parse_args()

    event_q: Queue = Queue(maxsize=args.queue_size)
    state = {
        "produced": 0, "published": 0, "dropped": 0, 
        "item_count": 0, "fill_level": 0,
        "last_emptied": "Unknown" # Initial state
    }
    stop_flag = {"stop": False}

    sampler = PirSampler(pin=args.pin)
    interp = PirInterpreter(cooldown_s=args.cooldown, min_high_s=args.min_high)

    producer_t = threading.Thread(target=producer_loop, args=(event_q, sampler, interp, args, state, stop_flag), daemon=True)
    publisher_t = threading.Thread(target=publisher_loop, args=(event_q, args, state, stop_flag), daemon=True)

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

if __name__ == "__main__":
    main()