# Section A 
# PIR Event Logger

A Raspberry Pi PIR motion sensor logger that writes structured JSONL events to disk.
Built around a clean two-layer pipeline — `PirSampler` reads the raw GPIO pin,
`PirInterpreter` applies anti-spam / filtering logic, and `pir_event_logger.py`
owns the polling loop, CLI, and file I/O.

---

## Project layout

```
.
├── pir_event_logger.py       # main entry point — CLI + polling loop + JSONL writer
└── pirlib/
    ├── __init__.py
    ├── sampler.py            # PirSampler  – GPIO / simulation abstraction
    └── interpreter.py        # PirInterpreter – anti-spam + semantic events
```

---

## Requirements

| Requirement | Version |
|---|---|
| Python | 3.10 + |
| RPi.GPIO | 0.7 + *(Raspberry Pi only)* |

On a development machine (Linux / macOS / Windows) `RPi.GPIO` is not needed —
the sampler automatically falls back to a built-in simulator.

---

## 1 — Create and activate a virtual environment

```bash
# create
python3 -m venv .venv

# activate — Linux / macOS
source .venv/bin/activate

# activate — Windows (PowerShell)
.venv\Scripts\Activate.ps1
```

Your prompt will show `(.venv)` when the environment is active.
All `pip install` commands below install only into this environment,
not system-wide.

---

## 2 — Install dependencies

**On a Raspberry Pi** (real hardware):

```bash
pip install --upgrade pip
pip install RPi.GPIO
```

**On any other machine** (simulation mode, no GPIO needed):

```bash
pip install --upgrade pip
# no extra packages required — stdlib only
```

To freeze a reproducible snapshot for later:

```bash
pip freeze > requirements.txt
```

And restore it on another machine:

```bash
pip install -r requirements.txt
```

---

## 3 — Wire the sensor *(Raspberry Pi only)*

| PIR pin | Pi header pin | Notes |
|---|---|---|
| VCC | Pin 2 (5 V) | some modules accept 3.3 V — check datasheet |
| GND | Pin 6 (GND) | |
| OUT | Pin 12 (BCM 18) | default; change with `--pin` |

> **BCM numbering** is used throughout. `--pin 18` refers to BCM GPIO 18,
> not physical pin 18.

---

## 4 — Run the logger

### Minimal (uses all defaults)

```bash
python pir_event_logger.py --device-id pir-01 --pin 18
```

### Full example

```bash
python pir_event_logger.py \
  --device-id      pir-01              \
  --pin            18                  \
  --sample-interval 0.1               \
  --cooldown       5                   \
  --min-high       0.2                 \
  --duration       60                  \
  --out            motion_events.jsonl \
  --verbose
```

### All CLI flags

| Flag | Type | Default | Description |
|---|---|---|---|
| `--device-id` | str | *(required)* | Identifier embedded in every record |
| `--pin` | int | `18` | BCM GPIO pin number |
| `--sample-interval` | float | `0.1` | Seconds between sensor reads |
| `--cooldown` | float | `5.0` | Min seconds between emitted events |
| `--min-high` | float | `0.0` | Min seconds signal must stay HIGH to count |
| `--duration` | float | `30.0` | Total run time in seconds (`0` = run until Ctrl-C) |
| `--out` | str | `motion_events.jsonl` | Output file (append-only) |
| `--verbose` / `-v` | flag | off | Print each event to stdout |

### Exit codes

| Code | Meaning |
|---|---|
| `0` | Clean stop (duration elapsed or Ctrl-C) |
| `1` | Runtime error (GPIO init failed, file I/O error) |
| `2` | Usage error (bad argument value) |

---

## 5 — Output format

Events are written one JSON object per line (JSONL / ndjson), appended to
`--out`. The file is flushed after every write so partial runs are never lost.

**Example record (pretty-printed):**

```json
{
  "seq":               1,
  "run_id":            "cd2bbc20-f0a0-4e79-ae52-2192978d78b1",
  "device_id":         "pir-01",
  "event_type":        "motion",
  "motion_state":      "detected",
  "event_time":        "2026-03-06T11:51:23.060Z",
  "ingest_time":       "2026-03-06T11:51:23.061Z",
  "latency_ms":        0.12,
  "pin":               18,
  "sample_interval_s": 0.1,
  "cooldown_s":        5.0,
  "min_high_s":        0.2
}
```

