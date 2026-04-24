# Lab 06 — Messaging via MQTT

## How to Run

### Hardware wiring

| Sensor pin | Pi physical pin | Pi BCM name | Purpose |
|---|---|---|---|
| `VCC` | 2 | 5 V | Power |
| `GND` | 6 | GND | Reference |
| `OUT` | 11 | GPIO 17 | Signal input |

### Install dependencies

```bash
cd labs/lab06
pip install -r requirements.txt
```

### Start the broker

```bash
sudo systemctl start mosquitto
sudo systemctl enable mosquitto   # auto-start on boot
```

Confirm it is running:

```bash
systemctl status mosquitto
```

You should see `Active: active (running)` on port `1883`.

### Run the consumer

Start the consumer first so it is subscribed before events arrive:

```bash
python consumer.py \
  --broker localhost \
  --port 1883 \
  --topic "smartbin/bin-01/pir-01/events" \
  --qos 1 \
  --out output/events.jsonl \
  --verbose
```

### Run the producer

In a second terminal:

```bash
python producer.py \
  --broker localhost \
  --port 1883 \
  --topic smartbin/bin-01/pir-01/events \
  --device-id pir-01 \
  --pin 17 \
  --sample-interval 0.1 \
  --cooldown 5.0 \
  --min-high 0.2 \
  --qos 1 \
  --verbose
```

### Parameter reference

**producer.py**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `--broker` | str | `localhost` | Hostname or IP of the MQTT broker |
| `--port` | int | `1883` | Broker port |
| `--topic` | str | — | MQTT topic to publish events to |
| `--device-id` | str | `pir-01` | Logical sensor name embedded in every record |
| `--pin` | int | `17` | BCM GPIO pin number |
| `--sample-interval` | float | `0.1` | Seconds between reads (0.1 s = 10 Hz) |
| `--cooldown` | float | `5.0` | Min seconds between emitted events |
| `--min-high` | float | `0.2` | Min seconds signal must stay HIGH before emitting |
| `--qos` | int | `1` | MQTT QoS level (0, 1, or 2) |
| `--verbose` / `-v` | flag | off | Print publish status to stdout |

**consumer.py**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `--broker` | str | `localhost` | Hostname or IP of the MQTT broker |
| `--port` | int | `1883` | Broker port |
| `--topic` | str | — | MQTT topic to subscribe to (wildcards supported) |
| `--qos` | int | `1` | MQTT QoS level (0, 1, or 2) |
| `--out` | str | `motion_events.jsonl` | Output file path (append mode) |
| `--verbose` / `-v` | flag | off | Print received events and metrics to stdout |

---

## Pipeline Output Format

A pipeline event as written by the consumer:

```json
{
  "@context": {
    "@vocab": "https://schema.org/",
    "sosa": "http://www.w3.org/ns/sosa/",
    "ssn": "http://www.w3.org/ns/ssn/",
    "xsd": "http://www.w3.org/2001/XMLSchema#",
    "pipeline": "https://github.com/manosmax/Pie/blob/main/docs/Ontology#",
    "event_time": {
      "@id": "sosa:resultTime",
      "@type": "xsd:dateTime"
    },
    "ingest_time": {
      "@id": "pipeline:ingestTime",
      "@type": "xsd:dateTime"
    },
    "device_id": {
      "@id": "sosa:madeBySensor",
      "@type": "@id"
    },
    "mounted_on": {
      "@id": "sosa:isHostedBy",
      "@type": "@id"
    },
    "event_type": {
      "@id": "sosa:observedProperty",
      "@type": "@id"
    },
    "motion_state": {
      "@id": "sosa:hasSimpleResult",
      "@type": "xsd:string"
    },
    "seq": {
      "@id": "pipeline:sequenceNumber",
      "@type": "xsd:integer"
    },
    "run_id": {
      "@id": "pipeline:runId",
      "@type": "xsd:string"
    },
    "pipeline_latency_ms": {
      "@id": "pipeline:latencyMs",
      "@type": "xsd:decimal"
    }
  },
  "@id": "urn:event:383f7d25-1535-4e05-b8da-90d02daf3601:1",
  "@type": "sosa:Observation",
  "event_time": "2026-04-06T15:23:05.131Z",
  "device_id": "urn:dev:team08:pir-01",
  "event_type": "urn:prop:team08:motion",
  "motion_state": "detected",
  "seq": 1,
  "run_id": "383f7d25-1535-4e05-b8da-90d02daf3601",
  "mounted_on": "urn:wastebin:bin-01",
  "ingest_time": "2026-04-06T15:23:05.148Z",
  "pipeline_latency_ms": 17.3
}
```

