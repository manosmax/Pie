# Team 8: Report LAB 2

**Team Members:**
* **Anastasios Kanellopoulos**
* **Pasamihalis Emmanouil**
* **Giakoumakis Emmanouil**

---

# Section A 
# PIR Event Logger

A Raspberry Pi PIR motion sensor logger that writes structured JSONL events to disk.


---

## Project layout

```
.
pir_event_logger.py      
pir_print.py 
└── pirlib/
    ├── __init__.py
    ├── sampler.py       
    └── interpreter.py      
```

---

## Requirements

| Requirement | Version |
|---|---|
| Python | 3.10 + |
| RPi.GPIO | 0.7 +|
---

## 1 — Create and activate a virtual environment

```bash
# create
python3 -m venv .venv --system-site-packages

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
pip install -r requirements.txt
```


---

## 3 — Wire the sensor *(Raspberry Pi only)*

| Sensor Pin | Pi pin (physical) | Pi name (BCM)   | Why |
|------------|-------------------|-----------------|-----|
| `VCC`        | 2                 | 5V|power|
| `GND`        | 6                 | GND|reference|
| `OUT`        | 11                | GPIO17|input signal|

---

## 4 — Run the logger

### Minimal (uses all defaults)

```bash
python pir_event_logger.py --device-id pir-01 --pin 17
```

### Full example

```bash
python pir_event_logger.py \
  --device-id      pir-01              \
  --pin            17                 \
  --sample-interval 0.1               \
  --cooldown       5                   \
  --min-high       0.2                 \
  --duration       60                  \
  --out            motion_events.jsonl \
  --verbose
```

### All CLI flags

| Flag | Type | Default               | Description |
|---|---|-----------------------|---|
| `--device-id` | str | *(required)*          | Identifier embedded in every record |
| `--pin` | int | `17`                  | BCM GPIO pin number |
| `--sample-interval` | float | `0.1`                 | Seconds between sensor reads |
| `--cooldown` | float | `5.0`                 | Min seconds between emitted events |
| `--min-high` | float | `0.0`                 | Min seconds signal must stay HIGH to count |
| `--duration` | float | `30.0`                | Total run time in seconds (`0` = run until Ctrl-C) |
| `--out` | str | `motion_events.jsonl` | Output file (append-only) |
| `--verbose` / `-v` | flag | off                   | Print each event to stdout |

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


## 6 — Anti-spam / filtering techniques

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


## 7 — Deactivate the virtual environment

```bash
deactivate
```

  

# Section B 

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
Motion Detected 

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
We used 0.1s which is an ideal middle point between too much data and possible fast events going undetected. 

**RQ15: What cooldown did you choose and why?**
We used a cooldown of 2s which is enough time for someone to pass away from the reach of the sensor 

**RQ16: Did you observe brief spikes? What min_high did you choose (or why did you keep it 0)?**
Min_high is the minimum duration of a high state that is required in order to register as an object. Using 0.2 we observed a lot of noise which was fixed by increasing it to 0.5. 

**RQ17: Compute and report latency for 3 records.**
The latency for the 3 records is the following : 0.021, 0.039, 0.019. The average is about 25ms 

**RQ18: In your own words, explain how your interpreter prevents “motion detected” spam.** (FIX)
The interpreter uses a flag that locks after the first event is emitted on a rising edge, preventing any further events from being written no matter how long the signal stays `HIGH`.It only resets when the signal falls `LOW` and rises again. Before any event is even considered, it is ensured the signal has been continuously `HIGH` long enough to rule out glitches and warm-up spikes. Finally, a cooldown timer records the last emission time and suppresses any new event that arrives before the minimum gap has elapsed, mirroring the PIR's own hardware reset behaviour.



**RQ19: Show a short output snippet of pir_print.py**
[print] pin=17 interval=0.1s cooldown=5.0s min_high=0.2s
t=   0.20s motion_detected
t=  14.31s motion_detected
t=  44.63s motion_detected


**RQ20: Show a short output snippet of pir_event_logger.py**
t=  14.21s  seq=0001  event_time=2026-03-06T12:38:40.247Z  latency=0.021 ms
t=  19.32s  seq=0002  event_time=2026-03-06T12:38:45.352Z  latency=0.039 ms
t=  25.02s  seq=0003  event_time=2026-03-06T12:38:51.057Z  latency=0.019 ms
t=  39.93s  seq=0004  event_time=2026-03-06T12:39:05.967Z  latency=0.017 ms
t= 134.11s  seq=0005  event_time=2026-03-06T12:40:40.141Z  latency=0.017 ms
t= 149.12s  seq=0006  event_time=2026-03-06T12:40:55.154Z  latency=0.027 ms
t= 157.23s  seq=0007  event_time=2026-03-06T12:41:03.261Z  latency=0.015 ms
t= 163.33s  seq=0008  event_time=2026-03-06T12:41:09.367Z  latency=0.031 ms
t= 168.94s  seq=0009  event_time=2026-03-06T12:41:14.972Z  latency=0.022 ms
t= 176.84s  seq=0010  event_time=2026-03-06T12:41:22.878Z  latency=0.025 ms
t= 182.55s  seq=0011  event_time=2026-03-06T12:41:28.582Z  latency=0.013 ms
t= 188.25s  seq=0012  event_time=2026-03-06T12:41:34.286Z  latency=0.014 ms
t= 194.26s  seq=0013  event_time=2026-03-06T12:41:40.291Z  latency=0.021 ms

---

## Part F — GitHub Projects Kanban Board (in your repo): what it is, why we use it, and exactly how to do it


**RQ21: Provide a screenshot of your board .**
<img width="1779" height="1079" alt="image" src="https://github.com/user-attachments/assets/11ffc301-00d8-41cb-bce8-115b419c8fb2" />


**RQ22: Give one concrete example of how the board can prevent a coordination bug (e.g., wrong pin, duplicated work, missed experiment).**
After having the "Smoke Test Works" issue on our board, each member of the team knows that the functionality of the wiring and the motion detector is in order and working as intended, so there is no need for repeating the test again (duplicated work).

**RQ23: Which card can be a “critical path” blocker for your team, and why?**
A critical path blocker is a task that must be completed before other tasks can proceed. If it is delayed, then our team can not continue with the rest of the project. We believe that the "Smoke Test Works" is a critical path blocker as we can not continue with out project if we do not verify first that the wiring and the motion detection is working.


