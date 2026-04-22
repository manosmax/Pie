
## How to Run

### Hardware wiring

| Sensor pin | Pi physical pin | Pi BCM name | Purpose |
|---|---|---|---|
| `VCC` | 2 | 5 V | Power |
| `GND` | 6 | GND | Reference |
| `OUT` | 11 | GPIO 17 | Signal input |

### Install dependencies

```bash
cd labs/lab05
pip install -r requirements.txt
```

### Run the pipeline

```bash
python run_pipeline.py \
  --device-id pir-01 \
  --pin 17 \
  --sample-interval 0.1 \
  --cooldown 5.0 \
  --min-high 0.2 \
  --duration 60 \
  --out motion_pipeline.jsonl \
  --verbose
```

### Parameter reference

| Parameter | Type | Default | Description |
|---|---|---|---|
| `--device-id` | str | `pir-01` | Logical sensor name embedded in every record |
| `--pin` | int | `17` | BCM GPIO pin number |
| `--sample-interval` | float | `0.1` | Seconds between reads (0.1 s = 10 Hz) |
| `--cooldown` | float | `5.0` | Min seconds between emitted events |
| `--min-high` | float | `0.2` | Min seconds signal must stay HIGH before emitting |
| `--queue-size` | int | `100` | Max records the bounded queue can hold |
| `--consumer-delay` | float | `0.0` | Artificial per-record delay in the consumer |
| `--duration` | float | `60.0` | Total run time in seconds (0 = run until Ctrl-C) |
| `--out` | str | `motion_pipeline.jsonl` | Output file path (append mode) |
| `--verbose` / `-v` | flag | off | Print status to stdout every second |


---
## Pipeline Output Format

A pipeline event after the Lab 05 changes:

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
  "ingest_time": "2026-04-06T15:23:05.131Z",
  "pipeline_latency_ms": 0.0
}
```

## Repository Structure

```
/
├── docs/
│   └── ontology.md                  ← Custom term definitions (our namespace)
├── labs/
│   └── lab05/
│       ├── README.md                ← This file
│       ├── models/
│       │   ├── sensor.jsonld        ← HC-SR501 PIR sensor description
│       │   ├── wastebin.jsonld      ← Wastebin entity description
│       │   ├── environment.jsonld   ← Room / deployment space description
│       │   └── context.jsonld       ← Shared @context for pipeline events
│       ├── requirements.txt
│       ├── run_pipeline.py
│       └── pirlib/
│           ├── __init__.py
│           ├── sampler.py
│           └── interpreter.py
```



## Overview

This lab builds on the producer/consumer pipeline from Lab 04. Raw pipeline output such as the record below is not specific. Thus jsonld models are used in order to make every field accurately determined. We solve this by modelling every entity in the system — the **sensor**, the **wastebin** it is mounted on, and the **environment** it is deployed in — as JSON-LD documents.

**Vocabularies used:**

| Prefix | Namespace | Why |
|---|---|---|
| `sosa` | `http://www.w3.org/ns/sosa/` | `Sensor`, `ObservableProperty`, `madeBySensor`, `resultTime` |
| `ssn` | `http://www.w3.org/ns/ssn/` | `hasProperty`, `SystemCapability` |
| `schema` | `https://schema.org/` | `name`, `description`, `manufacturer` |
| `pipeline` | `…/docs/ontology.md#` | `gpioPin`, `cooldownS`, `minHighS`, `sampleIntervalS` |

---

## Entity Diagram

```
Diagram
    ### MODELS

SENSOR {
        string  id                  "urn:dev:team08:pir-01"
        string  type                "sosa:Sensor"
        string  model               "HC-SR501"
        string  observes            "Motiion"
        int     gpioPin             "17"
        int     physicalPin         "11"
        float   sampleIntervalS     "0.1"
        float   cooldownS           "5.0"
        float   minHighS            "0.2"
        string  operatingMode       "repeat-trigger"
        string  status              "active"
    }

    WASTEBIN {
        string  id              "urn:wastebin:bin-01"
        string  type            "sosa:Platform"
        string  name            "Wastebin 01"
        string  material        "plastic"
        string  color           "grey"
        int     heightCm        "18"
        int     diameterCm      "8"
        string  wasteType       "general"
        string  status          "active"
    }

    ENVIRONMENT {
        string  id              "urn:env:kypes"
        string  type            "bot:Space"
        string  name            "Kypes Lab"
        string  building        "basiko"
        string  roomNumber      "02"
        string  trafficLevel    "high"
        string  setting         "indoor"
    }    
    
    ### Relationship summary

    SENSOR      ||--|| WASTEBIN     : "sosa:isHostedBy"
    SENSOR      ||--|| ENVIRONMENT  : "pipeline:deployedIn"
    WASTEBIN    ||--|| ENVIRONMENT  : "pipeline:locatedIn"
    WASTEBIN    ||--|| SENSOR       : "sosa:hosts" 
    ENVIRONMENT ||--|| WASTEBIN     : "pipeline:contains"
    ENVIRONMENT ||--|| SENSOR       : "pipeline:hostsSensors"

``` 



## Custom Ontology Namespace

```
https://github.com/manosmax/Pie/blob/main/docs/Ontology#
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
