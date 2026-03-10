"""
run_pipeline.py

Producer/consumer pipeline for PIR motion detection.
Producer reads PIR samples, interprets them, and pushes structured
event records onto a bounded queue.
Consumer drains the queue, enriches records with ingest time and
pipeline latency, and writes valid JSONL to disk.
"""

import argparse
import json
import threading
import time
import uuid
from datetime import datetime, timezone
from queue import Empty, Full, Queue


# ---------------------------------------------------------------------------
# Timestamp helpers
# ---------------------------------------------------------------------------

def utc_now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string with millisecond
    precision and a trailing Z (e.g. 2025-04-01T12:00:00.123Z)."""
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def parse_iso_utc(s: str) -> datetime:
    """Parse an ISO-8601 UTC string (with trailing Z) into a datetime."""
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


# ---------------------------------------------------------------------------
# Sampler – reads the PIR GPIO pin (or simulates it when RPi.GPIO is absent)
# ---------------------------------------------------------------------------

class PIRSampler:
    """Thin wrapper around a single GPIO input pin."""

    def __init__(self, pin: int):
        self.pin = pin
        self._simulated = False
        try:
            import RPi.GPIO as GPIO  # type: ignore
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(pin, GPIO.IN)
            self._gpio = GPIO
        except (ImportError, RuntimeError):
            # Not on a Raspberry Pi – use a simulated signal for testing.
            import random
            self._random = random
            self._simulated = True
            print(
                f"[sampler] RPi.GPIO not available; "
                f"simulating pin {pin} with random values."
            )

    def read(self) -> int:
        """Return 1 (motion) or 0 (no motion)."""
        if self._simulated:
            # ~20 % chance of a HIGH sample so events are visible in demos.
            return 1 if self._random.random() < 0.20 else 0
        return self._gpio.input(self.pin)

    def cleanup(self):
        if not self._simulated:
            self._gpio.cleanup()


# ---------------------------------------------------------------------------
# Interpreter – converts a raw sample stream into discrete motion events
# ---------------------------------------------------------------------------

class MotionInterpreter:
    """
    Debounce logic:
    - A motion event is emitted once the pin has been HIGH for at least
      min_high_seconds continuously.
    - After an event is emitted the sensor enters a cooldown period during
      which further HIGH samples are ignored.
    """

    def __init__(self, min_high_seconds: float, cooldown_seconds: float):
        self.min_high = min_high_seconds
        self.cooldown = cooldown_seconds

        self._high_since: float | None = None
        self._last_event_time: float | None = None
        self._event_fired = False  # True while pin stays HIGH after an event

    def update(self, sample: int, now: float) -> list[dict]:
        """
        Feed one sample and return a list of event dicts (usually empty or
        containing a single entry).

        Each dict has keys: motion_state ("detected").
        """
        events: list[dict] = []

        # --- cooldown check ---
        if self._last_event_time is not None:
            if (now - self._last_event_time) < self.cooldown:
                # Still in cooldown; reset rising-edge tracker if pin went low.
                if sample == 0:
                    self._high_since = None
                    self._event_fired = False
                return events

        if sample == 1:
            if self._high_since is None:
                self._high_since = now
                self._event_fired = False

            elapsed = now - self._high_since
            if elapsed >= self.min_high and not self._event_fired:
                events.append({"motion_state": "detected"})
                self._last_event_time = now
                self._event_fired = True
        else:
            # Pin went LOW – reset.
            self._high_since = None
            self._event_fired = False

        return events


# ---------------------------------------------------------------------------
# Producer thread
# ---------------------------------------------------------------------------

def producer_loop(
    event_q: Queue,
    sampler: PIRSampler,
    interp: MotionInterpreter,
    args: argparse.Namespace,
    metrics: dict,
    stop_flag: dict,
):
    run_id = str(uuid.uuid4())
    seq = 0

    while not stop_flag["stop"]:
        now = time.time()
        sample = sampler.read()

        for evt in interp.update(sample, now):
            seq += 1
            record = {
                "event_time": utc_now_iso(),
                "device_id": args.device_id,
                "event_type": "motion",
                "motion_state": evt["motion_state"],
                "seq": seq,
                "run_id": run_id,
            }
            try:
                event_q.put_nowait(record)
                metrics["produced"] += 1
            except Full:
                metrics["dropped"] += 1

        time.sleep(args.sample_interval)


# ---------------------------------------------------------------------------
# Consumer thread
# ---------------------------------------------------------------------------

def consumer_loop(
    event_q: Queue,
    out_path: str,
    args: argparse.Namespace,
    metrics: dict,
    stop_flag: dict,
):
    with open(out_path, "a", encoding="utf-8") as fh:
        while not stop_flag["stop"] or not event_q.empty():
            try:
                record = event_q.get(timeout=0.5)
            except Empty:
                continue

            # Enrich with ingest metadata.
            record["ingest_time"] = utc_now_iso()

            event_dt = parse_iso_utc(record["event_time"])
            ingest_dt = parse_iso_utc(record["ingest_time"])
            latency_ms = (ingest_dt - event_dt).total_seconds() * 1000.0
            record["pipeline_latency_ms"] = round(latency_ms, 3)

            fh.write(json.dumps(record) + "\n")
            fh.flush()

            metrics["consumed"] += 1
            current_q = event_q.qsize()
            if current_q > metrics["max_queue"]:
                metrics["max_queue"] = current_q

            event_q.task_done()

            if args.consumer_delay > 0.0:
                time.sleep(args.consumer_delay)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="PIR motion-detection pipeline (producer/consumer)."
    )
    parser.add_argument(
        "--device-id", default="pir-01",
        help="Logical identifier for this sensor (default: pir-01)."
    )
    parser.add_argument(
        "--pin", type=int, default=18,
        help="BCM GPIO pin number the PIR sensor is wired to (default: 18)."
    )
    parser.add_argument(
        "--sample-interval", type=float, default=0.1,
        help="Seconds between GPIO reads in the producer (default: 0.1)."
    )
    parser.add_argument(
        "--cooldown", type=float, default=5.0,
        help="Seconds to wait after an event before emitting another (default: 5)."
    )
    parser.add_argument(
        "--min-high", type=float, default=0.2,
        help="Seconds the pin must stay HIGH before an event is emitted (default: 0.2)."
    )
    parser.add_argument(
        "--queue-size", type=int, default=100,
        help="Maximum number of records the bounded queue may hold (default: 100)."
    )
    parser.add_argument(
        "--consumer-delay", type=float, default=0.0,
        help="Artificial delay (seconds) added after each record is consumed (default: 0)."
    )
    parser.add_argument(
        "--duration", type=float, default=60.0,
        help="How long (seconds) to run the pipeline (default: 60)."
    )
    parser.add_argument(
        "--out", default="motion_pipeline.jsonl",
        help="Output JSONL file path (default: motion_pipeline.jsonl)."
    )
    parser.add_argument(
        "--verbose", action="store_true",
        help="Print periodic status lines to stdout."
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    args = parse_args()

    # Shared state.
    event_q: Queue = Queue(maxsize=args.queue_size)
    metrics = {
        "produced": 0,
        "consumed": 0,
        "dropped": 0,
        "max_queue": 0,
    }
    stop_flag = {"stop": False}

    # Hardware / logic objects.
    sampler = PIRSampler(args.pin)
    interp = MotionInterpreter(
        min_high_seconds=args.min_high,
        cooldown_seconds=args.cooldown,
    )

    # Threads.
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

    producer_t.start()
    consumer_t.start()

    print(
        f"[main] pipeline started | device={args.device_id} "
        f"pin={args.pin} duration={args.duration}s out={args.out}"
    )

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
        print("\n[main] Ctrl-C received – stopping pipeline...")
    finally:
        stop_flag["stop"] = True
        producer_t.join()
        consumer_t.join()
        sampler.cleanup()

    print(
        f"[main] pipeline finished | "
        f"produced={metrics['produced']} "
        f"consumed={metrics['consumed']} "
        f"dropped={metrics['dropped']} "
        f"max_queue={metrics['max_queue']}"
    )


if __name__ == "__main__":
    main()