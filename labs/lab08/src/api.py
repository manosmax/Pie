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

# FIX 1: Add on_disconnect handler so the background loop reconnects automatically.
# Without this, a transient broker restart would leave the API unable to publish
# any "emptied" commands for the rest of the process lifetime.
def on_disconnect(client, userdata, rc):
    if rc != 0:
        print(f"[MQTT] Unexpected disconnect (rc={rc}). Will auto-reconnect...")

mqtt_client.on_connect = on_connect
mqtt_client.on_disconnect = on_disconnect

try:
    mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
    # FIX 2: Use loop_start() (already present) — but pair it with reconnect_delay_set
    # so paho retries automatically after a disconnect.
    mqtt_client.reconnect_delay_set(min_delay=1, max_delay=30)
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

DATA_DIR      = os.path.join(os.path.dirname(__file__), "data")
EVENTS_FILE   = os.path.join(DATA_DIR, "motion_events.jsonl")
# FIX 3: Persist emptied records so they survive API restarts and are queryable.
EMPTIED_FILE  = os.path.join(DATA_DIR, "emptied_records.jsonl")

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

def load_emptied_records(bin_id: str, limit: int | None = None) -> list:
    """Load persisted emptied records for a specific bin."""
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
    records.reverse()  # most recent first
    return records[:limit] if limit is not None else records

def save_emptied_record(record: dict) -> None:
    """Append an emptied record to the JSONL persistence file."""
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(EMPTIED_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")

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

emptied_parser = reqparse.RequestParser()
emptied_parser.add_argument("limit", type=int, default=20)

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
    @ns.expect(emptied_parser)
    @ns.marshal_list_with(emptied_model)
    def get(self, bin_id):
        """Retrieve the emptied history for a bin."""
        if not find_bin(bin_id):
            api.abort(404, f"Bin {bin_id} not found")
        args = emptied_parser.parse_args()
        return load_emptied_records(bin_id, limit=args["limit"]), 200

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

        # FIX 4: Persist the emptied record before publishing so the data is
        # never lost even if the MQTT publish fails.
        save_emptied_record(record)

        # --- MQTT Integration ---
        command_payload = {
            "action": "emptied",
            "bin_id": bin_id,
            "emptied_at": emptied_time
        }
        
        cmd_topic = f"smartbin/{bin_id}/command"

        # FIX 5: Check whether the client is actually connected before publishing.
        # If not, attempt a reconnect rather than silently doing nothing.
        if not mqtt_client.is_connected():
            print("[API] MQTT client not connected — attempting reconnect...")
            try:
                mqtt_client.reconnect()
            except Exception as e:
                print(f"[API] Reconnect failed: {e}")

        result = mqtt_client.publish(cmd_topic, json.dumps(command_payload), qos=1)
        
        if result.rc == mqtt.MQTT_ERR_SUCCESS:
            print(f"[API] Command sent to {cmd_topic}")
        else:
            # Record is already saved; log the failure but still return 201.
            print(f"[API] MQTT publish failed (rc={result.rc}). "
                  "Edge device will pick up state on next connection.")

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
    app.run(debug=True, host="0.0.0.0", port=5000)