"""
Smart Wastebin — REST API
================================
Flask-RESTX API that:
  • Reads bin / sensor metadata from JSON-LD model files
  • Reads persisted motion events from JSONL
  • Publishes bin-empty commands to the MQTT broker

FIX: _build_registries() now extracts short IDs (e.g. "bin-01") from full
     URIs (e.g. "urn:wastebin:bin-01") as dict keys, so /bins/bin-01 works.
FIX: get_sensor_for_bin() compares mounted_on URI against the bin's full URI,
     not the short ID, so the cross-reference resolves correctly.
FIX: Removed broken WERKZEUG_RUN_MAIN guard — debug=False means no reloader.
FIX: DATA_DIR and MODELS_DIR paths are resolved relative to __file__ which
     in Docker sits at /app/api.py, giving the correct /app/data and
     /app/models paths.
"""

import json
import os
import paho.mqtt.client as mqtt
import threading
from datetime import datetime, timezone
from flask import Flask
from flask_restx import Api, Resource, fields, reqparse

# ---------------------------------------------------------------------------
# Application & MQTT setup
# ---------------------------------------------------------------------------

app = Flask(__name__)

MQTT_BROKER = os.environ.get("MQTT_BROKER", "mosquitto")
MQTT_PORT   = int(os.environ.get("MQTT_PORT", 1883))

mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, "wastebin-api")

topic_store = {}
topic_lock  = threading.Lock()


def on_message(client, userdata, msg):
    """Store every message received by the API client."""
    with topic_lock:
        topic_store[msg.topic] = {
            "topic":     msg.topic,
            "payload":   msg.payload.decode("utf-8", errors="replace"),
            "qos":       msg.qos,
            "retain":    msg.retain,
            "timestamp": utc_now_iso(),
        }


def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        print("[MQTT] Connected to broker successfully.")
        client.subscribe("smartbin/#", qos=1)
        print("[MQTT] Subscribed to smartbin/#")
    else:
        print(f"[MQTT] Connection failed with code {reason_code}")


def on_disconnect(client, userdata, disconnect_flags, reason_code, properties):
    if reason_code != 0:
        print(f"[MQTT] Unexpected disconnect (rc={reason_code}). Will auto-reconnect...")


mqtt_client.on_message    = on_message
mqtt_client.on_connect    = on_connect
mqtt_client.on_disconnect = on_disconnect

# FIX: removed the broken WERKZEUG_RUN_MAIN guard; debug=False means the
#      reloader never runs, so there is only one process and one MQTT client.
try:
    mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
    mqtt_client.reconnect_delay_set(min_delay=1, max_delay=30)
    mqtt_client.loop_start()
except Exception as e:
    print(f"[MQTT] Initial connection error: {e}")

# ---------------------------------------------------------------------------
# Flask-RESTX
# ---------------------------------------------------------------------------

api = Api(
    app,
    version="1.0",
    title="Smart Wastebin API",
    description="REST API for querying Smart Wastebin sensor data and bin status",
)

ns      = api.namespace("bins",    description="Wastebin operations")
nsensor = api.namespace("sensors", description="Sensor operations")
nmqtt   = api.namespace("mqtt",    description="MQTT operations")

# FIX: paths are now relative to __file__ = /app/api.py in Docker,
#      so these resolve to /app/data and /app/models correctly.
_BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
DATA_DIR     = os.path.join(_BASE_DIR, "data")
MODELS_DIR   = os.path.join(_BASE_DIR, "models")
EVENTS_FILE  = os.path.join(DATA_DIR, "motion_events.jsonl")
EMPTIED_FILE = os.path.join(DATA_DIR, "emptied_records.jsonl")


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------

def load_json(filepath: str) -> dict:
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def load_events(
    filepath: str,
    limit: int | None = None,
    sensor_uri: str | None = None,
) -> list:
    """Load motion events, newest first.

    FIX: filter parameter renamed to sensor_uri to reflect that device_id
         in the JSONL is a full URI (e.g. urn:dev:team08:pir-01), not a
         short ID.
    """
    events = []
    if not os.path.exists(filepath):
        return events
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
                if sensor_uri and record.get("device_id") != sensor_uri:
                    continue
                events.append(record)
            except json.JSONDecodeError:
                continue
    events.reverse()
    return events[:limit] if limit is not None else events


