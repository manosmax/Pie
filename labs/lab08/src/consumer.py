"""
Smart Wastebin — MQTT Consumer
================================
Subscribes to the motion-event topic published by the producer,
enriches every record with ingest_time + pipeline_latency_ms,
and appends it to a JSONL file.

FIX: Previous file was erroneously a second producer (used PirSampler /
PirInterpreter, touched GPIO).  Real consumer has no hardware dependency.
FIX: Added --out argument that docker-compose.yml was already passing.
FIX: Added ingest_time and pipeline_latency_ms enrichment that the
     AsyncAPI spec promised but was never implemented.
"""

import argparse
import json
import logging
import os
from datetime import datetime, timezone

import paho.mqtt.client as mqtt

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def utc_now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def parse_iso(ts: str) -> datetime:
    """Parse an ISO-8601 timestamp that may end in Z or +00:00."""
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


# ---------------------------------------------------------------------------
# MQTT callbacks
# ---------------------------------------------------------------------------

def make_on_connect(args: argparse.Namespace):
    def on_connect(client, userdata, flags, reason_code, properties):
        if reason_code == 0:
            logger.info("[CONSUMER] Connected to broker %s:%s", args.host, args.port)
            client.subscribe(args.topic, qos=1)
            logger.info("[CONSUMER] Subscribed to %s", args.topic)
        else:
            logger.error("[CONSUMER] Connection failed rc=%s", reason_code)
    return on_connect


def make_on_message(args: argparse.Namespace):
    def on_message(client, userdata, msg):
        # --- Deserialise ---
        try:
            record = json.loads(msg.payload.decode("utf-8", errors="replace"))
        except json.JSONDecodeError as exc:
            logger.warning("[CONSUMER] Bad JSON on %s: %s", msg.topic, exc)
            return

        # --- Enrich: ingest_time ---
        ingest_ts = utc_now_iso()
        record["ingest_time"] = ingest_ts

        # --- Enrich: pipeline_latency_ms ---
        event_ts_str = record.get("event_time")
        if event_ts_str:
            try:
                event_dt  = parse_iso(event_ts_str)
                ingest_dt = parse_iso(ingest_ts)
                latency_ms = (ingest_dt - event_dt).total_seconds() * 1000.0
                record["pipeline_latency_ms"] = round(latency_ms, 3)
            except Exception as exc:
                logger.debug("[CONSUMER] Could not compute latency: %s", exc)

        # --- Persist ---
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")

        if args.verbose:
            logger.debug(
                "[CONSUMER] seq=%-4s  latency=%.1f ms  fill=%s%%",
                record.get("seq", "?"),
                record.get("pipeline_latency_ms", float("nan")),
                record.get("fill_level", "?"),
            )

    return on_message


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Smart Wastebin MQTT Consumer — subscribes to events, writes JSONL"
    )
    parser.add_argument("--host",    default="localhost",
                        help="MQTT broker hostname (default: localhost)")
    parser.add_argument("--port",    type=int, default=1883,
                        help="MQTT broker port (default: 1883)")
    parser.add_argument("--topic",   default="smartbin/bin-01/pir-01/events",
                        help="Topic to subscribe to")
    parser.add_argument("--out",     default="/app/data/motion_events.jsonl",
                        help="Output JSONL file path")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, "wastebin-consumer")
    client.on_connect = make_on_connect(args)
    client.on_message = make_on_message(args)
    client.reconnect_delay_set(min_delay=1, max_delay=30)
    client.connect(args.host, args.port, keepalive=60)

    logger.info("[CONSUMER] Writing to %s", args.out)

    try:
        client.loop_forever()
    except KeyboardInterrupt:
        logger.info("\n[CONSUMER] Shutting down.")
        client.disconnect()


if __name__ == "__main__":
    main()
