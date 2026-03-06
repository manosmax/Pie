import argparse
import json
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from pirlib.sampler     import PirSampler
from pirlib.interpreter import PirInterpreter


def utc_now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def posix_to_iso(ts: float) -> str:
    return (
        datetime.fromtimestamp(ts, tz=timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="pir_event_logger.py",
        description="Log PIR motion events to a JSONL file.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--device-id",        required=True,  metavar="ID",   help="Logical device identifier.")
    p.add_argument("--pin",              type=int,        default=18,     help="BCM GPIO pin.")
    p.add_argument("--sample-interval",  type=float,      default=0.1,    dest="sample_interval", help="Seconds between reads (E.2.1).")
    p.add_argument("--cooldown",         type=float,      default=5.0,    help="Min gap between events (E.2.3).")
    p.add_argument("--min-high",         type=float,      default=0.0,    dest="min_high", help="Min HIGH duration to emit (E.2.4).")
    p.add_argument("--duration",         type=float,      default=30.0,   help="Run time in seconds (0 = until Ctrl-C).")
    p.add_argument("--out",              default="motion_events.jsonl",   help="Output JSONL file (append).")
    p.add_argument("--verbose", "-v",    action="store_true",             help="Print each event to stdout.")
    return p


def validate(args: argparse.Namespace) -> None:
    errors = []
    if args.sample_interval <= 0:  errors.append("--sample-interval must be > 0")
    if args.cooldown < 0:          errors.append("--cooldown must be >= 0")
    if args.min_high < 0:          errors.append("--min-high must be >= 0")
    if args.duration < 0:          errors.append("--duration must be >= 0")
    if not (1 <= args.pin <= 27):  errors.append(f"--pin {args.pin} outside BCM range 1–27")
    if not args.device_id.strip(): errors.append("--device-id must not be empty")
    if errors:
        for e in errors:
            print(f"usage error: {e}", file=sys.stderr)
        sys.exit(2)

def main() -> None:
    p    = build_parser()
    args = p.parse_args()
    validate(args)

    # ── init sensor + interpreter ─────────────────────────────────────
    try:
        sampler = PirSampler(args.pin)
    except Exception as exc:
        print(f"RUNTIME ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    interp = PirInterpreter(cooldown_s=args.cooldown, min_high_s=args.min_high)

    # ── open output file (append) ─────────────────────────────────────
    out_path = Path(args.out)
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_file = out_path.open("a", encoding="utf-8")
    except OSError as exc:
        print(f"RUNTIME ERROR: cannot open {args.out!r}: {exc}", file=sys.stderr)
        sampler.cleanup()
        sys.exit(1)

    # ── session metadata ──────────────────────────────────────────────
    run_id  = str(uuid.uuid4())
    seq     = 0
    written = 0

    t0  = time.time()
    end = (t0 + args.duration) if args.duration > 0 else float("inf")

    print(
        f"[pir_event_logger] run_id={run_id}\n"
        f"  device_id={args.device_id!r}  sensor={sampler}\n"
        f"  pin={args.pin}  sample_interval={args.sample_interval}s  "
        f"cooldown={args.cooldown}s  min_high={args.min_high}s\n"
        f"  output={out_path.resolve()}\n"
        f"  duration={'unlimited' if args.duration == 0 else f'{args.duration}s'}"
    )

    try:
        while time.time() < end:
            now = time.time()
            raw = sampler.read()

            for ev in interp.update(raw, now):
                seq     += 1
                ingest_t = time.time()

                record = {

                    # ── required ──────────────────────────────────────
                    "seq":          seq,
                    "run_id":       run_id,
                    "device_id":    args.device_id,
                    "event_type":   "motion",
                    "motion_state": "detected",
                    "event_time":   posix_to_iso(now),
                    "ingest_time":  posix_to_iso(ingest_t),
                    "latency_ms":   round((ingest_t - now) * 1_000, 3),

                    # ── recommended ───────────────────────────────────
                    "pin":               args.pin,
                    "sample_interval_s": args.sample_interval,
                    "cooldown_s":        args.cooldown,
                    "min_high_s":        args.min_high,
                }

                line = json.dumps(record, separators=(",", ":"))
                try:
                    out_file.write(line + "\n")
                    out_file.flush()
                except OSError as exc:
                    print(f"RUNTIME ERROR: write failed: {exc}", file=sys.stderr)
                    sys.exit(1)

                written += 1
                if args.verbose:
                    print(
                        f"  t={now - t0:7.2f}s  seq={seq:04d}  "
                        f"event_time={record['event_time']}  "
                        f"latency={record['latency_ms']} ms"
                    )

            time.sleep(args.sample_interval)

    except KeyboardInterrupt:
        print("\n[pir_event_logger] Ctrl-C: stopping.")

    finally:
        out_file.close()
        sampler.cleanup()

    print(
        f"[pir_event_logger] done. "
        f"{written} event(s) written → {out_path}  (run_id={run_id})"
    )


if __name__ == "__main__":
    main()