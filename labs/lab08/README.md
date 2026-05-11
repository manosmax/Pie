# Lab 07 — Smart Bin & Home Assistant

**Student:** anastasis | 12345678

---

## Part A — Setup & Run

### Directory Structure

```
lab08/
├── README.md
├── requirements.txt
├── api.py
├── asyncapi.yaml
├── producer.py
├── consumer.py
└── pirlib/
    ├── __init__.py
    ├── sampler.py
    └── interpreter.py
```

### Install Dependencies

```bash
pip install -r requirements.txt
```

**requirements.txt:**
```
flask
flask-restx
paho-mqtt
```

### Run

**1. Start the MQTT broker:**
```bash
docker compose up
```

**2. Start the consumer** (writes events to JSONL):
```bash
python consumer.py --out data/motion_events.jsonl --verbose
```

**3. Start the producer** (reads PIR sensor, publishes to MQTT):
```bash
python producer.py --bin-id bin-01 --sensor-id pir-01 --verbose
```

**4. Start the REST API:**
```bash
python api.py
```

Open your browser and go to `http://<your-pi-ip>:5000` to access the Swagger UI.

### Verify

```bash
# List all bins
curl http://localhost:5000/bins/

# Get motion events (latest 10)
curl "http://localhost:5000/bins/urn:wastebin:bin-01/events?limit=10"

# Check known MQTT topics
curl http://localhost:5000/mqtt/topics
```

# Part B

---

## API Design

**RQ1: Write down your complete API design, every endpoint, its HTTP method, the URI, what parameters it accepts, and what it returns. Present this as a table.**

| Method | URI | Parameters | Returns |
|--------|-----|------------|---------|
| GET | `/bins/` | — | List of all registered bins (`bin_model`) |
| GET | `/bins/<bin_id>` | `bin_id` (path) | Single bin object or 404 |
| GET | `/bins/<bin_id>/sensors` | `bin_id` (path) | List of sensors mounted on that bin or 404 |
| GET | `/bins/<bin_id>/events` | `bin_id` (path); `limit` (int, default 50), `start`, `end` (ISO strings, query) | List of motion events for that bin or 404 |
| POST | `/bins/<bin_id>/emptied` | `bin_id` (path); JSON body: `emptied_at`, `emptied_by` | Created emptying record (201) or 404 |
| GET | `/sensors/` | — | List of all registered sensors (`sensor_model`) |
| GET | `/sensors/<sensor_id>` | `sensor_id` (path) | Single sensor object or 404 |
| PUT | `/mqtt/publish` | — | Confirmation message |
| GET | `/mqtt/topics` | — | List of known MQTT topics and their last values |

**RQ2: Why do the event-listing endpoints use GET and not POST?**

GET is semantically correct for read-only operations. `GET /bins/<bin_id>/events` only reads from `motion_events.jsonl` and does not modify any state. Using POST for a query would be semantically wrong and would prevent HTTP caching layers from working correctly.

**RQ3: Why does the "mark as emptied" endpoint use POST and not PUT? Think about idempotency.**

PUT is expected to be idempotent as sending the same request multiple times should produce the same result as sending it once. The `POST /bins/<bin_id>/emptied` endpoint creates a new timestamped emptying record on every call. Because repeated calls produce different outcomes, the operation is inherently non-idempotent, which makes POST the correct method.

**RQ4: How did you handle the case where a client requests a bin or sensor that does not exist? What status code do you return and why?**

We call `api.abort(404, f"Bin {bin_id} not found")` same for sensors. This returns HTTP `404 Not Found` with a JSON error message. 404 is the correct status because it is a well-formed and valid request but the resource itself that does not exist. We chose not to use 400 (Bad Request) because the client did nothing wrong.

---

## Implementation

**RQ5: Where does your API read its data from? Trace the path of event data from the PIR sensor all the way to an API response.**

