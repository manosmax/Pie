import click
import json
import uuid
import time
import sys
from datetime import datetime, timezone

def utc_now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )

@click.command(no_args_is_help=True)
@click.option('--device-id', required=True, type=str, help="Error: --device-id is required")
@click.option('--event-type', required=True, type=click.Choice(['deposit', 'heartbeat']), help="Error: --event-type is required")
@click.option('--count', required=True, type=int, help="Error: --count is required")
@click.option('--interval', required=True, type=float, help="Error: --interval is required")
@click.option('--out', 'out_path', required=True, type=click.Path(), help="Error: --out path is required")
@click.option('--starting-total', type=int, default=0)
@click.option('--verbose', is_flag=True)
def generate_events(device_id, event_type, count, interval, out_path, starting_total, verbose):

    if count <= 0:
        click.echo("Error: --count must be > 0", err=True)
        sys.exit(2)
        
    if interval < 0:
        click.echo("Error: --interval must be >= 0", err=True)
        sys.exit(2)

    run_id = str(uuid.uuid4())
    written = 0
    deposit_total = starting_total

    try:
        with open(out_path, "a", encoding="utf-8") as f:
            for seq in range(1, count + 1):
                now = utc_now_iso()
                
                record = {
                    "event_time": now,
                    "ingest_time": now,
                    "device_id": device_id,
                    "event_type": event_type,
                    "seq": seq,
                    "run_id": run_id
                }

                if event_type == "deposit":
                    deposit_total += 1
                    record["deposit_delta"] = 1
                    record["deposit_total"] = deposit_total
                elif event_type == "heartbeat":
                    record["status"] = "online"

                f.write(json.dumps(record) + "\n")
                f.flush()
                written += 1

                if verbose and seq % 5 == 0:
                    click.echo(f"generated seq={seq} type={event_type} out={out_path}")

                if interval > 0 and seq < count:
                    time.sleep(interval)
                    
    except KeyboardInterrupt:
        click.echo(f"\nInterrupted. Wrote {written} record(s).")
        sys.exit(0)
        
    except Exception as e:
        click.echo(f"Runtime error: {e}", err=True)
        sys.exit(1)

if __name__ == '__main__':
    generate_events()
