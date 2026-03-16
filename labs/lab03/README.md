# Team 8: Report LAB 3

**Team Members:**
* **Anastasios Kanellopoulos**
* **Pasamihalis Emmanouil**
* **Giakoumakis Emmanouil**

---
# Lab 03 — PIR Motion Event Pipeline

A producer-consumer pipeline that separates PIR acquisition from event storage using a bounded queue and two threads.

## Structure

```
lab03/
├── run_pipeline.py       # Main script: queue, threads, CLI, shutdown
├── requirements.txt
└── pirlib/
    ├── __init__.py
    ├── sampler.py        # GPIO read abstraction (stubs on non-Pi)
    └── interpreter.py   # Raw bool → motion events (cooldown + min-high)
```

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
pip install -r requirements.txt
```


# Normal run (60 s, no artificial delay)
python run_pipeline.py \
  --device-id pir-01 \
  --pin 18 \
  --sample-interval 0.1 \
  --cooldown 5.0 \
  --min-high 0.2 \
  --queue-size 100 \
  --consumer-delay 0.0 \
  --duration 60 \
  --out motion_pipeline.jsonl \
  --verbose

# Slow-consumer experiment (simulate overload)
python run_pipeline.py \
  --device-id pir-01 \
  --pin 18 \
  --sample-interval 0.1 \
  --cooldown 5.0 \
  --min-high 0.2 \
  --queue-size 100 \
  --consumer-delay 0.5 \
  --duration 60 \
  --out motion_slow.jsonl \
  --verbose

## Output format (JSONL)

Each line is one JSON object:

```json
{"event_time":"2025-03-10T14:23:01.042Z","device_id":"pir-01","event_type":"motion","motion_state":"detected","seq":1,"run_id":"...","ingest_time":"2025-03-10T14:23:01.043Z","pipeline_latency_ms":1.2}
```

Required fields: `event_time`, `ingest_time`, `device_id`, `event_type`, `motion_state`, `seq`, `run_id`, `pipeline_latency_ms`.

## Key design decisions

| Concern | Choice |
|---|---|
| Backpressure policy | Drop-newest (`put_nowait`, catch `Full`) |
| Queue type | `queue.Queue(maxsize=N)` — bounded, thread-safe |
| Shutdown | `stop_flag` dict; consumer drains queue before exiting |
| Timestamps | UTC millisecond ISO-8601, same helper everywhere |
---

# Section B 

---

**RQ1: Which lecture pipeline phases do you believe you had already implemented in Lab 02?**
From Lab02 we had already implemented data collection and ingestion using intepreter.py. Also we stored data in JSON format. 

**RQ2: Which part of your Lab 02 code did you reuse directly?**
We reused sampler.py and interpreter.py from Lab02

**RQ3: Which part did you have to adapt for the pipeline architecture?**
The interpreter and sampler is thw same from Lab02, we used those differently though. Before the main function ran sequentially inside the loop. Now the processes of consumption and production run asynchronously, while communicating with the queue. We also altered the arguments to fit our programs profile.

**RQ4: In your own words, why is a queue useful between acquisition and writing?**
Using a queue allows us to store data if they are produced faster than they can be consumed. In other words, it prevents data loss if the speed that data is produced is bigger than the speed of consuming it.

**RQ5: What is backpressure?**
Backpressure is when the speed of producing the data is bigger than the speed of consuming it. That puts pressure on the queue which keeps growing until it reaches it's limit. Back pressure policies are then deployed to handle such events.

**RQ6: Why can a slow writer become a data acquisition problem and not just a storage problem?**
If the queue fills up because of a slow writer, there will be dataloss which affects data acquisition. If the writes is slow, we ought to alter data acquisition to collect only limited and necessary information to be abled to be handled by the writer without filling up the queue.

**RQ7: Is your current edge pipeline closer to ETL or ELT? Explain briefly.**
Our current edge pipeline is closer to ETL as we first use interperter.py and enrich our datawith information from run_pipeline.py before storing them as JSON format.

**RQ8: What transformation already happens before your data is written to disk?**
The data is packaged into a structured JSON object with fields like
```JSON
{"event_time": "2026-03-10T10:57:46.318Z", "device_id": "pir-01", "event_type": "motion", "motion_state": "detected", "seq": 4, "run_id": "33dc4166-aa39-4b7c-83c5-f2d5b3fb8ac9", "ingest_time": "2026-03-10T10:57:46.318Z", "pipeline_latency_ms": 0.0}
```

**RQ9: Give one example of a transformation that could be moved later to another stage of the system.**
We can first collect all the data from multiple sensors and then match the data to the sensor at a later stage of the system.

**RQ10: Explain the responsibility of the producer in one sentence.**
The responsibility of the producer is to acquire data from the sensor, enrich it with metadata and place it on the queue.

**RQ11: Explain the responsibility of the consumer in one sentence.**
The responsibility of the consumer is to take data from the queue, transform it, use data for analytics and finally stores then on a JSON file.

**RQ12: Show two example JSONL records from your output and explain their fields briefly.**
```JSON
{"event_time": "2026-03-10T10:40:18.149Z", "device_id": "pir-01", "event_type": "motion", "motion_state": "detected", "seq": 1, "run_id": "8c19aa60-dae2-4580-a528-863c2bc58721", "ingest_time": "2026-03-10T10:40:18.149Z", "pipeline_latency_ms": 0.0}
{"event_time": "2026-03-10T10:57:46.318Z", "device_id": "pir-01", "event_type": "motion", "motion_state": "detected", "seq": 4, "run_id": "33dc4166-aa39-4b7c-83c5-f2d5b3fb8ac9", "ingest_time": "2026-03-10T10:57:46.318Z", "pipeline_latency_ms": 0.0}
```
event_time — when the producer created the record (motion was confirmed)

ingest_time — when the consumer pulled it off the queue

device_id — which sensor produced the event

event_type / motion_state — what kind of event it was

seq — position of this event within the current run, useful for detecting gaps

run_id — UUID shared by all records from one execution of the program

pipeline_latency_ms — time the record spent travelling through the queue

**RQ13: What does pipeline_latency_ms mean in your system?**
It is the time between when the producer acquired the event and when the consumer stored it on the JSON file.

**RQ14: What changed when you introduced --consumer-delay 0.5?**
The queue started filling up as there was delay from processing the produced data.

**RQ15: Did the queue absorb the slowdown? Explain briefly using your own observations** 
Due to us using a big queue of 100 events, the queue managed to absorb the slowdown. 

**RQ16: What is one clear sign, from your terminal status output, that the producer is outrunning the consumer?**
One clear evidence that the proucer is outperforming the consumer is that the max_queue field starts growing unchecked. 

**RQ17: Why is a bounded queue more informative than an unbounded queue during overload?**
Under normal conditions the queue should be able to absorb the bottleneck and not not fill up. An unbounded queue would increase it's size to accomodate the extra data. Thus we would not see dropped events. On a bounded queue, after some time during an overload it would fill up and dropped events would signal the overload. 

**RQ18: Why should status lines stay in the tedrminal instead of being mixed into the JSONL file?**
Status lines are not a type of data the consumer should store. They are not events by themselves. IF we wanted to store them as analytics, they should be stored on a different file. 

**RQ19: Which field lets you group records from the same program execution, and why is that useful?**
The fields `device_id` and `run_id` are relevant on that department. The first signals that the records come from the same device. The second signals that they came from the same instance of a program. 

**RQ20: Why would an unbounded queue be dangerous on a Raspberry Pi?**
An unbounded queue would be dangerous on a Raspberry Pi, because it has a limited amount of storage available for storing data. Filling up that storage completely will cause crashes and data loss.

**RQ21: If you later replaced the JSONL writer with another output component, which part of your system could stay almost unchanged and why?**
The producer reads data from the sensor and has nothing to do with data storage. Thus, it would stay the same. The consumer should be modified a bit to accomodate this change in data type. 


