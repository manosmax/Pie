import argparse
import json
import threading
import time
import uuid
from datetime import datetime, timezone
from queue import Empty, Full, Queue
from pirlib import PirInterpreter, PirSampler
import paho.mqtt.client as mqtt

def utc_now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )

def parse_iso_utc(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()

    p.add_argument("--queue-size", type=int, default=100,
                   help="Maximum number of records in queue")
    p.add_argument("--out", default="motion_pipeline.jsonl",
                   help="Path to the JSONL output file")
    p.add_argument("--verbose", action="store_true",
                   help="Print periodic status lines")
    #new arguments for mqtt 
    p.add_argument("--port" , default = 1883)
    p.add_argument("--qos" , default = 1)
    p.add_argument("--topic" , default = "smartbin/bin-01/pir-01/events ")
    p.add_argument("--host", default="localhost")
    return p.parse_args()


def subscriber_loop(
    event_q: Queue,
    out_path: str,
    args,
    stop_flag: dict,
    consumed: int,
) -> None:
    topic, qos = args.topic, args.qos
    metrics = {"count": 0, "total_latency_ms": 0.0}

    def on_message(client, userdata, msg):
        record = json.loads(msg.payload)
        now = datetime.now(timezone.utc)
        record["ingest_time"] = now.isoformat()
        delta = (now - datetime.fromisoformat(record["event_time"])).total_seconds() * 1000
        record["pipeline_latency_ms"] = round(delta, 2)
        metrics["total_latency_ms"] += delta

        #put  
        event_q.put(record)            

    def on_connect(client, *_):
        client.subscribe(topic, qos=qos)   

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

            consumed += 1
            metrics["count"] += 1

            avg_lat = metrics["total_latency_ms"] / metrics["count"]
            print(f"[SUB] #{consumed} seq={record.get('seq')} "
                  f"latency={record.get('pipeline_latency_ms', 'N/A')}ms avg={avg_lat:.1f}ms")

    client.loop_stop()
    client.disconnect()





def main() -> None:
    args = parse_args()

    event_q   = Queue()
    stop_flag = {"stop": False}
    metrics   = {}
    consumed  = 0

    subscriber_loop(event_q, args.out, args, stop_flag, consumed)


if __name__ == "__main__":
    main()