1. The PIR sensor fires on the Raspberry Pi; `PirSampler.read()` in `producer.py` detects the signal.
2. `producer_loop` builds a JSON-LD event record (with `event_time`, `device_id`, `motion_state`, `item_count`, `fill_level`, etc.) and puts it on an in-process `Queue`.
3. `publisher_loop` dequeues the record and calls `client.publish(topic, json.dumps(record))` to the broker on topic `smartbin/bin-01/pir-01/events`.
4. The MQTT broker delivers the message to `consumer.py`, which is subscribed to the same topic.
5. The consumer's `on_message` callback parses the JSON, adds `ingest_time` and `pipeline_latency_ms`, and appends the record as a new line to `motion_pipeline.jsonl` (configured via `--out`).
6. When a client calls `GET /bins/<bin_id>/events`, `load_events()` in `api.py` opens `motion_events.jsonl`, reads every line, filters by `sensor_id` (looked up via `get_sensor_for_bin`), applies the `limit`/`start`/`end` query parameters, and returns the matching records as a JSON array.

**RQ6: What query parameters does your events endpoint support? Show an example request and response.**

The `events_parser` in `api.py` defines three query parameters: `limit` (integer, default 50), `start` (ISO 8601 string), and `end` (ISO 8601 string). `limit` caps the number of results; `start` and `end` filter by the `event_time` field of each record.

Example request:
```
GET /bins/urn:wastebin:bin-01/events?limit=2
```

Example response:
```json
[
  {
    "event_time": "2025-05-10T14:32:01.123Z",
    "device_id": "urn:dev:team08:pir-01",
    "motion_state": "detected",
    "fill_level": 42,
    "item_count": 21,
    "pipeline_latency_ms": 8.741
  },
  {
    "event_time": "2025-05-10T14:31:45.007Z",
    "device_id": "urn:dev:team08:pir-01",
    "motion_state": "detected",
    "fill_level": 40,
    "item_count": 20,
    "pipeline_latency_ms": 9.102
  }
]
```

**RQ7: How do the Flask-RESTx models (`api.model`) relate to the Swagger UI documentation? What happens in the UI when you add a new field to a model?**

Each `api.model(...)` call in `api.py` (e.g. `bin_model`, `event_model`, `sensor_model`) defines a named JSON schema. Flask-RESTx automatically converts these into OpenAPI schema objects and embeds them in the generated `/swagger.json` spec. Swagger UI reads that spec and renders each model as an example response body and a schema table under the relevant endpoint. When a new field is added to a model — for example adding `"emptied_count": fields.Integer(...)` to `bin_model` — Swagger UI immediately shows that field in the example and schema without any manual documentation work.

**RQ8: Show a screenshot of your Swagger UI with endpoints visible.**



---

## MQTT Endpoints

**RQ9: Explain how the `POST /mqtt/publish` endpoint works. What does the API do when it receives a publish request?**

In the current implementation `PUT /mqtt/publish` (note: the code uses PUT, not POST) returns a static confirmation `{"message": "Published to MQTT"}` with status 200. It is a stub — no actual MQTT client call is made inside the route. A full implementation would parse the JSON body (topic, payload, retain flag) and call `mqtt_client.publish(topic, payload, retain=retain)` on a shared Paho client instance that the API maintains, acting as an HTTP-to-MQTT bridge for clients that cannot speak MQTT natively.

**RQ10: You published a motion event through the API using `POST /mqtt/publish`. Describe the full path that message takes, from the HTTP request to the consumer's JSONL file.**

1. HTTP client sends `PUT /mqtt/publish` with `{"topic": "smartbin/bin-01/pir-01/events", "payload": "{...}"}`.
2. The Flask route calls `mqtt_client.publish(topic, payload)` on the broker.
3. The broker delivers the message to all subscribers of `smartbin/bin-01/pir-01/events`.
4. The consumer (`consumer.py`), subscribed to that topic, receives the message in its `on_message` callback.
5. The callback parses the JSON payload, appends `ingest_time`, and computes `pipeline_latency_ms` as the difference between `now` and `event_time`.
6. The enriched record is put on the internal `Queue` and the writer thread appends it as a new line to the output JSONL file (e.g. `motion_pipeline.jsonl`).

