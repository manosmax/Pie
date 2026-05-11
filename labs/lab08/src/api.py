import json
import os
import paho.mqtt.client as mqtt
from datetime import datetime, timezone
from flask import Flask
from flask_restx import Api, Resource, fields, reqparse

# ---------------------------------------------------------------------------
# App & MQTT Setup
# ---------------------------------------------------------------------------

app = Flask(__name__)

# MQTT Settings
MQTT_BROKER = "localhost"
MQTT_PORT = 1883

mqtt_client = mqtt.Client()

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("[MQTT] Connected to broker successfully.")
    else:
        print(f"[MQTT] Connection failed with code {rc}")

mqtt_client.on_connect = on_connect

try:
    # loop_start() runs the background thread for MQTT heartbeats/publishing
    mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
    mqtt_client.loop_start()
except Exception as e:
    print(f"[MQTT] Initial connection error: {e}")

api = Api(
    app,
    version="1.0",
    title="Smart Wastebin API",
    description="REST API for querying Smart Wastebin sensor data and bin status",
)

# Namespaces
ns      = api.namespace("bins",    description="Wastebin operations")
nsensor = api.namespace("sensors", description="Sensor operations")
nmqtt   = api.namespace("mqtt",    description="MQTT operations")

DATA_DIR    = os.path.join(os.path.dirname(__file__), "data")
EVENTS_FILE = os.path.join(DATA_DIR, "motion_events.jsonl")

# ---------------------------------------------------------------------------
# Data Loading Helpers
# ---------------------------------------------------------------------------

def load_json(filepath: str) -> dict:
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)

def load_events(filepath: str, limit: int | None = None, sensor_id: str | None = None) -> list:
    events = []
    if not os.path.exists(filepath):
        return events

    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line: continue
            try:
                record = json.loads(line)
                if sensor_id and record.get("device_id") != sensor_id:
                    continue
                events.append(record)
            except json.JSONDecodeError:
                continue

    events.reverse()  # most recent first
    return events[:limit] if limit is not None else events

def _build_registries() -> tuple[dict, dict]:
    bins_reg, sensors_reg = {}, {}
    MODELS_DIR = os.path.join((os.path.dirname(__file__)), "models")
    
    # Paths to JSON-LD models
    wastebin_path = os.path.join(MODELS_DIR, "wastebin.jsonld")
    sensor_path   = os.path.join(MODELS_DIR, "sensor.jsonld")
    env_path      = os.path.join(MODELS_DIR, "environment.jsonld")

    env_name = "Unknown"
    if os.path.exists(env_path):
        env_data = load_json(env_path)
        env_name = env_data.get("name", env_data.get("@id", "Unknown"))

    if os.path.exists(wastebin_path):
        wb = load_json(wastebin_path)
        bin_id = wb.get("@id", "unknown")
        bins_reg[bin_id] = {
            "id": bin_id,
            "name": wb.get("name", ""),
            "location": env_name,
            "status": wb.get("pipeline:status", "unknown"),
        }

    if os.path.exists(sensor_path):
        s = load_json(sensor_path)
        sensor_id = s.get("@id", "unknown")
        raw_status = s.get("pipeline:status", "unknown")
        sensors_reg[sensor_id] = {
            "id": sensor_id,
            "type": "PIR",
            "model": s.get("model", ""),
            "mounted_on": s.get("sosa:isHostedBy", ""),
            "status": raw_status.get("@value", "unknown") if isinstance(raw_status, dict) else raw_status,
        }

    return bins_reg, sensors_reg

bins_registry, sensors_registry = _build_registries()

def find_bin(bin_id: str) -> dict | None:
    return bins_registry.get(bin_id)

def find_sensor(sensor_id: str) -> dict | None:
    return sensors_registry.get(sensor_id)

def get_sensor_for_bin(bin_id: str) -> str | None:
    for sid, s in sensors_registry.items():
        if s.get("mounted_on") == bin_id:
            return sid
    return None

def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")

# ---------------------------------------------------------------------------
# Swagger Models
# ---------------------------------------------------------------------------

bin_model = api.model("Bin", {
    "id": fields.String(required=True),
    "name": fields.String(),
    "location": fields.String(),
    "status": fields.String(),
})

event_model = api.model("Event", {
    "event_time": fields.String(),
    "device_id": fields.String(),
    "motion_state": fields.String(),
    "fill_level": fields.Integer(),
    "item_count": fields.Integer(),
})

emptied_model = api.model("EmptiedRecord", {
    "bin_id": fields.String(),
    "emptied_at": fields.String(),
    "emptied_by": fields.String(),
})

sensor_model = api.model("Sensor", {
    "id": fields.String(required=True),
    "type": fields.String(),
    "mounted_on": fields.String(),
    "status": fields.String(),
})

events_parser = reqparse.RequestParser()
events_parser.add_argument("limit", type=int, default=50)

# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@ns.route("/")
class BinList(Resource):
    @ns.marshal_list_with(bin_model)
    def get(self):
        return list(bins_registry.values()), 200

@ns.route("/<string:bin_id>/events")
class BinEvents(Resource):
    @ns.expect(events_parser)
    @ns.marshal_list_with(event_model)
    def get(self, bin_id):
        if not find_bin(bin_id):
            api.abort(404, f"Bin {bin_id} not found")
        args = events_parser.parse_args()
        sensor_id = get_sensor_for_bin(bin_id)
        return load_events(EVENTS_FILE, limit=args["limit"], sensor_id=sensor_id), 200

@ns.route("/<string:bin_id>/emptied")
class BinEmptied(Resource):
    @ns.expect(emptied_model)
    @ns.marshal_with(emptied_model, code=201)
    def post(self, bin_id):
        """Record that a bin was emptied and notify the Edge device via MQTT."""
        if not find_bin(bin_id):
            api.abort(404, f"Bin {bin_id} not found")

        data = api.payload or {}
        emptied_time = data.get("emptied_at") or utc_now_iso()
        
        record = {
            "bin_id": bin_id,
            "emptied_at": emptied_time,
            "emptied_by": data.get("emptied_by") or "unknown",
        }

        # --- MQTT Integration ---
        command_payload = {
            "action": "emptied",
            "bin_id": bin_id,
            "emptied_at": emptied_time
        }
        
        cmd_topic = f"smartbin/{bin_id}/command"
        result = mqtt_client.publish(cmd_topic, json.dumps(command_payload), qos=1)
        
        if result.rc == mqtt.MQTT_ERR_SUCCESS:
            print(f"[API] Command sent to {cmd_topic}")
        else:
            print(f"[API] MQTT Publish failed: {result.rc}")

        return record, 201

@nsensor.route("/")
class SensorList(Resource):
    @nsensor.marshal_list_with(sensor_model)
    def get(self):
        return list(sensors_registry.values()), 200

@nmqtt.route("/topics")
class MqttTopics(Resource):
    def get(self):
        return {"topics": ["events", "motion", "fill-level", "command"]}, 200

# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Note: Use threaded=True or loop_start() to ensure MQTT background processing
    app.run(debug=True, host="0.0.0.0", port=5000)