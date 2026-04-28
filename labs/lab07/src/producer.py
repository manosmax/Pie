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


def utc_now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="PIR producer — reads sensor, publishes to MQTT")
    p.add_argument("--device-id",       default="urn:dev:team08:pir-01")
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
    "@vocab": "https://schema.org/",
    "sosa": "http://www.w3.org/ns/sosa/",
    "ssn": "http://www.w3.org/ns/ssn/",
    "xsd": "http://www.w3.org/2001/XMLSchema#",
    "pipeline": "https://github.com/manosmax/Smart-Waste-Bin/blob/main/docs/Ontology#",
    "event_time":           {"@id": "sosa:resultTime",        "@type": "xsd:dateTime"},
    "ingest_time":          {"@id": "pipeline:ingestTime",    "@type": "xsd:dateTime"},
    "device_id":            {"@id": "sosa:madeBySensor",      "@type": "@id"},
    "mounted_on":           {"@id": "sosa:isHostedBy",        "@type": "@id"},
    "event_type":           {"@id": "sosa:observedProperty",  "@type": "@id"},
    "motion_state":         {"@id": "sosa:hasSimpleResult",   "@type": "xsd:string"},
    "seq":                  {"@id": "pipeline:sequenceNumber","@type": "xsd:integer"},
    "run_id":               {"@id": "pipeline:runId",         "@type": "xsd:string"},
    "pipeline_latency_ms":  {"@id": "pipeline:latencyMs",     "@type": "xsd:decimal"},
}


def producer_loop(
    event_q: Queue,
    sampler: PirSampler,
    interp: PirInterpreter,
    args: argparse.Namespace,
    metrics: dict,
    stop_flag: dict,
) -> None:
    run_id = str(uuid.uuid4())
    seq = 0

    while not stop_flag["stop"]:
        t = time.monotonic()
        raw = sampler.read()

        for _ in interp.update(raw, t):
            seq += 1
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
                "mounted_on": "urn:wastebin:bin-01",
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
) -> None:
    topic, qos = args.topic, args.qos

    client = mqtt.Client()
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
        except Exception:
            continue

        result = client.publish(topic, json.dumps(record, default=str), qos=qos)
        if result.rc != mqtt.MQTT_ERR_SUCCESS:
            metrics["errors"] += 1
            logger.warning("Publish failed (rc=%d)", result.rc)
        elif args.verbose:
            print(f"[PUB] seq={record.get('seq')} → {topic}")

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

    # producer reads from the raw data and creates an event on the queue 
    producer_t = threading.Thread(
        target=producer_loop,
        args=(event_q, sampler, interp, args, metrics, stop_flag),
        daemon=True,
    )
    #publishes on the mqtt broker on the specified port 
    publisher_t = threading.Thread(
        target=publisher_loop,
        args=(event_q, args, metrics, stop_flag),
        daemon=True,
    )

    print(f"[producer] Starting — device={args.device_id} pin={args.pin} duration={args.duration}s")
    producer_t.start()
    publisher_t.start()

    start_t = time.time()


    #information for events 
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