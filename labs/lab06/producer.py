import argparse
import time
import uuid
from datetime import datetime, timezone
from queue import Empty, Full, Queue
from pirlib import PirInterpreter, PirSampler
import threading
import paho.mqtt.client as mqtt   # ✅ fix 1: wrong import syntax
import logging
import json


def utc_now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )

def parse_iso_utc(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))

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

    jsonld_context = {
        "@vocab": "https://schema.org/",
        "sosa": "http://www.w3.org/ns/sosa/",
        "ssn": "http://www.w3.org/ns/ssn/",
        "xsd": "http://www.w3.org/2001/XMLSchema#",
        "pipeline": "https://github.com/manosmax/Pie/blob/main/docs/Ontology#",
        "event_time": {"@id": "sosa:resultTime", "@type": "xsd:dateTime"},
        "ingest_time": {"@id": "pipeline:ingestTime", "@type": "xsd:dateTime"},
        "device_id": {"@id": "sosa:madeBySensor", "@type": "@id"},
        "mounted_on": {"@id": "sosa:isHostedBy", "@type": "@id"},
        "event_type": {"@id": "sosa:observedProperty", "@type": "@id"},
        "motion_state": {"@id": "sosa:hasSimpleResult", "@type": "xsd:string"},
        "seq": {"@id": "pipeline:sequenceNumber", "@type": "xsd:integer"},
        "run_id": {"@id": "pipeline:runId", "@type": "xsd:string"},
        "pipeline_latency_ms": {"@id": "pipeline:latencyMs", "@type": "xsd:decimal"}
    }

    while not stop_flag["stop"]:
        t = time.monotonic()
        raw = sampler.read()

        for _event in interp.update(raw, t):
            seq += 1
            record = {
                "@context": jsonld_context,
                "@id": f"urn:event:{run_id}:{seq}",
                "@type": "sosa:Observation",
                "event_time": utc_now_iso(),
                "device_id": args.device_id,
                "event_type": "urn:prop:team08:motion",
                "motion_state": "detected",
                "seq": seq,
                "run_id": run_id,
                "mounted_on": "urn:wastebin:bin-01"
            }
            try:
                event_q.put_nowait(record)
                metrics["produced"] += 1
            except Full:
                metrics["dropped"] += 1

        time.sleep(args.sample_interval)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="PIR motion event pipeline")
    p.add_argument("--device-id",        default="urn:dev:team08:pir-01")
    p.add_argument("--pin",              type=int,   default=17)
    p.add_argument("--sample-interval",  type=float, default=0.1)
    p.add_argument("--cooldown",         type=float, default=5.0)
    p.add_argument("--min-high",         type=float, default=0.2)
    p.add_argument("--queue-size",       type=int,   default=100)
    p.add_argument("--consumer-delay",   type=float, default=0.0)
    p.add_argument("--duration",         type=float, default=60.0)
    p.add_argument("--verbose",          action="store_true")
    p.add_argument("--host",             default="localhost")          
    p.add_argument("--port",             type=int,   default=1883)   
    p.add_argument("--qos",              type=int,   default=1)      
    p.add_argument("--topic",            default="smartbin/bin-01/pir-01/events")  
    return p.parse_args()


logger = logging.getLogger(__name__)

def publisher_loop(
    event_q: Queue,
    out_path: str,
    args,
    metrics: dict,
    stop_flag: dict,
) -> None:
    topic, qos = args.topic, args.qos

    client = mqtt.Client()
    client.will_set(f"{topic}/status", "offline", qos=qos, retain=True)
    client.on_publish = lambda *_: metrics.update(published=metrics["published"] + 1) 

    client.connect(args.host, args.port, keepalive=60)
    client.loop_start()
    client.publish(f"{topic}/status", "online", qos=qos, retain=True)

    while not stop_flag["stop"] or not event_q.empty():
        try:
            record = event_q.get(timeout=0.5)
        except Empty:
            continue

        result = client.publish(topic, json.dumps(record, default=str), qos=qos)

        if result.rc != mqtt.MQTT_ERR_SUCCESS:
            metrics["errors"] = metrics.get("errors", 0) + 1
            logger.warning("Publish failed (rc=%d)", result.rc)
        elif args.verbose:
            print(f"[MQTT] seq={record.get('seq')} type={record.get('event_type')} → {topic}")

        event_q.task_done()

    client.loop_stop()
    client.publish(f"{topic}/status", "offline", qos=qos, retain=True).wait_for_publish(3.0)
    client.disconnect()


def main() -> None:
    args = parse_args()
    event_q: Queue = Queue(maxsize=args.queue_size)
    metrics = {
        "produced":  0,
        "published": 0,
        "dropped":   0,
        "errors":    0,
        "max_queue": 0,
    }
    stop_flag = {"stop": False}

    sampler = PirSampler(pin=args.pin)
    interp  = PirInterpreter(cooldown_s=args.cooldown, min_high_s=args.min_high)

    producer_t = threading.Thread(
        target=producer_loop,
        args=(event_q, sampler, interp, args, metrics, stop_flag),
        daemon=True,
    )
    publisher_t = threading.Thread(
        target=publisher_loop,
        args=(event_q, args.out, args, metrics, stop_flag),  
        daemon=True,
    )

    print(f"[main] Starting pipeline device={args.device_id} pin={args.pin} "
          f"duration={args.duration}s out={args.out}")

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
            time.sleep(1.0)
    except KeyboardInterrupt:
        print("\n[main] Ctrl-C received — stopping...")
    finally:
        stop_flag["stop"] = True
        producer_t.join()
        publisher_t.join()
        sampler.cleanup()

    print(
        f"[main] Done. produced={metrics['produced']} "
        f"published={metrics['published']} dropped={metrics['dropped']}"
    )

if __name__ == "__main__":
    main()