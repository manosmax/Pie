import json
import os
from datetime import datetime, timezone

from flask import Flask
from flask_restx import Api, Resource, fields, reqparse

# ---------------------------------------------------------------------------
# DEBUG UTILITIES
# ---------------------------------------------------------------------------

def print_tree(start_path, prefix=""):
    if not os.path.exists(start_path):
        print(f"{prefix}❌ {start_path} (not found)")
        return

    print(f"{prefix}📁 {os.path.basename(start_path)}/")

    try:
        items = os.listdir(start_path)
    except PermissionError:
        print(f"{prefix}⚠️ Permission denied")
        return

    for i, name in enumerate(sorted(items)):
        path = os.path.join(start_path, name)
        is_last = i == len(items) - 1
        connector = "└── " if is_last else "├── "

        if os.path.isdir(path):
            print(f"{prefix}{connector}📁 {name}/")
            new_prefix = prefix + ("    " if is_last else "│   ")
            print_tree(path, new_prefix)
        else:
            print(f"{prefix}{connector}📄 {name}")


def debug_print_json(label, data):
    print(f"\n📦 {label}:")
    try:
        print(json.dumps(data, indent=2))
    except Exception as e:
        print("❌ Failed to print JSON:", e)


# ---------------------------------------------------------------------------
# PATH SETUP
# ---------------------------------------------------------------------------

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(BASE_DIR, ".."))
DATA_DIR = os.path.join(ROOT_DIR, "models")

EVENTS_FILE = os.path.join(DATA_DIR, "motion_events.jsonl")

print("\n================ DEBUG START ================\n")
print("📍 BASE_DIR:", BASE_DIR)
print("📍 ROOT_DIR:", ROOT_DIR)
print("📍 DATA_DIR:", DATA_DIR)
print("📍 EVENTS_FILE:", EVENTS_FILE)

print("\n--- 🌳 FULL PROJECT TREE ---")
print_tree(ROOT_DIR)

print("\n--- 🌳 MODELS TREE ---")
print_tree(DATA_DIR)

print("\n--- 📂 FILE EXISTENCE CHECK ---")
wastebin_path = os.path.join(DATA_DIR, "wastebin.jsonld")
sensor_path   = os.path.join(DATA_DIR, "sensor.jsonld")
env_path      = os.path.join(DATA_DIR, "environment.jsonld")

print("wastebin.jsonld:", os.path.exists(wastebin_path), wastebin_path)
print("sensor.jsonld:", os.path.exists(sensor_path), sensor_path)
print("environment.jsonld:", os.path.exists(env_path), env_path)
print("motion_events.jsonl:", os.path.exists(EVENTS_FILE), EVENTS_FILE)

print("\n============================================\n")

# ---------------------------------------------------------------------------
# APP SETUP
# ---------------------------------------------------------------------------

app = Flask(__name__)
api = Api(app)

ns = api.namespace("bins")
nsensor = api.namespace("sensors")

# ---------------------------------------------------------------------------
# LOADERS
# ---------------------------------------------------------------------------

def load_json(filepath):
    print(f"\n📥 Loading JSON: {filepath}")
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
        debug_print_json("Loaded JSON", data)
        return data


def load_events(filepath, limit=None, sensor_id=None):
    print(f"\n📥 Loading events from: {filepath}")

    events = []

    if not os.path.exists(filepath):
        print("⚠️ Events file does not exist")
        return events

    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            try:
                record = json.loads(line)
                if sensor_id and record.get("device_id") != sensor_id:
                    continue
                events.append(record)
            except:
                continue

    events.reverse()

    if limit:
        events = events[:limit]

    print(f"✅ Loaded {len(events)} events")
    return events


# ---------------------------------------------------------------------------
# BUILD REGISTRIES
# ---------------------------------------------------------------------------

def _build_registries():
    bins = {}
    sensors = {}

    env_name = "Unknown"

    if os.path.exists(env_path):
        env = load_json(env_path)
        env_name = env.get("name", env.get("@id", "Unknown"))

    if os.path.exists(wastebin_path):
        wb = load_json(wastebin_path)
        bin_id = wb.get("@id", "unknown")

        print("🆔 BIN ID FOUND:", bin_id)

        bins[bin_id] = {
            "id": bin_id,
            "name": wb.get("name"),
            "location": env_name,
            "status": wb.get("pipeline:status"),
        }
    else:
        print("❌ wastebin.jsonld NOT FOUND")

    if os.path.exists(sensor_path):
        s = load_json(sensor_path)
        sensor_id = s.get("@id", "unknown")

        print("🆔 SENSOR ID FOUND:", sensor_id)

        raw_status = s.get("pipeline:status")

        sensors[sensor_id] = {
            "id": sensor_id,
            "type": "PIR",
            "model": s.get("model"),
            "mounted_on": s.get("sosa:isHostedBy"),
            "status": raw_status.get("@value") if isinstance(raw_status, dict) else raw_status,
        }
    else:
        print("❌ sensor.jsonld NOT FOUND")

    print("\n🔗 SENSOR → BIN mapping:")
    for sid, s in sensors.items():
        print(f"  Sensor {sid} mounted on → {s.get('mounted_on')}")

    print("\n📊 FINAL REGISTRIES:")
    debug_print_json("Bins", bins)
    debug_print_json("Sensors", sensors)

    return bins, sensors


bins_registry, sensors_registry = _build_registries()

# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

def find_bin(bin_id):
    print(f"\n🔍 Looking for bin: {bin_id}")
    print("Available bins:", list(bins_registry.keys()))
    return bins_registry.get(bin_id)


def get_sensor_for_bin(bin_id):
    for sid, s in sensors_registry.items():
        if s.get("mounted_on") == bin_id:
            print(f"✅ Found sensor {sid} for bin {bin_id}")
            return sid
    print("⚠️ No sensor found for bin")
    return None


# ---------------------------------------------------------------------------
# API MODELS
# ---------------------------------------------------------------------------

bin_model = api.model("Bin", {
    "id": fields.String,
    "name": fields.String,
    "location": fields.String,
    "status": fields.String,
})

# ---------------------------------------------------------------------------
# ENDPOINTS
# ---------------------------------------------------------------------------

@ns.route("/")
class BinList(Resource):
    def get(self):
        print("\n📡 GET /bins")
        return list(bins_registry.values())


@ns.route("/<string:bin_id>")
class BinDetail(Resource):
    def get(self, bin_id):
        print(f"\n📡 GET /bins/{bin_id}")
        b = find_bin(bin_id)
        if not b:
            return {"error": "not found"}, 404
        return b


@ns.route("/<string:bin_id>/events")
class BinEvents(Resource):
    def get(self, bin_id):
        print(f"\n📡 GET /bins/{bin_id}/events")
        sensor_id = get_sensor_for_bin(bin_id)
        return load_events(EVENTS_FILE, sensor_id=sensor_id)


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("\n🚀 STARTING FLASK...\n")
    app.run(debug=True, host="0.0.0.0", port=5000)
