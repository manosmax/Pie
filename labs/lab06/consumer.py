import argparse
import json
import threading
import time
from datetime import datetime, timezone
from queue import Empty, Queue

import paho.mqtt.client as mqtt


def utc_now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="PIR consumer — subscribes to MQTT, writes JSONL")
    p.add_argument("--out",      default="motion_pipeline.jsonl")
    p.add_argument("--host",     default="localhost")
    p.add_argument("--port",     type=int, default=1883)
    p.add_argument("--qos",      type=int, default=1)
    p.add_argument("--topic",    default="smartbin/bin-01/pir-01/events")
    p.add_argument("--duration", type=float, default=600.0,
                   help="How long to run (seconds); 0 = run until Ctrl-C")
    p.add_argument("--verbose",  action="store_true")
    return p.parse_args()


def subscriber_loop(
    event_q: Queue,
    out_path: str,
    args: argparse.Namespace,
    metrics: dict,
    stop_flag: dict,
) -> None:
    topic, qos = args.topic, args.qos

    def on_connect(client, userdata, flags, rc):
        if rc == 0:
            client.subscribe(topic, qos=qos)
            print(f"[SUB] Connected and subscribed to {topic}")
        else:
            print(f"[SUB] Connection failed (rc={rc})")

    def on_message(client, userdata, msg):
        try:
            record = json.loads(msg.payload)
        except json.JSONDecodeError:
            print("[SUB] Received invalid JSON — skipping")
            return

        now = datetime.now(timezone.utc)
        record["ingest_time"] = now.isoformat(timespec="milliseconds").replace("+00:00", "Z")

        try:
            event_dt = datetime.fromisoformat(record["event_time"].replace("Z", "+00:00"))
            latency_ms = (now - event_dt).total_seconds() * 1000.0
            record["pipeline_latency_ms"] = round(latency_ms, 3)
        except (KeyError, ValueError):
            record["pipeline_latency_ms"] = None

        event_q.put(record)  # unbounded queue — won't block

    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(args.host, args.port, keepalive=60)
    client.loop_start()

    with open(out_path, "a", encoding="utf-8") as f:
        while not stop_flag["stop"] or not event_q.empty():
            try:
                record = event_q.get(timeout=0.5)
            except Empty:
                continue

            f.write(json.dumps(record) + "\n")
            f.flush()
            event_q.task_done()

            metrics["consumed"] += 1
            metrics["total_latency_ms"] += record.get("pipeline_latency_ms") or 0.0
            avg_lat = metrics["total_latency_ms"] / metrics["consumed"]

            if args.verbose:
                print(
                    f"[SUB] #{metrics['consumed']} seq={record.get('seq')} "
                    f"latency={record.get('pipeline_latency_ms', 'N/A')}ms "
                    f"avg={avg_lat:.1f}ms"
                )

    client.loop_stop()
    client.disconnect()


def main() -> None:
    args = parse_args()

    event_q: Queue = Queue()
    metrics = {"consumed": 0, "total_latency_ms": 0.0}
    stop_flag = {"stop": False}

    worker_t = threading.Thread(
        target=subscriber_loop,
        args=(event_q, args.out, args, metrics, stop_flag),
        daemon=True,
    )

    print(f"[consumer] Starting — topic={args.topic} out={args.out}")
    worker_t.start()

    start_t = time.time()
    try:
        while True:
            if args.duration > 0 and (time.time() - start_t) >= args.duration:
                break
            time.sleep(1.0)
    except KeyboardInterrupt:
        print("\n[consumer] Ctrl-C — stopping...")
    finally:
        stop_flag["stop"] = True
        worker_t.join()

    print(f"[consumer] Done. consumed={metrics['consumed']}")


if __name__ == "__main__":
    main()