## Project Structure

```
pie/labs/lab06
├── src/
│   ├── producer.py        # Reads PIR sensor, publishes events to MQTT
│   ├── consumer.py        # Subscribes to MQTT, writes events to JSONL
│   └── pirlib/            # PIR sensor driver (sampler + interpreter)
├── Dockerfile
├── docker-compose.yml
├── mosquitto.conf
└── requirements.txt
```

---

## Wiring *(Raspberry Pi)*

| Sensor Pin | Pi Physical Pin | BCM Name |
|------------|-----------------|----------|
| `VCC`      | 2               | 5V       |
| `GND`      | 6               | GND      |
| `OUT`      | 11              | GPIO17   |

---

## Build 
```bash 
docker compose build
``` 

## Run with Docker
```bash
# Terminal 1 — MQTT broker
docker compose up mosquitto

# Terminal 2 — PIR producer
docker compose up producer

# Terminal 3 — MQTT consumer
docker compose up consumer
```

Events are saved to `data/motion_events.jsonl`.

``` Bash 
# In order to view the jsonl output with a preetier format run : 
while IFS= read -r line; do echo "$line" | python -m json.tool; echo "---"; done < data/motion_events.jsonl
``` 


To pass custom arguments, override the command in `docker-compose.yml`:

```yaml
producer:
  command: python -u producer.py --verbose --pin 17 --cooldown 2.0 --min-high 0.1
consumer:
  command: python -u consumer.py --verbose --out /app/data/motion_events.jsonl
```

Or run directly without Docker:

```bash
python -m venv .venv --system-site-packages
source .venv/bin/activate
pip install -r requirements.txt

systemctl start mosquitto 

python src/producer.py --pin 17 --cooldown 2.0 --min-high 0.1 --verbose
python src/consumer.py --out data/motion_events.jsonl --verbose
```

| Argument | Default | Description |
|----------|---------|-------------|
| `--pin` | `17` | GPIO BCM pin number |
| `--cooldown` | `5.0` | Seconds between events |
| `--min-high` | `0.2` | Seconds signal must stay HIGH |
| `--duration` | `600.0` | How long to run (seconds) |
| `--host` | `localhost` | MQTT broker host |
| `--port` | `1883` | MQTT broker port |
| `--topic` | `smartbin/bin-01/pir-01/events` | MQTT topic |
| `--qos` | `1` | MQTT QoS level |
| `--out` | `motion_pipeline.jsonl` | Output file (consumer only) |
| `--verbose` | `false` | Print live status |



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
We chose the `smartbin/bin-01/pir-01/events` as we felt it clearly explained what type of data is stored and allows us good naming flexibility for future extensibility, for example `smartbin/bin-02/pir-01/events` or `smartbin/bin-01/pir-02/events`.

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

Our records include an event with the name of the bin and the sensor, that triggered it, as well as the latency of the pipeline and an event timestamp.The latency is higher than it used to be because now the producer and consumer are running independently and they have been decoupled.

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
