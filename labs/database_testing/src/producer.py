
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


# State persistence


STATE_FILE = "/app/data/sensor_state.json"
state_lock = threading.Lock()


def load_state() -> dict:
    
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                logger.info("[STATE] Loaded: item_count=%s fill_level=%s",
                            data.get("item_count", 0), data.get("fill_level", 0))
                return data
        except Exception as exc:
            logger.warning("[STATE] Could not load state file (%s) — starting fresh.", exc)
    return {"item_count": 0, "fill_level": 0}


def save_state(state: dict) -> None:
    
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f)
    os.replace(tmp, STATE_FILE)



# Constants


BIN_CAPACITY = 50

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
    "fill_level":          {"@id": "pipeline:fillLevel",      "@type": "xsd:integer"},
}



# Helpers


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



# Home Assistant MQTT Discovery


def send_discovery(client, bin_id: str, sensor_id: str, pir_topic: str, fill_topic: str) -> None:
    """Publish retained HA MQTT Discovery payloads."""
    device_info = {
        "identifiers": [bin_id],
        "name": f"Smart Waste Bin {bin_id}",
        "model": "IoT-Bin-v2",
        "manufacturer": "Team 08",
    }

    pir_config = {
        "name": f"Waste Bin {bin_id} Motion",
        "state_topic": pir_topic,
        "payload_on": "detected",
        "payload_off": "clear",
        "device_class": "motion",
        "unique_id": f"{bin_id}_{sensor_id}_motion",
        "off_delay": 6,
        "device": device_info,
    }

    fill_config = {
        "name": f"Waste Bin {bin_id} Fill Level",
        "state_topic": fill_topic,
        "unit_of_measurement": "%",
        "icon": "mdi:delete-variant",
        "state_class": "measurement",
        "unique_id": f"{bin_id}_fill_level",
        "device": device_info,
    }

    client.publish(
        f"homeassistant/binary_sensor/{bin_id}_{sensor_id}/config",
        json.dumps(pir_config), qos=1, retain=True,
    )
    client.publish(
        f"homeassistant/sensor/{bin_id}_fill/config",
        json.dumps(fill_config), qos=1, retain=True,
    )
    logger.info("[HA] Discovery sent for Motion and Fill Level entities.")



# Producer thread — reads GPIO, enqueues event dicts


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

            with state_lock:
                state["item_count"] += 1
                fill_level = min(int((state["item_count"] / BIN_CAPACITY) * 100), 100)
                state["fill_level"] = fill_level
                save_state(state)

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
                "fill_level": fill_level,
            }

            try:
                event_q.put_nowait(record)
                metrics["produced"] += 1
            except Full:
                metrics["dropped"] += 1
                logger.warning("[PRODUCER] Queue full — event dropped (seq=%d)", seq)

        time.sleep(args.sample_interval)



# Publisher thread — drains queue, sends to MQTT, handles commands


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
            logger.info("[PUB] Connected to MQTT Broker")
            send_discovery(client, args.bin_id, args.sensor_id, ha_pir_topic, ha_fill_topic)

            client.subscribe(command_topic, qos=qos)
            logger.info("[PUB] Subscribed to %s", command_topic)
        else:
            logger.error("[PUB] Connection failed rc=%s", reason_code)

    def on_message(client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode())
        except json.JSONDecodeError:
            logger.warning("[PUB] Failed to parse command: %s", msg.payload)
            return

        if payload.get("action") == "emptied":
            emptied_at = payload.get("emptied_at") or utc_now_iso()
            emptied_by = payload.get("emptied_by", "unknown")

            with state_lock:
                if state["fill_level"] == 0 and state["item_count"] == 0:
                    logger.info("[CMD] Bin %s already empty — ignoring duplicate.", args.bin_id)
                    return
                state["item_count"] = 0
                state["fill_level"] = 0
                
                save_state(state)

            client.publish(ha_fill_topic, "0", qos=qos, retain=True)
            logger.info("[CMD] Bin %s emptied by '%s' at %s.", args.bin_id, emptied_by, emptied_at)
        else:
            logger.warning("[PUB] Unknown command action: %s", payload.get("action"))

    client.on_connect = on_connect
    client.on_message = on_message
    client.will_set(f"{topic}/status", "offline", qos=qos, retain=True)
    client.on_publish = lambda *_: metrics.__setitem__(
        "published", metrics["published"] + 1
    )
    client.reconnect_delay_set(min_delay=1, max_delay=30)
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
        client.publish(ha_fill_topic, str(record.get("fill_level", 0)), qos=qos)

        if result.rc != mqtt.MQTT_ERR_SUCCESS:
            metrics["errors"] += 1
            logger.warning("[PUB] Publish failed rc=%d", result.rc)
        elif args.verbose:
            logger.debug("[PUB] seq=%s  fill=%s%%", record.get("seq"), record.get("fill_level"))

        event_q.task_done()

    client.publish(f"{topic}/status", "offline", qos=qos, retain=True).wait_for_publish(3.0)
    client.loop_stop()
    client.disconnect()



# Entry point


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    args = parse_args()
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    
    state     = load_state()
    event_q: Queue = Queue(maxsize=args.queue_size)
    metrics   = {"produced": 0, "published": 0, "dropped": 0, "errors": 0}
    stop_flag = {"stop": False}

    sampler = PirSampler(pin=args.pin)
    interp  = PirInterpreter(cooldown_s=args.cooldown, min_high_s=args.min_high)

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

    logger.info(
        "[PRODUCER] Starting — bin=%s sensor=%s duration=%.0fs  "
        "resumed item_count=%s fill=%s%%",
        args.bin_id, args.sensor_id, args.duration,
        state["item_count"], state["fill_level"],
    )
    producer_t.start()
    publisher_t.start()

    start_t = time.time()
    try:
        while (time.time() - start_t) < args.duration:
            if args.verbose:
                logger.debug(
                    "[STATUS] produced=%s published=%s dropped=%s queue=%s",
                    metrics["produced"], metrics["published"],
                    metrics["dropped"], event_q.qsize(),
                )
            time.sleep(2.0)
    except KeyboardInterrupt:
        logger.info("\n[PRODUCER] Ctrl-C — stopping...")
    finally:
        stop_flag["stop"] = True
        producer_t.join(timeout=5)
        publisher_t.join(timeout=5)
        sampler.cleanup()

    logger.info(
        "[PRODUCER] Done. produced=%s published=%s dropped=%s",
        metrics["produced"], metrics["published"], metrics["dropped"],
    )


if __name__ == "__main__":
    main()