**Field reference:**

| Field | Description |
|---|---|
| `seq` | Per-run sequence number, starting at 1 |
| `run_id` | UUID4 unique to this invocation |
| `device_id` | Value of `--device-id` |
| `event_type` | Always `"motion"` |
| `motion_state` | Always `"detected"` |
| `event_time` | UTC ISO-8601 — when the motion was detected |
| `ingest_time` | UTC ISO-8601 — when the record was written |
| `latency_ms` | `ingest_time − event_time` in milliseconds |
| `pin` | BCM pin used |
| `sample_interval_s` | Configured sample interval |
| `cooldown_s` | Configured cooldown |
| `min_high_s` | Configured min-high filter |

---

## 6 — Interpreting the log

Quick one-liner to pretty-print all events:

```bash
cat motion_events.jsonl | python3 -m json.tool
```

Count total events in a run:

```bash
grep -c '"event_type"' motion_events.jsonl
```

Filter by `run_id`:

```bash
grep "cd2bbc20" motion_events.jsonl | python3 -m json.tool
```

Compute average latency with Python:

```python
import json, statistics

with open("motion_events.jsonl") as f:
    records = [json.loads(line) for line in f]

latencies = [r["latency_ms"] for r in records]
print(f"avg latency: {statistics.mean(latencies):.3f} ms")
print(f"max latency: {max(latencies):.3f} ms")
```

---

## 7 — Anti-spam / filtering techniques

The `PirInterpreter` inside `pirlib/interpreter.py` applies five techniques
on every raw sample before an event is ever written to disk:

| # | Technique | CLI flag | What it does |
|---|---|---|---|
| E.2.1 | Sampling rate | `--sample-interval` | Controls how often the pin is read. Too slow → miss short pulses; too fast → CPU waste and noise. |
| E.2.2 | once-per-high | *(always on)* | Emits **exactly one** event per HIGH window, no matter how long the signal stays HIGH. |
| E.2.3 | Cooldown | `--cooldown` | After an event is emitted, ignores new detections for this many seconds. Mirrors the PIR hardware reset (~5–6 s). |
| E.2.4 | min-high filter | `--min-high` | Discards spikes shorter than this duration. Filters sensor warm-up glitches. |
| E.2.5 | Dual timestamps | *(always on)* | Every record stores both `event_time` and `ingest_time`; `latency_ms` is computed automatically. |

---

## 8 — Simulation mode

When `RPi.GPIO` is not installed the sampler silently switches to a built-in
simulator that generates a repeating waveform:

```
|← 4 s LOW →|← 2 s HIGH →|← 4 s LOW →| ...
```

This lets you develop, test, and inspect output on any machine without
touching real hardware. The exact same `pir_event_logger.py` command works
in both modes — no code changes needed.

---

## 9 — Deactivate the virtual environment

```bash
deactivate
```

---

## Troubleshooting

**`ModuleNotFoundError: No module named 'pirlib'`**
Run the script from the project root (the directory that contains the
`pirlib/` folder), or add the root to `PYTHONPATH`:

```bash
export PYTHONPATH=$(pwd)
python pir_event_logger.py --device-id pir-01 --pin 18
```

**`RuntimeError: Not running on a RPi!`**
`RPi.GPIO` is installed but the kernel module is not loaded (common in
Docker / WSL). Either run on real hardware or uninstall `RPi.GPIO` to let
the auto-simulator take over.

**Events are never written**
- Increase `--duration` or remove it (`0` = unlimited).
- Lower `--min-high` — a value larger than your `--sample-interval` may filter
  every pulse on a noisy setup.
- Lower `--cooldown` for rapid-fire testing.
- Use `--verbose` to see live status and confirm the loop is running.


# Section B 
**RQ0: What is the commit hash of your final “end-of-lab” commit for Lab 01?**
The final commit hash, before this update is the following : 05e15202680a32edbde8939962c854a6412d6f5d

---

##  Part A - Understanding the sensor device

**RQ1: Is a PIR sensor active or passive? Contact or no-contact? Explain in your own words.**
The PIR sensor is passive because it does not emit its own energy to scan object. Also it is no-contact because it operates through optical sensor. 

**RQ2: What is the output range/representation of this sensor?**
The output is range is 0-3.3 Volts. The **LOW** range is for when no motion is detected and the **HIGH** range is for when motion is detected.

