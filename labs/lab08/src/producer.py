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

def send_discovery(client, bin_id, sensor_id, pir_topic, fill_topic):
    """Sends the MQTT Discovery JSON to Home Assistant for Motion and Fill Level sensors."""

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

    client.publish(f"homeassistant/binary_sensor/{bin_id}_{sensor_id}/config", json.dumps(pir_config), qos=1, retain=True)
    client.publish(f"homeassistant/sensor/{bin_id}_fill/config", json.dumps(fill_config), qos=1, retain=True)

    print("[HA] Discovery sent for Motion and Fill Level entities.")

def utc_now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="PIR producer — reads sensor, publishes to MQTT")
    p.add_argument("--device-id",       default="urn:dev:team08:pir-01")
    p.add_argument("--bin-id",          default="bin-01")
    p.add_argument("--sensor-id",       default="pir-01")
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

JSONLD_CONTEXT = {
    "@vocab":   "https://schema.org/",
    "sosa":     "http://www.w3.org/ns/sosa/",
    "ssn":      "http://www.w3.org/ns/ssn/",
    "xsd":      "http://www.w3.org/2001/XMLSchema#",
    "pipeline": "https://github.com/manosmax/Pie/blob/main/docs/ontology.md#",
    "event_time":          {"@id": "sosa:resultTime",         "@type": "xsd:dateTime"},
    "ingest_time":         {"@id": "pipeline:ingestTime",     "@type": "xsd:dateTime"},
    "device_id":           {"@id": "sosa:madeBySensor",       "@type": "@id"},
    "mounted_on":          {"@id": "sosa:isHostedBy",         "@type": "@id"},
    "event_type":          {"@id": "sosa:observedProperty",   "@type": "@id"},
    "motion_state":        {"@id": "sosa:hasSimpleResult",    "@type": "xsd:string"},
    "seq":                 {"@id": "pipeline:sequenceNumber", "@type": "xsd:integer"},
    "run_id":              {"@id": "pipeline:runId",          "@type": "xsd:string"},
    "pipeline_latency_ms": {"@id": "pipeline:latencyMs",      "@type": "xsd:decimal"},
    "item_count":          {"@id": "pipeline:itemCount",      "@type": "xsd:integer"},
    "fill_level":          {"@id": "pipeline:fillLevel",      "@type": "xsd:integer"}
}

BIN_CAPACITY = 50

def producer_loop(
    event_q: Queue,
    sampler: PirSampler,
    interp: PirInterpreter,
    args: argparse.Namespace,
    metrics: dict,
    stop_flag: dict,
    state: dict,
) -> None:
    run_id = str(uuid.uuid4())
    seq = 0

    while not stop_flag["stop"]:
        t = time.monotonic()
        raw = sampler.read()

        for _ in interp.update(raw, t):
            seq += 1
            state["item_count"] += 1
            fill_level = min(int((state["item_count"] / BIN_CAPACITY) * 100), 100)

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
                "fill_level": fill_level
            }
            try:
                event_q.put_nowait(record)
                metrics["produced"] += 1
            except Full:
                metrics["dropped"] += 1
                logger.warning("Queue full — event dropped (seq=%d)", seq)

        time.sleep(args.sample_interval)

def publisher_loop(
    event_q: Queue,
    args: argparse.Namespace,
    metrics: dict,
    stop_flag: dict,
    state: dict,
) -> None:
    topic, qos = args.topic, args.qos
    ha_pir_topic  = f"smartbin/{args.bin_id}/{args.sensor_id}/motion"
    ha_fill_topic = f"smartbin/{args.bin_id}/fill-level/state"
    command_topic = f"smartbin/{args.bin_id}/command"

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)

    def on_connect(client, userdata, flags, reason_code, properties):
        if reason_code == 0:
            print("[PUB] Connected to MQTT Broker")
            send_discovery(client, args.bin_id, args.sensor_id, ha_pir_topic, ha_fill_topic)
            # Subscribe to wildcard to match API's topic format (smartbin/urn:wastebin:{bin_id}/command)
            client.subscribe("smartbin/+/command", qos=qos)
            print(f"[PUB] Subscribed to smartbin/+/command (matches: {command_topic})")
        else:
            print(f"[PUB] Connection failed with code {reason_code}")

    def on_message(client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode())
            if payload.get("action") == "emptied":
                print(f"[PUB] Received emptied command: {payload}")
                state["item_count"] = 0
                # Publish reset fill_level immediately to Home Assistant
                client.publish(ha_fill_topic, "0", qos=qos)
                print(f"[PUB] Reset item_count and fill_level to 0, published to {ha_fill_topic}")
        except json.JSONDecodeError:
            print(f"[PUB] Failed to parse command message: {msg.payload}")

    client.on_connect = on_connect
    client.on_message = on_message
    client.will_set(f"{topic}/status", "offline", qos=qos, retain=True)
    client.on_publish = lambda *_: metrics.__setitem__(
        "published", metrics["published"] + 1
    )

    client.connect(args.host, args.port, keepalive=60)
    client.loop_start()
    client.publish(f"{topic}/status", "online", qos=qos, retain=True)

    while not stop_flag["stop"] or not event_q.empty():
        try:
            record = event_q.get(timeout=0.5)
        except Empty:
            continue

        result = client.publish(topic, json.dumps(record, default=str), qos=qos)

        client.publish(ha_pir_topic, "detected", qos=qos)

        fill_level = record.get("fill_level", 0)
        client.publish(ha_fill_topic, str(fill_level), qos=qos)

        if result.rc != mqtt.MQTT_ERR_SUCCESS:
            metrics["errors"] += 1
            logger.warning("Publish failed (rc=%d)", result.rc)
        elif args.verbose:
            print(f"[PUB] seq={record.get('seq')} → fill={fill_level}%")

        event_q.task_done()

    client.publish(f"{topic}/status", "offline", qos=qos, retain=True).wait_for_publish(3.0)
    client.loop_stop()
    client.disconnect()

def main() -> None:
    logging.basicConfig(level=logging.INFO)
    args = parse_args()

    event_q: Queue = Queue(maxsize=args.queue_size)
    metrics = {"produced": 0, "published": 0, "dropped": 0, "errors": 0}
    stop_flag = {"stop": False}

    sampler = PirSampler(pin=args.pin)
    interp = PirInterpreter(cooldown_s=args.cooldown, min_high_s=args.min_high)
    state = {"item_count": 0}

    producer_t = threading.Thread(
        target=producer_loop,
        args=(event_q, sampler, interp, args, metrics, stop_flag, state),
        daemon=True,
    )
    publisher_t = threading.Thread(
        target=publisher_loop,
        args=(event_q, args, metrics, stop_flag, state),
        daemon=True,
    )

    print(f"[producer] Starting — bin={args.bin_id} sensor={args.sensor_id} duration={args.duration}s")
    producer_t.start()
    publisher_t.start()

    start_t = time.time()

    try:
        while (time.time() - start_t) < args.duration:
            if args.verbose:
                print(
                    f"[status] produced={metrics['produced']} "
                    f"published={metrics['published']} "
                    f"dropped={metrics['dropped']} "
                    f"queue={event_q.qsize()}"
                )
            time.sleep(2.0)
    except KeyboardInterrupt:
        print("\n[producer] Ctrl-C — stopping...")
    finally:
        stop_flag["stop"] = True
        producer_t.join()
        publisher_t.join()
        sampler.cleanup()

    print(
        f"[producer] Done. produced={metrics['produced']} "
        f"published={metrics['published']} dropped={metrics['dropped']}"
    )

if __name__ == "__main__":
    main()
