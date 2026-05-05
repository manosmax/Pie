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

DATA_DIR    = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data") # ο φάκελος lab08 πρακτικά 
EVENTS_FILE = os.path.join(DATA_DIR, "motion_events.jsonl")


def load_json(filepath: str) -> dict:
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)

#ανοίγει το αρχείο motion events και για κάθε ένα αρχείοκ το βάζει στο local dictionary events 
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

    events.reverse()  # most recent first

    if limit is not None:
        events = events[:limit]

    return events



def _build_registries() -> tuple[dict, dict]:
    bins_reg    = {}
    sensors_reg = {}

    wastebin_path = os.path.join(DATA_DIR, "wastebin.jsonld")
    sensor_path   = os.path.join(DATA_DIR, "sensor.jsonld")
    env_path      = os.path.join(DATA_DIR, "environment.jsonld")

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

    return bins_reg, sensors_reg


bins_registry, sensors_registry = _build_registries()


def find_bin(bin_id: str) -> dict | None:
    return bins_registry.get(bin_id)


def find_sensor(sensor_id: str) -> dict | None:
    return sensors_registry.get(sensor_id)


def get_sensor_for_bin(bin_id: str) -> str | None:
    """Return the sensor ID mounted on a given bin."""
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
    "id":       fields.String(required=True, description="Bin unique identifier"),
    "name":     fields.String(description="Human-readable name"),
    "location": fields.String(description="Deployment location"),
    "status":   fields.String(description="Current status"),
})

event_model = api.model("Event", {
    "event_time":          fields.String(description="ISO timestamp of the event"),
    "device_id":           fields.String(description="Sensor ID that produced this event"),
    "motion_state":        fields.String(description="Motion state (detected/clear)"),
    "fill_level":          fields.Integer(description="Bin fill level (%)"),
    "item_count":          fields.Integer(description="Running item count"),
    "pipeline_latency_ms": fields.Float(description="Pipeline latency in ms"),
})

emptied_model = api.model("EmptiedRecord", {
    "bin_id":     fields.String(description="Bin identifier"),
    "emptied_at": fields.String(description="ISO timestamp of when the bin was emptied"),
    "emptied_by": fields.String(description="Who emptied the bin"),
})

sensor_model = api.model("Sensor", {
    "id":         fields.String(required=True, description="Sensor unique identifier"),
    "type":       fields.String(description="Sensor type (PIR, ultrasonic, etc.)"),
    "model":      fields.String(description="Hardware model"),
    "mounted_on": fields.String(description="Bin this sensor is mounted on"),
    "status":     fields.String(description="Current sensor status"),
})


events_parser = reqparse.RequestParser()
events_parser.add_argument("limit", type=int, default=50,   help="Max events to return")
events_parser.add_argument("start", type=str, default=None, help="Start datetime (ISO format)")
events_parser.add_argument("end",   type=str, default=None, help="End datetime (ISO format)")

# ---------------------------------------------------------------------------
# BINS endpoints
# ---------------------------------------------------------------------------

@ns.route("/")
class BinList(Resource):
    @ns.marshal_list_with(bin_model)
    def get(self):
        """List all registered bins."""
        return list(bins_registry.values()), 200


@ns.route("/<string:bin_id>")
@ns.param("bin_id", "The bin identifier (e.g. urn:wastebin:bin-01)")
@ns.response(404, "Bin not found")
class BinDetail(Resource):
    @ns.marshal_with(bin_model)
    def get(self, bin_id):
        """Fetch information for a specific bin."""
        bin_data = find_bin(bin_id)
        if not bin_data:
            api.abort(404, f"Bin {bin_id} not found")
        return bin_data


@ns.route("/<string:bin_id>/sensors")
@ns.param("bin_id", "The bin identifier")
@ns.response(404, "Bin not found")
class BinSensors(Resource):
    @ns.marshal_list_with(sensor_model)
    def get(self, bin_id):
        """Get all sensors mounted on a specific bin."""
        if not find_bin(bin_id):
            api.abort(404, f"Bin {bin_id} not found")
        mounted = [s for s in sensors_registry.values() if s.get("mounted_on") == bin_id]
        return mounted, 200


@ns.route("/<string:bin_id>/events")
@ns.param("bin_id", "The bin identifier")
@ns.response(404, "Bin not found")
class BinEvents(Resource):
    @ns.expect(events_parser)
    @ns.marshal_list_with(event_model)
    def get(self, bin_id):
        """Get motion event history for a specific bin."""
        if not find_bin(bin_id):
            api.abort(404, f"Bin {bin_id} not found")

        args      = events_parser.parse_args()
        sensor_id = get_sensor_for_bin(bin_id)
        events    = load_events(EVENTS_FILE, limit=args["limit"], sensor_id=sensor_id)

        # Optional datetime filtering
        if args["start"] or args["end"]:
            filtered = []
            for e in events:
                try:
                    t = datetime.fromisoformat(e["event_time"].replace("Z", "+00:00"))
                    if args["start"] and t < datetime.fromisoformat(args["start"].replace("Z", "+00:00")):
                        continue
                    if args["end"]   and t > datetime.fromisoformat(args["end"].replace("Z", "+00:00")):
                        continue
                    filtered.append(e)
                except (KeyError, ValueError):
                    filtered.append(e)
            events = filtered

        return events, 200


@ns.route("/<string:bin_id>/emptied")
@ns.param("bin_id", "The bin identifier")
@ns.response(201, "Bin marked as emptied")
@ns.response(404, "Bin not found")
class BinEmptied(Resource):
    @ns.expect(emptied_model)
    @ns.marshal_with(emptied_model, code=201)
    def post(self, bin_id):
        """Record that a bin was emptied."""
        if not find_bin(bin_id):
            api.abort(404, f"Bin {bin_id} not found")

        data   = api.payload or {}
        record = {
            "bin_id":     bin_id,
            "emptied_at": data.get("emptied_at") or utc_now_iso(),
            "emptied_by": data.get("emptied_by") or "unknown",
        }
        return record, 201


# ---------------------------------------------------------------------------
# SENSORS endpoints
# ---------------------------------------------------------------------------

@nsensor.route("/")
class SensorList(Resource):
    @nsensor.marshal_list_with(sensor_model)
    def get(self):
        """List all registered sensors."""
        return list(sensors_registry.values()), 200


@nsensor.route("/<string:sensor_id>")
@nsensor.param("sensor_id", "The sensor identifier (e.g. urn:dev:team08:pir-01)")
@nsensor.response(404, "Sensor not found")
class SensorDetail(Resource):
    @nsensor.marshal_with(sensor_model)
    def get(self, sensor_id):
        """Fetch information for a specific sensor."""
        sensor = find_sensor(sensor_id)
        if not sensor:
            api.abort(404, f"Sensor {sensor_id} not found")
        return sensor


# ---------------------------------------------------------------------------
# MQTT endpoints
# ---------------------------------------------------------------------------

@nmqtt.route("/publish")
class MqttPublish(Resource):
    def put(self):
        """Publish a message to an MQTT topic."""
        return {"message": "Published to MQTT"}, 200


@nmqtt.route("/topics")
class MqttTopics(Resource):
    def get(self):
        """List known MQTT topics and their last retained value."""
        topics = [
            {"topic": "smartbin/bin-01/pir-01/events",    "last_value": "N/A"},
            {"topic": "smartbin/bin-01/pir-01/motion",    "last_value": "N/A"},
            {"topic": "smartbin/bin-01/fill-level/state", "last_value": "N/A"},
        ]
        return {"topics": topics}, 200


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