---

## Repository Structure

```
/
├── labs/
│   └── lab06/
│       ├── README.md                ← This file
│       ├── requirements.txt
│       ├── producer.py              ← Reads PIR sensor, publishes to MQTT
│       ├── consumer.py              ← Subscribes to MQTT, enriches, writes JSONL
│       └── pirlib/
│           ├── __init__.py
│           ├── sampler.py
│           └── interpreter.py
```

---

## Overview

This lab decouples the producer and consumer from Lab 05 using the **pub/sub pattern**. Instead of two threads sharing a Python `Queue` in the same process, the producer and consumer are now independent scripts that communicate through a **Mosquitto MQTT broker**.

The producer publishes motion events to a topic. The consumer subscribes to that topic and receives them via a callback. The broker sits in between — neither side knows about the other, and they do not need to be running at the same time.

**MQTT concepts used:**

| Concept | What it does |
|---|---|
| **Topic hierarchy** | `/`-separated paths that organise messages (e.g. `smartbin/bin-01/pir-01/events`) |
| **Wildcards** | `+` matches one level; `#` matches any number of levels |
| **QoS 0** | At most once — fire and forget, no acknowledgement |
| **QoS 1** | At least once — acknowledged, may duplicate |
| **QoS 2** | Exactly once — four-step handshake, highest overhead |
| **Retained messages** | Broker stores the last message on a topic; new subscribers receive it immediately |

---

## Topic Structure

```
smartbin/
└── bin-01/
    └── pir-01/
        ├── events      ← motion event records (JSON payload)
        └── status      ← retained online / offline heartbeat
```

**Subscription patterns supported:**

| Pattern | Receives |
|---|---|
| `smartbin/bin-01/pir-01/events` | Events from this sensor only |
| `smartbin/bin-01/#` | All messages from this bin (events + status) |
| `smartbin/+/pir-01/events` | Motion events from pir-01 across all bins |
| `smartbin/#` | Everything — all bins, all sensors, all topics |