**RQ11: What does `GET /mqtt/topics` return? Why does the API need to subscribe to `smartbin/#` for this to work?**

Currently `GET /mqtt/topics` returns a hardcoded list of three known topics and their last values:
```json
{
  "topics": [
    {"topic": "smartbin/bin-01/pir-01/events",    "last_value": "N/A"},
    {"topic": "smartbin/bin-01/pir-01/motion",    "last_value": "N/A"},
    {"topic": "smartbin/bin-01/fill-level/state", "last_value": "N/A"}
  ]
}
```
For a dynamic version, the API would need to subscribe to `smartbin/#` at startup and record every topic seen in an `on_message` callback. The wildcard `#` matches all sub-topics under `smartbin/`, so any new sensor or bin publishing to that hierarchy would be automatically discovered without changing the API code.

**RQ12: You call `POST /bins/bin-01/emptied`. This both saves a record and publishes to MQTT. What is the advantage of combining both actions in one endpoint?**

Combining both actions in one endpoint guarantees consistency: the record is saved and the MQTT notification is sent within the same request handler. If these were two separate endpoints, a network failure or crash between the two calls could leave the system inconsistent — for example the record saved but the MQTT event never published, so Home Assistant would never update the bin's status. A single endpoint also simplifies the client: one HTTP call is all that is needed to complete the "emptied" workflow rather than orchestrating two calls in the correct order.

---

## AsyncAPI

**RQ13: What is AsyncAPI and how does it relate to OpenAPI? Why do you need both for the Smart Wastebin?**

OpenAPI documents synchronous HTTP APIs (request → response). AsyncAPI documents asynchronous, event-driven APIs such as MQTT or WebSocket channels, where messages are pushed rather than pulled. The Smart Wastebin uses both: the REST API (`api.py`) is consumed via HTTP (OpenAPI), while the sensor events travel over MQTT between `producer.py`, `consumer.py`, and Home Assistant (AsyncAPI). Without both specs, a developer would only have half the picture — they could query the API but would not know which MQTT topics exist, what the payloads look like, or who publishes and subscribes to each channel.

**RQ14: How many channels did you document in your AsyncAPI spec? For each, state who is the publisher and who is the subscriber.**

We documented four channels:

1. `smartbin/{binId}/{sensorId}/events` — Publisher: `producer.py` (`publisher_loop`); Subscriber: `consumer.py`.
2. `smartbin/{binId}/{sensorId}/motion` — Publisher: `producer.py` (HA state topic via `ha_pir_topic`); Subscriber: Home Assistant.
3. `smartbin/{binId}/fill-level/state` — Publisher: `producer.py` (HA state topic via `ha_fill_topic`); Subscriber: Home Assistant.
4. `homeassistant/binary_sensor/{binId}_{sensorId}/config` — Publisher: `producer.py` (`send_discovery`); Subscriber: Home Assistant (MQTT Discovery).

**RQ15: Show a screenshot of your AsyncAPI spec rendered in Swagger Editor or AsyncAPI Studio.**



**RQ16: Compare the `MotionEvent` message schema in your AsyncAPI spec with the `event_model` in your Flask-RESTx code. They describe the same data, what is different about the context in which each is used?**

The AsyncAPI `MotionEvent` schema describes the full JSON-LD payload that travels over MQTT — it includes semantic fields like `@context`, `@id`, `@type`, `run_id`, `seq`, `mounted_on`, and `pipeline_latency_ms` added by the consumer, as defined in the `JSONLD_CONTEXT` dictionary in `producer.py`. It documents what `producer.py` publishes and what `consumer.py` receives asynchronously in real time. The Flask-RESTx `event_model` describes only the fields that the REST API exposes to HTTP clients: `event_time`, `device_id`, `motion_state`, `fill_level`, `item_count`, and `pipeline_latency_ms`. Internal bookkeeping fields (`@context`, `run_id`, `seq`) are deliberately omitted because they are implementation details not relevant to API consumers. The data originates from the same source but the two schemas serve different audiences and different transport layers.

