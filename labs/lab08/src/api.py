import json
import os
from datetime import datetime, timezone

from flask import Flask
from flask_restx import Api, Resource, fields, reqparse

# ---------------------------------------------------------------------------
# App & API setup
# ---------------------------------------------------------------------------

app = Flask(__name__)
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

# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

# ✅ FIXED PATH (points to ../models)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "..", "models")

EVENTS_FILE = os.path.join(DATA_DIR, "motion_events.jsonl")


def load_json(filepath: str) -> dict:
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def load_events(
    filepath: str,
    limit: int | None = None,
    sensor_id: str | None = None,
) -> list:
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
                if sensor_id and record.get("device_id") != sensor_id:
                    continue
                events.append(record)
            except json.JSONDecodeError:
                continue

    events.reverse()

    if limit is not None:
        events = events[:limit]

    return events


# ---------------------------------------------------------------------------
# Build in-memory registries from JSON-LD model files
# ---------------------------------------------------------------------------

def _build_registries() -> tuple[dict, dict]:
    bins_reg    = {}
    sensors_reg = {}

    wastebin_path = os.path.join(DATA_DIR, "wastebin.jsonld")
    sensor_path   = os.path.join(DATA_DIR, "sensor.jsonld")
    env_path      = os.path.join(DATA_DIR, "environment.jsonld")

    print("📂 DATA_DIR:", DATA_DIR)
    print("📄 wastebin path exists:", os.path.exists(wastebin_path))
    print("📄 sensor path exists:", os.path.exists(sensor_path))

    env_name = "Unknown"
    if os.path.exists(env_path):
        env_data = load_json(env_path)
        env_name = env_data.get("name", env_data.get("@id", "Unknown"))

    if os.path.exists(wastebin_path):
        wb = load_json(wastebin_path)
        bin_id = wb.get("@id", "unknown")

        bins_reg[bin_id] = {
            "id":       bin_id,
            "name":     wb.get("name", ""),
            "location": env_name,
            "status":   wb.get("pipeline:status", "unknown"),
        }

    if os.path.exists(sensor_path):
        s = load_json(sensor_path)
        sensor_id  = s.get("@id", "unknown")
        raw_status = s.get("pipeline:status", "unknown")

        sensors_reg[sensor_id] = {
            "id":         sensor_id,
            "type":       "PIR",
            "model":      s.get("model", ""),
            "mounted_on": s.get("sosa:isHostedBy", ""),
            "status":     raw_status.get("@value", "unknown")
                          if isinstance(raw_status, dict) else raw_status,
        }

    print("✅ Bins loaded:", bins_reg)
    print("✅ Sensors loaded:", sensors_reg)

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
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


# ---------------------------------------------------------------------------
# Swagger models
# ---------------------------------------------------------------------------

bin_model = api.model("Bin", {
    "id":       fields.String(required=True),
    "name":     fields.String,
    "location": fields.String,
    "status":   fields.String,
})

event_model = api.model("Event", {
    "event_time":          fields.String,
    "device_id":           fields.String,
    "motion_state":        fields.String,
    "fill_level":          fields.Integer,
    "item_count":          fields.Integer,
    "pipeline_latency_ms": fields.Float,
})

sensor_model = api.model("Sensor", {
    "id":         fields.String(required=True),
    "type":       fields.String,
    "model":      fields.String,
    "mounted_on": fields.String,
    "status":     fields.String,
})

events_parser = reqparse.RequestParser()
events_parser.add_argument("limit", type=int, default=50)

# ---------------------------------------------------------------------------
# BINS endpoints
# ---------------------------------------------------------------------------

@ns.route("/")
class BinList(Resource):
    @ns.marshal_list_with(bin_model)
    def get(self):
        return list(bins_registry.values()), 200


@ns.route("/<string:bin_id>")
class BinDetail(Resource):
    @ns.marshal_with(bin_model)
    def get(self, bin_id):
        bin_data = find_bin(bin_id)
        if not bin_data:
            api.abort(404, f"Bin {bin_id} not found")
        return bin_data


@ns.route("/<string:bin_id>/sensors")
class BinSensors(Resource):
    @ns.marshal_list_with(sensor_model)
    def get(self, bin_id):
        if not find_bin(bin_id):
            api.abort(404, f"Bin {bin_id} not found")
        mounted = [s for s in sensors_registry.values() if s.get("mounted_on") == bin_id]
        return mounted, 200


@ns.route("/<string:bin_id>/events")
class BinEvents(Resource):
    @ns.expect(events_parser)
    @ns.marshal_list_with(event_model)
    def get(self, bin_id):
        if not find_bin(bin_id):
            api.abort(404, f"Bin {bin_id} not found")

        args = events_parser.parse_args()
        sensor_id = get_sensor_for_bin(bin_id)
        events = load_events(EVENTS_FILE, limit=args["limit"], sensor_id=sensor_id)

        return events, 200


# ---------------------------------------------------------------------------
# SENSORS endpoints
# ---------------------------------------------------------------------------

@nsensor.route("/")
class SensorList(Resource):
    @nsensor.marshal_list_with(sensor_model)
    def get(self):
        return list(sensors_registry.values()), 200


@nsensor.route("/<string:sensor_id>")
class SensorDetail(Resource):
    @nsensor.marshal_with(sensor_model)
    def get(self, sensor_id):
        sensor = find_sensor(sensor_id)
        if not sensor:
            api.abort(404, f"Sensor {sensor_id} not found")
        return sensor


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