**Design rationale:**
The four-level hierarchy `smartbin / bin / sensor / message-type` supports both narrow subscriptions (a single sensor's events) and broad ones (all sensors on a bin, or the same sensor type across all bins) using standard MQTT wildcards. The `status` subtopic is published with the retain flag so any new subscriber learns the sensor's current state without waiting for the next update.

---

## System Architecture

```
┌──────────────────────────────┐        MQTT        ┌─────────────────────────┐
│          producer.py         │ ─── publish ─────▶ │      Mosquitto broker   │
│                              │                     │                         │
│  PIR sampler  →  interpreter │   topic:            │  port 1883              │
│  build record →  serialize   │   smartbin/         │                         │
│  publish JSON                │   bin-01/           └────────────┬────────────┘
└──────────────────────────────┘   pir-01/                        │
                                   events                      subscribe
                                                                   │
                                                      ┌────────────▼────────────┐
                                                      │       consumer.py       │
                                                      │                         │
                                                      │  on_message callback    │
                                                      │  add ingest_time        │
                                                      │  add latency_ms         │
                                                      │  write JSONL            │
                                                      └─────────────────────────┘
```
---

# Part B 

# MQTT fundamentals

**RQ1: What is the role of the MQTT broker? Why don’t we just let the producer and consumer communicate directly (e.g via sockets)?**

An MQTT broker allows for asynchronous communication between the producers and the consumers, adding important feautures such as persistence,routing and protocol conversion. Lastly, it makes infromation easily reusable by other applications that demand it. Wihout a broker the communication between parts of the system could only be synchronous and limited. 

**RQ2: What topic structure did you choose and why? How does it support future extensibility (more sensors, more bins)?**

**RQ3: Explain the difference between QoS 0, 1, and 2 in your own words. Which did you use for your motion events and why?**

QoS 0 does not guarantee anything, meaning the message might arrive on time,late or never. QoS 1, makes sure the message is delivered but can create duplicates, meaning it is not a good application for the Smart-Bin Project as it might make us believe there are more trash in the bin. QoS 2, guarantee the message is recieved and only once, which is the best option if the extra delay added is not a deal breaker. 

**RQ4: What is a retained message? Give one concrete example of when it would be useful for your system.**

A retained message gets stored along with the QoS so it can be sent to a new subscriber when it subscribes after the message. In our system a retained message can be used so any new subscriber will know the total produced events (motion detection after waste dropping)

# Terminal exploration

**RQ5: When you subscribed to smartbin/+/motion, which messages did you receive and which did you not? Explain why, based on how + works.**
 
We received every message adressed to our sensor `("pir-01")` in the subtopic `"motion"`. We did not receive any messages in topics under `"motion"`, because `+` matches only one topic level.

**RQ6: What happened when you subscribed to #? Why is this useful for debugging but dangerous in production?**

Using # is useful when debugging because it allows us to check every topic for any message sent. However in production use cases it can be problematic as it may overwhelm the system and give unnecessary information to the subscribers.

**RQ7: You published a message while no subscriber was connected (without the retain flag). Then you started a subscriber. Did it receive the message? Why or why not?**

We did not receive the message because there was no retain flag so the message was not stored for the new subscriber to read it.

# Pipeline changes
**RQ8: What are the main differences between your run_pipeline.py (threaded queue) and the new producer.py + consumer.py (MQTT)?**

The main difference between the old pipeline and the new pipeline it that the producer and the consumer work independently, allowing them to run from different systems.

**RQ9: In the threaded version, what happened when the queue was full? In the MQTT version, what happens if the consumer is slow or offline?**

In the threaded version if the queue was full the event was stored for a short period of time and then dropped meaning it was lost. In the MQTT version if the consumer is slow or offline it heavily depends on the queue size the broker allows, on the QoS and the flags we have defined. 

**RQ10: How does the callback pattern in paho-mqtt (on_message) differ from the polling pattern you used in the threaded consumer (queue.get(timeout=0.5))?**

The callback pattern is an interrupt event for when a message arrives and is defined in `on_message` function.

**RQ11: Show one example JSON record from the MQTT-based consumer. Is the structure the same as in previous labs? What about pipeline_latency_ms, is it higher or lower? Why?**

# Decoupling experiments

**RQ12: You stopped the consumer and kept the producer running. What happened to the messages published during that time? Were they delivered when the consumer restarted?**

The consumer received only the last message as we set the `RETAIN` flag to `1`.

**RQ13: You ran two consumers on the same topic. Did both receive every message? Why does this matter for building scalable systems?**

Both consumers received the messages. This is extremely important as we can use different topics for different consumers to build large scalable systems, that are efficient and usable by a large number of consumers.

**RQ14: Could you run the producer on one Raspberry Pi and the consumer on a different machine (e.g., your laptop)? What would you need to change?**

We would need to execute code in both machines to establish MQTT and over the internet communication.

# Reflection

**RQ15: In your own words, what does “decoupling” mean in the context of pub/sub? What are the practical benefits?**

In our own words, decoupling in the context of pub/sub means running two processes separately and independently from each other. In this case, the publisher and the subscriber. The benefits are asynchronous communication, flexibility for other applications that want to use information and more features and redundancy than traditional TCP/UDP communication.

**RQ16: If the Mosquitto broker itself crashes, what happens to your system? How could you mitigate this?**

The broker is a single-failure point which is a strong vulnerability in pub/sub systems. We could mitigate this issue by maybe defaulting to another broker or service once a crash or system downtime is detected.
