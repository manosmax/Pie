import time, argparse
from pirlib.sampler import PirSampler
from pirlib.interpreter import PirInterpreter

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--pin", type=int, required=True)
    p.add_argument("--sample-interval", type=float, default=0.1)
    p.add_argument("--cooldown", type=float, default=0.0)
    p.add_argument("--min-high", type=float, default=0.0)
    p.add_argument("--duration", type=float, default=30.0)
    args = p.parse_args()

    sampler = PirSampler(args.pin)
    interp = PirInterpreter(cooldown_s=args.cooldown, min_high_s=args.min_high)

    t0 = time.time()
    end = t0 + args.duration

    print(f"[print] pin={args.pin} interval={args.sample_interval}s cooldown={args.cooldown}s min_high={args.min_high}s")

    try:
        while time.time() < end:
            now = time.time()
            raw = sampler.read()
            for ev in interp.update(raw, now):
                print(f"t={ev['t']-t0:7.2f}s {ev['kind']}")
            time.sleep(args.sample_interval)
    except KeyboardInterrupt:
        print("\n[print] Ctrl-C: exit.")

if __name__ == "__main__":
    main()