**RQ3: If TIME is set to 300s, what wrong assumption might your software make about “continuous motion”?**
If an object passes quickly the sensor won't be able to detect the IR signal.

**RQ4: Why does warm-up time matter in real deployments?**
Because it needs time to acclimatize to the room IR level.



---

## Part B — Raspberry Pi GPIO basics (what you are controlling, which pins to use, and why)

**RQ5: Explain a realistic bug that happens when a team mixes BCM and BOARD numbering.**
A signal might me misinterpreted because a team read the pin using onother numbering method.

---
## Part C — Wiring the PIR sensor (step-by-step) and verifying hardware

**RQ6: Fill in the wiring table for your setup (use your actual pins).**

| Sensor Pin | Pi pin (physical) | Pi name (BCM)   | Why |
|------------|-------------------|-----------------|-----|
| `VCC`        | 2                 | 5V|power|
| `GND`        | 6                 | GND|reference|
| `OUT`        | 11                | GPIO17|input signal|

**RQ7: Which GPIO pin did you select (BCM) and why?**
We used the 11th pin (`GPIO17`) because it was the closest to the rest of our wiring and the best option for the sensor connectivity.

**RQ8: Paste the command you ran for the smoke test and a short snippet of output.**
`Input:`python pir_smoke_test.py
`Output:`
Motion stopped \
Motion Detected \
Motion stopped \
Motion Detected \
Motion stopped \
Motion Detected \

**RQ9: With TIME at minimum, approximately how long did OUT remain HIGH after motion?**
With TIME at minimum it took half a second to go from `Motion Detected` to `Motion Stopped`.

**RQ10: With TIME at maximum, approximately how long did OUT remain HIGH after motion?**
With TIME at maximum it took half a second to go from `Motion Detected` to `Motion Stopped`.

**RQ11: What was the maximum distance at which you reliably triggered motion at low sensitivity vs high sensitivity?**
We could not fully see the capabilities of the sensor but after going 3 meters away the sensor could not detect motion at low sensitivity and at high sensitivity the sensor worked after 5 meters away.

**RQ12: Describe the observed difference between H and L mode in your own words (based on your experiment).**
On `L` mode once the sensor is triggered it stays HIGH for a timer cycle, on `H` mode if additional action is detected while the output is high the timer resets and starts again.

---
## Part D — Software setup

**RQ13: Paste your sys.executable output and explain how it proves you are using the venv.**
```bash
(venv) iotlab_upat_8@iotlab-Upat-8:~/programs/Pie/labs/lab02 $ python -c "import sys; print(sys.executable)"
/home/iotlab_upat_8/programs/Pie/labs/lab02/venv/bin/python
```
At the start of the command we see `(venv)` and also the path has `/venv` in the name.

---

## Part E — From “signal” to “event” (core programming)

**RQ14: What sample interval did you choose and why? (Use your knob experiments to justify it.)**

**RQ15: What cooldown did you choose and why?**

**RQ16: Did you observe brief spikes? What min_high did you choose (or why did you keep it 0)?**

**RQ17: Compute and report latency for 3 records.**

**RQ18: In your own words, explain how your interpreter prevents “motion detected” spam.**

**RQ19: Show a short output snippet of pir_print.py**

**RQ20: Show a short output snippet of pir_event_logger.py**

---

## Part F — GitHub Projects Kanban Board (in your repo): what it is, why we use it, and exactly how to do it


**RQ21: Provide a screenshot of your board .**
<img width="1779" height="1079" alt="image" src="https://github.com/user-attachments/assets/11ffc301-00d8-41cb-bce8-115b419c8fb2" />


**RQ22: Give one concrete example of how the board can prevent a coordination bug (e.g., wrong pin, duplicated work, missed experiment).**
After having the "Smoke Test Works" issue on our board, each member of the team knows that the functionality of the wiring and the motion detector is in order and working as intended, so there is no need for repeating the test again (duplicated work).

**RQ23: Which card can be a “critical path” blocker for your team, and why?**
A critical path blocker is a task that must be completed before other tasks can proceed. If it is delayed, then our team can not continue with the rest of the project. We believe that the "Smoke Test Works" is a critical path blocker as we can not continue with out project if we do not verify first that the wiring and the motion detection is working.