def load_emptied_records(bin_id: str, limit: int | None = None) -> list:
    records = []
    if not os.path.exists(EMPTIED_FILE):
        return records
    with open(EMPTIED_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
                if record.get("bin_id") == bin_id:
                    records.append(record)
            except json.JSONDecodeError:
                continue
    records.reverse()
    return records[:limit] if limit is not None else records


def save_emptied_record(record: dict) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(EMPTIED_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


def _uri_to_short_id(uri: str) -> str:
    """Extract the last colon-separated segment of a URN.

    e.g.  "urn:wastebin:bin-01"     → "bin-01"
          "urn:dev:team08:pir-01"   → "pir-01"
    """
    return uri.split(":")[-1]


def _build_registries() -> tuple[dict, dict]:
    """Build in-memory registries keyed by short IDs.

    FIX: previously the full URI was used as the dict key, so
         /bins/bin-01 always returned 404.
    """
    bins_reg: dict    = {}
    sensors_reg: dict = {}

    wastebin_path = os.path.join(MODELS_DIR, "wastebin.jsonld")
    sensor_path   = os.path.join(MODELS_DIR, "sensor.jsonld")
    env_path      = os.path.join(MODELS_DIR, "environment.jsonld")

    env_name = "Unknown"
    if os.path.exists(env_path):
        env_data = load_json(env_path)
        env_name = env_data.get("name", env_data.get("@id", "Unknown"))

    if os.path.exists(wastebin_path):
        wb = load_json(wastebin_path)
        bin_uri   = wb.get("@id", "unknown")
        # FIX: use short ID as key
        short_id  = _uri_to_short_id(bin_uri)
        raw_status = wb.get("pipeline:status", "unknown")
        bins_reg[short_id] = {
            "id":       short_id,
            "uri":      bin_uri,           # keep full URI for MQTT topic building
            "name":     wb.get("name", ""),
            "location": env_name,
            "status":   raw_status.get("@value", "unknown") if isinstance(raw_status, dict) else raw_status,
        }

    if os.path.exists(sensor_path):
        s = load_json(sensor_path)
        sensor_uri  = s.get("@id", "unknown")
        # FIX: use short ID as key
        short_sid   = _uri_to_short_id(sensor_uri)
        raw_status  = s.get("pipeline:status", "unknown")
        mounted_uri = s.get("sosa:isHostedBy", "")
        sensors_reg[short_sid] = {
            "id":         short_sid,
            "uri":        sensor_uri,
            "type":       "PIR",
            "model":      s.get("model", ""),
            # FIX: store the full mounted_on URI so get_sensor_for_bin can
            #      compare URIs to URIs rather than URI to short ID.
            "mounted_on": mounted_uri,
            "status":     raw_status.get("@value", "unknown") if isinstance(raw_status, dict) else raw_status,
        }

    return bins_reg, sensors_reg


bins_registry, sensors_registry = _build_registries()


def find_bin(bin_id: str) -> dict | None:
    return bins_registry.get(bin_id)


def find_sensor(sensor_id: str) -> dict | None:
    return sensors_registry.get(sensor_id)


def get_sensor_for_bin(bin_id: str) -> str | None:
    """Return the short sensor ID whose host URI matches this bin's URI.

    FIX: previously compared mounted_on URI against the short bin_id string,
         which never matched.
    """
    bin_entry = bins_registry.get(bin_id)
    if not bin_entry:
        return None
    bin_uri = bin_entry.get("uri", "")
    for short_sid, s in sensors_registry.items():
        if s.get("mounted_on") == bin_uri:
            return short_sid
    return None


def get_sensor_uri_for_bin(bin_id: str) -> str | None:
    """Return the full sensor URI for filtering JSONL events."""
    short_sid = get_sensor_for_bin(bin_id)
    if not short_sid:
        return None
    return sensors_registry[short_sid].get("uri")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


# ---------------------------------------------------------------------------
# Swagger models
# ---------------------------------------------------------------------------

bin_model = api.model("Bin", {
    "id":       fields.String(required=True),
    "name":     fields.String(),
    "location": fields.String(),
    "status":   fields.String(),
})

event_model = api.model("Event", {
    "event_time":   fields.String(),
    "device_id":    fields.String(),
    "motion_state": fields.String(),
    "fill_level":   fields.Integer(),
    "item_count":   fields.Integer(),
})

emptied_model = api.model("EmptiedRecord", {
    "bin_id":     fields.String(),
    "emptied_at": fields.String(),
    "emptied_by": fields.String(),
})

emptied_input_model = api.model("EmptiedInput", {
    "emptied_by": fields.String(description="Who emptied the bin (optional)", default="operator"),
})

sensor_model = api.model("Sensor", {
    "id":         fields.String(required=True),
    "type":       fields.String(),
    "mounted_on": fields.String(),
    "status":     fields.String(),
})

publish_model = api.model("MQTTPublish", {
    "topic":   fields.String(required=True,  description="MQTT topic to publish to"),
    "payload": fields.String(required=True,  description="Message payload"),
    "qos":     fields.Integer(description="Quality of Service (0, 1, or 2)", default=1),
    "retain":  fields.Boolean(description="Retain this message on the broker", default=False),
})

events_parser  = reqparse.RequestParser()
events_parser.add_argument("limit", type=int, default=50)

emptied_parser = reqparse.RequestParser()
emptied_parser.add_argument("limit", type=int, default=20)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@ns.route("/")
class BinList(Resource):
    @ns.marshal_list_with(bin_model)
    def get(self):
        """List all registered bins."""
        return list(bins_registry.values()), 200


@ns.route("/<string:bin_id>")
class BinDetail(Resource):
    @ns.marshal_with(bin_model)
    @ns.response(404, "Bin not found")
    def get(self, bin_id):
        """Get details for a specific bin."""
        bin_data = find_bin(bin_id)
        if not bin_data:
            api.abort(404, f"Bin '{bin_id}' not found")
        return bin_data, 200


@ns.route("/<string:bin_id>/events")
class BinEvents(Resource):
    @ns.expect(events_parser)
    @ns.marshal_list_with(event_model)
    def get(self, bin_id):
        """Get recent motion events for a bin."""
        if not find_bin(bin_id):
            api.abort(404, f"Bin '{bin_id}' not found")
        args       = events_parser.parse_args()
        sensor_uri = get_sensor_uri_for_bin(bin_id)
        return load_events(EVENTS_FILE, limit=args["limit"], sensor_uri=sensor_uri), 200


@ns.route("/<string:bin_id>/empty")
class BinEmpty(Resource):
    @ns.expect(emptied_input_model)
    @ns.marshal_with(emptied_model, code=200)
    def post(self, bin_id):
        """
        Mark a bin as emptied.

        Publishes an MQTT command so the producer resets fill level and
        item count to zero, then persists the emptied record locally.
        """
        if not find_bin(bin_id):
            api.abort(404, f"Bin '{bin_id}' not found")

        sensor_id = get_sensor_for_bin(bin_id)
        if not sensor_id:
            api.abort(400, f"Bin '{bin_id}' has no active sensor attached")

        payload_data = api.payload or {}
        emptied_by   = payload_data.get("emptied_by", "operator")
        emptied_at   = utc_now_iso()

        command_topic   = f"smartbin/{bin_id}/command"
        command_payload = json.dumps({
            "action":     "emptied",
            "emptied_at": emptied_at,
            "emptied_by": emptied_by,
        })

        result = mqtt_client.publish(command_topic, command_payload, qos=1)
        print(f"[API] Publishing to {command_topic}: {command_payload} (rc={result.rc})")
        if result.rc != mqtt.MQTT_ERR_SUCCESS:
            api.abort(503,
                f"Failed to publish MQTT command (rc={result.rc}). Is the broker reachable?")

        record = {
            "bin_id":     bin_id,
            "emptied_at": emptied_at,
            "emptied_by": emptied_by,
        }
        save_emptied_record(record)

        status_topic   = f"smartbin/{bin_id}/status"
        status_payload = json.dumps({"state": "emptied", "emptied_at": emptied_at})
        mqtt_client.publish(status_topic, status_payload, qos=1, retain=True)

        print(f"[EMPTY] Sent emptied command for bin {bin_id} at {emptied_at}")
        return record, 200


@ns.route("/<string:bin_id>/emptied-history")
class BinEmptiedHistory(Resource):
    @ns.expect(emptied_parser)
    @ns.marshal_list_with(emptied_model)
    def get(self, bin_id):
        """Get the emptied history for a bin."""
        if not find_bin(bin_id):
            api.abort(404, f"Bin '{bin_id}' not found")
        args = emptied_parser.parse_args()
        return load_emptied_records(bin_id, limit=args["limit"]), 200


@nsensor.route("/")
class SensorList(Resource):
    @nsensor.marshal_list_with(sensor_model)
    def get(self):
        """List all registered sensors."""
        return list(sensors_registry.values()), 200


@nsensor.route("/<string:sensor_id>")
class SensorDetail(Resource):
    @nsensor.marshal_with(sensor_model)
    @nsensor.response(404, "Sensor not found")
    def get(self, sensor_id):
        """Get details for a specific sensor."""
        sensor_data = find_sensor(sensor_id)
        if not sensor_data:
            api.abort(404, f"Sensor '{sensor_id}' not found")
        return sensor_data, 200


@nmqtt.route("/publish")
class MQTTPublish(Resource):
    @nmqtt.expect(publish_model)
    @nmqtt.response(200, "Message published")
    @nmqtt.response(400, "Invalid request")
    def post(self):
        """Publish a message to an MQTT topic."""
        data    = api.payload or {}
        topic   = data.get("topic")
        payload = data.get("payload")
        qos     = data.get("qos", 1)
        retain  = data.get("retain", False)

        if not topic or not payload:
            api.abort(400, "Both 'topic' and 'payload' are required")
        if qos not in [0, 1, 2]:
            api.abort(400, "QoS must be 0, 1, or 2")

        result = mqtt_client.publish(topic, payload, qos=qos, retain=retain)
        return {
            "status":  "published",
            "topic":   topic,
            "payload": payload,
            "qos":     qos,
            "retain":  retain,
            "mqtt_rc": result.rc,
        }, 200


@nmqtt.route("/topics")
class MqttTopics(Resource):
    def get(self):
        """List all known MQTT topics and their last received message."""
        with topic_lock:
            return {
                "topic_count": len(topic_store),
                "topics":      list(topic_store.values()),
            }, 200


@nmqtt.route("/topics/<path:topic>")
class MQTTTopicDetail(Resource):
    @nmqtt.response(404, "Topic not found or no message received yet")
    def get(self, topic):
        """Get the last received message for a specific MQTT topic."""
        with topic_lock:
            if topic not in topic_store:
                api.abort(404, f"No message received on topic '{topic}'")
            return topic_store[topic], 200


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=5000)