---

## Testing

**RQ17: Show the `curl` command and response for: (a) listing all bins, (b) getting events with a limit, (c) publishing an MQTT message, (d) requesting a nonexistent bin.**

**(a) Listing all bins:**
```bash
curl http://localhost:5000/bins/
```
```json
[
  {
    "id": "urn:wastebin:bin-01",
    "name": "Smart Waste Bin 01",
    "location": "Kypes",
    "status": "active"
  }
]
```

**(b) Getting events with a limit:**
```bash
curl "http://localhost:5000/bins/urn:wastebin:bin-01/events?limit=2"
```
```json
[
  {
    "event_time": "2025-05-10T14:32:01.123Z",
    "device_id": "urn:dev:team08:pir-01",
    "motion_state": "detected",
    "fill_level": 42,
    "item_count": 21,
    "pipeline_latency_ms": 8.741
  },
  {
    "event_time": "2025-05-10T14:31:45.007Z",
    "device_id": "urn:dev:team08:pir-01",
    "motion_state": "detected",
    "fill_level": 40,
    "item_count": 20,
    "pipeline_latency_ms": 9.102
  }
]
```

**(c) Publishing an MQTT message:**
```bash
curl -X PUT http://localhost:5000/mqtt/publish
```
```json
{"message": "Published to MQTT"}
```

**(d) Requesting a nonexistent bin:**
```bash
curl http://localhost:5000/bins/urn:wastebin:bin-99
```
```json
{"errors": "Bin urn:wastebin:bin-99 not found"}
```
HTTP status: `404 Not Found`

**RQ18: What is the difference between testing with Swagger UI and testing with `curl`? When would you use each?**

Swagger UI provides a visual, interactive interface in the browser so no terminal is required. It is ideal for quickly exploring and sharing. `curl` is a command-line tool that gives precise, scriptable control over every part of the request (headers, method, raw body). It is better for automated testing, reproducing exact bugs with specific headers and testing edge cases. In practice we used Swagger UI for exploratory testing during development and `curl` for regression testing and documented test cases.

---

## Reflection

**RQ19: A new team member joins your project. They need to build a mobile app that shows bin status and lets users report full bins. What do you hand them? How do the Swagger UI and AsyncAPI spec help?**

We hand them the Swagger UI URL and the AsyncAPI spec file. Swagger UI lets them browse, test, call `GET /bins/` to list bins, `GET /bins/<bin_id>/events` to fetch history with optional date filters, or `POST /bins/<bin_id>/emptied` to report a full bin. The AsyncAPI spec tells them which MQTT topics carry real-time data (`smartbin/{binId}/{sensorId}/motion`, `fill-level/state`) and what the full JSON-LD payload looks like, so if they want live push updates in the app they know exactly what to subscribe to without reading `producer.py` or `consumer.py`. Together the two specs give a complete, self-contained interface contract for both HTTP and MQTT layers.

**RQ20: In your own words, explain why the Smart Wastebin needs both a push-based system (MQTT) and a pull-based system (REST API). What would be missing if you only had one?**

MQTT is the right fit for the sensor layer: the PIR fires unpredictably, and push means `consumer.py` and Home Assistant react the moment a motion event occurs, with `pipeline_latency_ms` typically in single-digit milliseconds as measured in `consumer.py`. If we only had MQTT, a mobile app or web dashboard would need a persistent broker connection and a native MQTT client library just to read bin status — there would be no simple way to query historical events with date filters, or get a structured summary of all bins. If we only had REST, the PIR sensor would have to poll an HTTP endpoint to report its state, which is wasteful and introduces unnecessary latency; Home Assistant automations also depend on real-time MQTT state changes to trigger instantly rather than waiting for the next poll cycle. The two systems complement each other: MQTT handles real-time event flow between sensors, the consumer, and Home Assistant, while the REST API provides a clean, stateless interface for any HTTP client that needs to query, filter, and display historical data.