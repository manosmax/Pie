import argparse
import json
import threading
import time
import uuid
from datetime import datetime, timezone
from queue import Empty, Full, Queue
from pirlib import PirInterpreter, PirSampler
from models import *


def utc_now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def parse_iso_utc(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))

# Producer thread
def producer_loop(
    event_q: Queue,
    sampler: PirSampler,
    interp: PirInterpreter,
    args: argparse.Namespace,
    metrics: dict,
    stop_flag: dict,
) -> None:
    """
    Reads PIR samples, passes them through the interpreter, and enqueues
    structured event records.  Drops the newest record when the queue is full
    """
    run_id = str(uuid.uuid4())
    seq = 0

    while not stop_flag["stop"]:
        t = time.monotonic()
        raw = sampler.read()

        for _event in interp.update(raw, t):
            seq += 1

            record = {
                "event_time":   utc_now_iso(),
                "device_id":    args.device_id,
                "event_type":   "motion",
                "motion_state": "detected",
                "seq":          seq,
                "run_id":       run_id,
                "mounted_on":   "urn:wastebin:team08:bin-01"

            }

            try:
                event_q.put_nowait(record)
                metrics["produced"] += 1
            except Full:
                metrics["dropped"] += 1

        time.sleep(args.sample_interval)

# Consumer thread

def consumer_loop(
    event_q: Queue,
    out_path: str,
    args: argparse.Namespace,
    metrics: dict,
    stop_flag: dict,
) -> None:
    """
    Dequeues event records, enriches them with ingest_time and
    pipeline_latency_ms, then writes one JSON object per line to the
    output file.
    """
    with open(out_path, "a", encoding="utf-8") as f:
        while not stop_flag["stop"] or not event_q.empty():
            try:
                record = event_q.get(timeout=0.5)
            except Empty:
                continue

            # Enrich the record
            ingest_ts = utc_now_iso()
            record["ingest_time"] = ingest_ts

            event_dt  = parse_iso_utc(record["event_time"])
            ingest_dt = parse_iso_utc(ingest_ts)
            latency_ms = (ingest_dt - event_dt).total_seconds() * 1000.0
            record["pipeline_latency_ms"] = round(latency_ms, 3)

            # Write one JSON line and flush immediately
            f.write(json.dumps(record) + "\n")
            f.flush()

            metrics["consumed"] += 1
            metrics["max_queue"] = max(metrics["max_queue"], event_q.qsize())
            event_q.task_done()

            if args.consumer_delay > 0.0:
                time.sleep(args.consumer_delay)

# CLI

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="PIR motion event pipeline")

    p.add_argument("--device-id",        default="pir-01",
                   help="Logical name for this sensor device")
    p.add_argument("--pin",              type=int,   default=17,
                   help="BCM GPIO pin number the PIR is wired to")
    p.add_argument("--sample-interval",  type=float, default=0.1,
                   help="Seconds between PIR reads (e.g. 0.1 = 10 Hz)")
    p.add_argument("--cooldown",         type=float, default=5.0,
                   help="Minimum seconds between emitted events (interpreter cooldown)")
    p.add_argument("--min-high",         type=float, default=0.2,
                   help="Minimum seconds the signal must stay HIGH before emitting")
    p.add_argument("--queue-size",       type=int,   default=100,
                   help="Maximum number of records the bounded queue can hold")
    p.add_argument("--consumer-delay",   type=float, default=0.0,
                   help="Artificial delay (s) added per record in the consumer "
                        "(simulate slow downstream)")
    p.add_argument("--duration",         type=float, default=60.0,
                   help="How long (seconds) to run the pipeline before stopping")
    p.add_argument("--out",              default="motion_pipeline.jsonl",
                   help="Path to the JSONL output file")
    p.add_argument("--verbose",          action="store_true",
                   help="Print periodic status lines to stdout")

    return p.parse_args()


def main() -> None:
    args = parse_args()
    event_q: Queue = Queue(maxsize=args.queue_size)
    metrics = {
        "produced":  0,
        "consumed":  0,
        "dropped":   0,
        "max_queue": 0,
    }
    stop_flag = {"stop": False}

    
    sampler = PirSampler(pin=args.pin)
    interp  = PirInterpreter(
        cooldown_s=args.cooldown,
        min_high_s=args.min_high,
    )

    
    producer_t = threading.Thread(
        target=producer_loop,
        args=(event_q, sampler, interp, args, metrics, stop_flag),
        daemon=True,
    )
    consumer_t = threading.Thread(
        target=consumer_loop,
        args=(event_q, args.out, args, metrics, stop_flag),
        daemon=True,
    )

    print(f"[main] Starting pipeline  device={args.device_id}  pin={args.pin}  "
          f"duration={args.duration}s  out={args.out}")

    producer_t.start()
    consumer_t.start()

    start_t = time.time()
    try:
        while (time.time() - start_t) < args.duration:
            if args.verbose:
                print(
                    f"[status] produced={metrics['produced']} "
                    f"consumed={metrics['consumed']} "
                    f"dropped={metrics['dropped']} "
                    f"queue={event_q.qsize()} "
                    f"max_queue={metrics['max_queue']}"
                )
            time.sleep(1.0)
    except KeyboardInterrupt:
        print("\n[main] Ctrl-C received — stopping...")
    finally:
        stop_flag["stop"] = True
        producer_t.join()
        consumer_t.join()
        sampler.cleanup()

    print(
        f"[main] Done.  produced={metrics['produced']}  "
        f"consumed={metrics['consumed']}  dropped={metrics['dropped']}  "
        f"max_queue={metrics['max_queue']}"
    )


if __name__ == "__main__":
    main()