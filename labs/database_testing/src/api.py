"""
api.py — Smart Wastebin REST API (Flask-RESTX / Swagger)
=========================================================
All data served from SQLite (smartbin.db) via database.py.

/bins/                          GET  — list all bins
/bins/<bin_id>                  GET  — bin detail
/bins/<bin_id>/events           GET  — PIR events (paginated)
/bins/<bin_id>/usage            GET  — full weekly usage heatmap
/bins/<bin_id>/usage/peak       GET  — peak hour for a given day
/bins/<bin_id>/usage/least      GET  — least-active hour for a given day
/bins/<bin_id>/empty            POST — mark bin as emptied (MQTT + DB)
/bins/<bin_id>/emptied-history  GET  — emptied log

/sensors/                       GET  — list all sensors
/sensors/<sensor_id>            GET  — sensor detail
/sensors/<sensor_id>/events     GET  — PIR events for one sensor

/mqtt/publish                   POST — publish a raw MQTT message
/mqtt/subscribe                 POST — subscribe to an extra topic at runtime
/mqtt/topics                    GET  — live in-memory snapshot (last msg per topic)
/mqtt/topics/<path:topic>       GET  — last in-memory message for a specific topic
/mqtt/topics/<path:topic>       DELETE — remove topic from in-memory store
/mqtt/messages                  GET  — ALL stored MQTT messages from DB (paginated)
/mqtt/messages/<bin_id>         GET  — stored MQTT messages filtered by bin

/ml/retrain                     POST — retrain model from real DB data
/ml/predict                     GET  — predict busy/quiet for the next hour
"""

import json
import os
import threading
from datetime import datetime, timezone
from train_model import BUSY_THRESHOLD
import io
import csv

import paho.mqtt.client as mqtt
from flask import Flask, Response
from flask_restx import Api, Resource, fields, reqparse

from database import (
    DB_PATH,
    get_connection,
    init_db,
    insert_mqtt_message,
    insert_pir_event,
    upsert_bin,
    upsert_sensor,
    upsert_mounted_on,
    QUERY_PEAK_HOUR,
    QUERY_LEAST_HOUR,
    QUERY_WEEKLY_HEATMAP,
)

# ── utc_now_iso — MUST be defined before MQTT callbacks are registered ────────

def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")

# ── App & DB setup ────────────────────────────────────────────────────────────

app = Flask(__name__)

MQTT_BROKER = os.environ.get("MQTT_BROKER", "mosquitto")
MQTT_PORT   = int(os.environ.get("MQTT_PORT", 1883))

_BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
MODELS_DIR = os.path.join(_BASE_DIR, "models")
ML_DIR     = os.path.join(_BASE_DIR, "models_v_s")

init_db(DB_PATH)
db_conn = get_connection(DB_PATH)
db_lock = threading.Lock()

# ── MQTT ──────────────────────────────────────────────────────────────────────

mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, "wastebin-api")

# In-memory store: topic → last received message dict
topic_store: dict = {}
topic_lock  = threading.Lock()


def _extract_bin_id_from_topic(topic: str) -> str | None:
    """smartbin/<bin_id>/... → <bin_id>, or None."""
    parts = topic.split("/")
    if len(parts) >= 2 and parts[0] == "smartbin":
        return parts[1]
    return None


def on_message(client, userdata, msg):
    payload_str = msg.payload.decode("utf-8", errors="replace")
    ts = utc_now_iso()                          # safe — defined above

    # 1. Update in-memory snapshot (last message per topic)
    with topic_lock:
        topic_store[msg.topic] = {
            "topic":     msg.topic,
            "payload":   payload_str,
            "qos":       msg.qos,
            "retain":    msg.retain,
            "timestamp": ts,
        }

    # 2. Persist to MQTT_Messages table for crash-recovery / debug
    bin_id = _extract_bin_id_from_topic(msg.topic)
    with db_lock:
        insert_mqtt_message(db_conn, msg.topic, payload_str,
                            msg.qos, msg.retain, bin_id)

    # 3. If it's a sensor-event topic, also persist to PIR_Events + Bin_Usage
    if "/events" in msg.topic:
        try:
            record = json.loads(payload_str)
            with db_lock:
                insert_pir_event(db_conn, record)
        except Exception:
            pass


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

try:
    mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
    mqtt_client.reconnect_delay_set(min_delay=1, max_delay=30)
    mqtt_client.loop_start()
except Exception as e:
    print(f"[MQTT] Initial connection error: {e}")

# ── Bootstrap JSON-LD model files → DB ───────────────────────────────────────

def _load_json_safe(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _uri_to_short_id(uri: str) -> str:
    return uri.split(":")[-1]


def _bootstrap_registries():
    wb  = _load_json_safe(os.path.join(MODELS_DIR, "wastebin.jsonld"))
    s   = _load_json_safe(os.path.join(MODELS_DIR, "sensor.jsonld"))
    env = _load_json_safe(os.path.join(MODELS_DIR, "environment.jsonld"))

    env_name = env.get("name", env.get("@id", "Unknown"))

    if wb:
        bin_uri  = wb.get("@id", "")
        bin_id   = _uri_to_short_id(bin_uri)
        raw_stat = wb.get("pipeline:status", "active")
        status   = raw_stat.get("@value", "active") if isinstance(raw_stat, dict) else raw_stat
        with db_lock:
            upsert_bin(db_conn, bin_id, bin_uri, wb.get("name", ""), env_name, status)

    if s:
        sensor_uri  = s.get("@id", "")
        sensor_id   = _uri_to_short_id(sensor_uri)
        mounted_uri = s.get("sosa:isHostedBy", "")
        bin_id_s    = _uri_to_short_id(mounted_uri) if mounted_uri else None
        raw_stat    = s.get("pipeline:status", "active")
        status      = raw_stat.get("@value", "active") if isinstance(raw_stat, dict) else raw_stat
        with db_lock:
            upsert_sensor(db_conn, sensor_id, sensor_uri, "PIR",
                          s.get("model", ""), status)
            if bin_id_s:
                upsert_mounted_on(db_conn, sensor_id, bin_id_s)


_bootstrap_registries()

# ── Helpers ───────────────────────────────────────────────────────────────────

def _row_to_dict(row) -> dict:
    return dict(row) if row else {}


def _rows_to_list(rows) -> list:
    return [dict(r) for r in rows]

# ── Flask-RESTX / Swagger ────────────────────────────────────────────────────

api = Api(
    app,
    version="2.0",
    title="Smart Wastebin API",
    description="REST API — all data served from SQLite. Full Swagger UI.",
)

ns      = api.namespace("bins",    description="Bin operations")
nsensor = api.namespace("sensors", description="Sensor operations")
nmqtt   = api.namespace("mqtt",    description="MQTT operations")
nsml    = api.namespace("ml",      description="Machine-learning operations")

# ── Swagger models ────────────────────────────────────────────────────────────

bin_model = api.model("Bin", {
    "bin_id":     fields.String(required=True),
    "bin_uri":    fields.String(),
    "name":       fields.String(),
    "location":   fields.String(),
    "status":     fields.String(),
    "created_at": fields.String(),
})

sensor_model = api.model("Sensor", {
    "sensor_id":   fields.String(required=True),
    "sensor_uri":  fields.String(),
    "sensor_type": fields.String(),
    "model":       fields.String(),
    "status":      fields.String(),
    "bin_id":      fields.String(description="Bin this sensor is mounted on"),
})

event_model = api.model("PIREvent", {
    "id":                  fields.Integer(),
    "event_id":            fields.String(),
    "sensor_id":           fields.String(),
    "bin_id":              fields.String(),
    "event_time":          fields.String(),
    "ingest_time":         fields.String(),
    "motion_state":        fields.String(),
    "seq":                 fields.Integer(),
    "run_id":              fields.String(),
    "item_count":          fields.Integer(),
    "fill_level":          fields.Integer(),
    "pipeline_latency_ms": fields.Float(),
})

usage_model = api.model("BinUsage", {
    "bin_id":      fields.String(),
    "day_of_week": fields.Integer(description="0=Mon … 6=Sun"),
    "hour":        fields.Integer(description="0-23"),
    "usage_count": fields.Integer(),
})

peak_model = api.model("PeakHour", {
    "bin_id":      fields.String(),
    "day_of_week": fields.Integer(),
    "hour":        fields.Integer(),
    "usage_count": fields.Integer(),
    "label":       fields.String(),
})

emptied_model = api.model("EmptiedRecord", {
    "bin_id":     fields.String(),
    "emptied_at": fields.String(),
    "emptied_by": fields.String(),
})

emptied_input_model = api.model("EmptiedInput", {
    "emptied_by": fields.String(default="operator",
                                description="Who emptied the bin (optional)"),
})

topic_model = api.model("MQTTTopic", {
    "topic":     fields.String(description="MQTT topic string"),
    "payload":   fields.String(description="Last received payload (UTF-8)"),
    "qos":       fields.Integer(description="QoS level of the last message"),
    "retain":    fields.Boolean(description="Was the last message retained?"),
    "timestamp": fields.String(description="ISO-8601 UTC time the message was received"),
})

topics_list_model = api.model("MQTTTopicList", {
    "topic_count": fields.Integer(description="Number of distinct topics seen"),
    "topics":      fields.List(fields.Nested(topic_model)),
})

subscribe_input_model = api.model("MQTTSubscribeInput", {
    "topic": fields.String(required=True,
                           description="Topic filter (wildcards # and + supported)"),
    "qos":   fields.Integer(default=1, description="QoS level (0, 1 or 2)"),
})

publish_model = api.model("MQTTPublish", {
    "topic":   fields.String(required=True, description="MQTT topic to publish to"),
    "payload": fields.String(required=True, description="Message payload"),
    "qos":     fields.Integer(default=1, description="Quality of Service (0, 1 or 2)"),
    "retain":  fields.Boolean(default=False, description="Retain this message on the broker"),
})

mqtt_msg_model = api.model("MQTTMessage", {
    "id":          fields.Integer(),
    "bin_id":      fields.String(),
    "topic":       fields.String(),
    "payload":     fields.String(),
    "qos":         fields.Integer(),
    "retained":    fields.Boolean(),
    "received_at": fields.String(),
})

predict_model = api.model("MLPrediction", {
    "prediction":     fields.String(),
    "confidence":     fields.Float(),
    "predicted_hour": fields.Integer(),
    "day_of_week":    fields.Integer(),
    "is_weekend":     fields.Boolean(),
    "timestamp":      fields.String(),
})

retrain_model = api.model("MLRetrain", {
    "status":                fields.String(),
    "samples_used":          fields.Integer(),
    "model_path":            fields.String(),
    "classification_report": fields.String(),
})




# ── Parsers ───────────────────────────────────────────────────────────────────

limit_parser = reqparse.RequestParser()
limit_parser.add_argument("limit", type=int, default=50, help="Max rows to return")

day_parser = reqparse.RequestParser()
day_parser.add_argument("day", type=int, default=0,
                        help="Day of week: 0=Mon … 6=Sun")

mqtt_parser = reqparse.RequestParser()
mqtt_parser.add_argument("limit", type=int, default=100,
                         help="Max messages to return")



# ── /bins ────────────────────────────────────────────────────────────────────

@ns.route("/")
class BinList(Resource):
    @ns.marshal_list_with(bin_model)
    def get(self):
        """List all bins."""
        with db_lock:
            rows = db_conn.execute(
                "SELECT * FROM Bins ORDER BY bin_id"
            ).fetchall()
        return _rows_to_list(rows), 200


@ns.route("/<string:bin_id>")
class BinDetail(Resource):
    @ns.marshal_with(bin_model)
    @ns.response(404, "Bin not found")
    def get(self, bin_id):
        """Get details for a specific bin."""
        with db_lock:
            row = db_conn.execute(
                "SELECT * FROM Bins WHERE bin_id=?", (bin_id,)
            ).fetchone()
        if not row:
            api.abort(404, f"Bin '{bin_id}' not found")
        return _row_to_dict(row), 200


@ns.route("/<string:bin_id>/events")
class BinEvents(Resource):
    @ns.expect(limit_parser)
    @ns.marshal_list_with(event_model)
    @ns.response(404, "Bin not found")
    def get(self, bin_id):
        """Get PIR motion events for a bin (newest first)."""
        args = limit_parser.parse_args()
        with db_lock:
            if not db_conn.execute(
                "SELECT 1 FROM Bins WHERE bin_id=?", (bin_id,)
            ).fetchone():
                api.abort(404, f"Bin '{bin_id}' not found")
            rows = db_conn.execute(
                """SELECT * FROM PIR_Events WHERE bin_id=?
                   ORDER BY event_time DESC LIMIT ?""",
                (bin_id, args["limit"])
            ).fetchall()
        return _rows_to_list(rows), 200


@ns.route("/<string:bin_id>/usage")
class BinUsage(Resource):
    @ns.marshal_list_with(usage_model)
    @ns.response(404, "Bin not found")
    def get(self, bin_id):
        """Full weekly usage heatmap for a bin (7 days × 24 hours)."""
        with db_lock:
            if not db_conn.execute(
                "SELECT 1 FROM Bins WHERE bin_id=?", (bin_id,)
            ).fetchone():
                api.abort(404, f"Bin '{bin_id}' not found")
            rows = db_conn.execute(
                QUERY_WEEKLY_HEATMAP, {"bin_id": bin_id}
            ).fetchall()
        return _rows_to_list(rows), 200


@ns.route("/<string:bin_id>/usage/peak")
class BinPeakHour(Resource):
    @ns.expect(day_parser)
    @ns.marshal_with(peak_model)
    @ns.response(404, "No usage data found")
    def get(self, bin_id):
        """Peak usage hour for a bin on a specific day (0=Mon … 6=Sun)."""
        args = day_parser.parse_args()
        dow  = args["day"]
        with db_lock:
            row = db_conn.execute(
                QUERY_PEAK_HOUR, {"bin_id": bin_id, "day_of_week": dow}
            ).fetchone()
        if not row:
            api.abort(404, "No usage data for this bin/day")
        result = dict(row)
        result.update({"bin_id": bin_id, "day_of_week": dow, "label": "peak"})
        return result, 200


@ns.route("/<string:bin_id>/usage/least")
class BinLeastHour(Resource):
    @ns.expect(day_parser)
    @ns.marshal_with(peak_model)
    @ns.response(404, "No usage data found")
    def get(self, bin_id):
        """Least-active hour for a bin on a specific day (0=Mon … 6=Sun)."""
        args = day_parser.parse_args()
        dow  = args["day"]
        with db_lock:
            row = db_conn.execute(
                QUERY_LEAST_HOUR, {"bin_id": bin_id, "day_of_week": dow}
            ).fetchone()
        if not row:
            api.abort(404, "No usage data for this bin/day")
        result = dict(row)
        result.update({"bin_id": bin_id, "day_of_week": dow, "label": "least"})
        return result, 200


@ns.route("/<string:bin_id>/empty")
class BinEmpty(Resource):
    @ns.expect(emptied_input_model)
    @ns.marshal_with(emptied_model)
    @ns.response(404, "Bin not found")
    @ns.response(503, "MQTT publish failed")
    def post(self, bin_id):
        """Mark a bin as emptied — publishes MQTT command and stores record."""
        with db_lock:
            if not db_conn.execute(
                "SELECT 1 FROM Bins WHERE bin_id=?", (bin_id,)
            ).fetchone():
                api.abort(404, f"Bin '{bin_id}' not found")

        payload_data = api.payload or {}
        emptied_by   = payload_data.get("emptied_by", "operator")
        emptied_at   = utc_now_iso()

        cmd_topic   = f"smartbin/{bin_id}/command"
        cmd_payload = json.dumps({
            "action":     "emptied",
            "emptied_at": emptied_at,
            "emptied_by": emptied_by,
        })

        result = mqtt_client.publish(cmd_topic, cmd_payload, qos=1)
        print(f"[API] Publishing to {cmd_topic}: {cmd_payload} (rc={result.rc})")
        if result.rc != mqtt.MQTT_ERR_SUCCESS:
            api.abort(503, f"Failed to publish MQTT command (rc={result.rc}). "
                           "Is the broker reachable?")

        with db_lock:
            insert_mqtt_message(db_conn, cmd_topic, cmd_payload, 1, False, bin_id)

        status_payload = json.dumps({"state": "emptied", "emptied_at": emptied_at})
        mqtt_client.publish(f"smartbin/{bin_id}/status",
                            status_payload, qos=1, retain=True)

        print(f"[EMPTY] Sent emptied command for bin {bin_id} at {emptied_at}")
        return {"bin_id": bin_id, "emptied_at": emptied_at, "emptied_by": emptied_by}, 200


@ns.route("/<string:bin_id>/emptied-history")
class BinEmptiedHistory(Resource):
    @ns.expect(limit_parser)
    def get(self, bin_id):
        """Get emptied-command history for a bin from MQTT_Messages."""
        args = limit_parser.parse_args()
        with db_lock:
            rows = db_conn.execute(
                """SELECT id, bin_id, topic, payload, received_at AS emptied_at
                   FROM MQTT_Messages
                   WHERE bin_id=? AND topic LIKE '%/command'
                   ORDER BY received_at DESC LIMIT ?""",
                (bin_id, args["limit"])
            ).fetchall()
        return _rows_to_list(rows), 200
    

@ns.route("/<string:bin_id>/usage_data")
class BinUsageCSV(Resource):
    @ns.produces(["text/csv"])
    @ns.response(200, "CSV file download")
    @ns.response(404, "Bin not found")
    def get(self, bin_id):
        """Export full weekly usage heatmap as a CSV file for ML training.

        Returns a 168-row CSV (7 days × 24 hours) with columns:
        day_of_week, hour, is_weekend, event_count, label.
        Rows with no recorded usage are included with event_count=0.
        label is 'busy' if event_count >= BUSY_THRESHOLD, else 'quiet'.
        """
        with db_lock:
            if not db_conn.execute(
                "SELECT 1 FROM Bins WHERE bin_id=?", (bin_id,)
            ).fetchone():
                api.abort(404, f"Bin '{bin_id}' not found")

            rows = db_conn.execute(
                QUERY_WEEKLY_HEATMAP, {"bin_id": bin_id}
            ).fetchall()

        usage_lookup: dict[tuple[int, int], int] = {
            (r["day_of_week"], r["hour"]): r["usage_count"]
            for r in rows
        }

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["day_of_week", "hour", "is_weekend", "event_count", "label"])

        for dow in range(7):
            is_weekend = 1 if dow in (5, 6) else 0
            for hour in range(24):
                count = usage_lookup.get((dow, hour), 0)
                label = "busy" if count >= BUSY_THRESHOLD else "quiet"
                writer.writerow([dow, hour, is_weekend, count, label])

        return Response(
            output.getvalue().encode("utf-8"),
            status=200,
            mimetype="text/csv",
            headers={
                "Content-Disposition": f'attachment; filename="usage_data_{bin_id}.csv"',
                "Content-Type": "text/csv; charset=utf-8",
            }
        )
# ── /sensors ──────────────────────────────────────────────────────────────────

@nsensor.route("/")
class SensorList(Resource):
    @nsensor.marshal_list_with(sensor_model)
    def get(self):
        """List all sensors with their mounted bin."""
        with db_lock:
            rows = db_conn.execute("""
                SELECT s.*, m.bin_id
                FROM   Sensors s
                LEFT   JOIN Mounted_On m ON s.sensor_id = m.sensor_id
                ORDER  BY s.sensor_id
            """).fetchall()
        return _rows_to_list(rows), 200


@nsensor.route("/<string:sensor_id>")
class SensorDetail(Resource):
    @nsensor.marshal_with(sensor_model)
    @nsensor.response(404, "Sensor not found")
    def get(self, sensor_id):
        """Get details for a specific sensor."""
        with db_lock:
            row = db_conn.execute("""
                SELECT s.*, m.bin_id
                FROM   Sensors s
                LEFT   JOIN Mounted_On m ON s.sensor_id = m.sensor_id
                WHERE  s.sensor_id = ?
            """, (sensor_id,)).fetchone()
        if not row:
            api.abort(404, f"Sensor '{sensor_id}' not found")
        return _row_to_dict(row), 200


@nsensor.route("/<string:sensor_id>/events")
class SensorEvents(Resource):
    @nsensor.expect(limit_parser)
    @nsensor.marshal_list_with(event_model)
    @nsensor.response(404, "Sensor not found")
    def get(self, sensor_id):
        """Get recent PIR events for a specific sensor (newest first)."""
        args = limit_parser.parse_args()
        with db_lock:
            if not db_conn.execute(
                "SELECT 1 FROM Sensors WHERE sensor_id=?", (sensor_id,)
            ).fetchone():
                api.abort(404, f"Sensor '{sensor_id}' not found")
            rows = db_conn.execute(
                """SELECT * FROM PIR_Events WHERE sensor_id=?
                   ORDER BY event_time DESC LIMIT ?""",
                (sensor_id, args["limit"])
            ).fetchall()
        return _rows_to_list(rows), 200

# ── /mqtt ─────────────────────────────────────────────────────────────────────

@nmqtt.route("/publish")
class MQTTPublish(Resource):
    @nmqtt.expect(publish_model)
    @nmqtt.response(200, "Message published")
    @nmqtt.response(400, "Invalid request")
    def post(self):
        """Publish a raw message to any MQTT topic."""
        data    = api.payload or {}
        topic   = data.get("topic")
        payload = data.get("payload")
        qos     = data.get("qos", 1)
        retain  = data.get("retain", False)

        if not topic or not payload:
            api.abort(400, "Both 'topic' and 'payload' are required")
        if qos not in (0, 1, 2):
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



@nmqtt.route("/messages")
class MQTTMessageList(Resource):
    @nmqtt.expect(mqtt_parser)
    @nmqtt.marshal_list_with(mqtt_msg_model)
    def get(self):
        """All stored MQTT messages from the database, newest first.
        Persisted across restarts — use for crash/shutdown debugging."""
        args = mqtt_parser.parse_args()
        with db_lock:
            rows = db_conn.execute(
                "SELECT * FROM MQTT_Messages ORDER BY received_at DESC LIMIT ?",
                (args["limit"],)
            ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["retained"] = bool(d.get("retained", 0))
            result.append(d)
        return result, 200


@nmqtt.route("/messages/<string:bin_id>")
class MQTTMessagesByBin(Resource):
    @nmqtt.expect(mqtt_parser)
    @nmqtt.marshal_list_with(mqtt_msg_model)
    def get(self, bin_id):
        """All stored MQTT messages for a specific bin, newest first."""
        args = mqtt_parser.parse_args()
        with db_lock:
            rows = db_conn.execute(
                """SELECT * FROM MQTT_Messages WHERE bin_id=?
                   ORDER BY received_at DESC LIMIT ?""",
                (bin_id, args["limit"])
            ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["retained"] = bool(d.get("retained", 0))
            result.append(d)
        return result, 200

# ── /ml ───────────────────────────────────────────────────────────────────────

@nsml.route("/retrain")
class MLRetrain(Resource):
    @nsml.marshal_with(retrain_model)
    def post(self):
        """Retrain the busy/quiet predictor from real PIR_Events in the database.
        Falls back to synthetic data automatically if fewer than 50 real samples exist."""
        try:
            from train_model import train_from_db
            clf, report, n_samples, model_path = train_from_db(DB_PATH, ML_DIR)
            return {
                "status":                "ok",
                "samples_used":          n_samples,
                "model_path":            model_path,
                "classification_report": report,
            }, 200
        except ValueError as exc:
            from train_model import train_from_pseudo
            clf, report, n_samples, model_path = train_from_pseudo(ML_DIR)
            return {
                "status":                f"fallback_pseudo ({exc})",
                "samples_used":          n_samples,
                "model_path":            model_path,
                "classification_report": report,
            }, 200
        except Exception as exc:
            api.abort(500, str(exc))


@nsml.route("/predict")
class MLPredict(Resource):
    @nsml.marshal_with(predict_model)
    def get(self):
        """Predict busy/quiet for the next hour using the trained model.
        Returns 503 if the model has not been trained yet."""
        import joblib
        import pandas as pd

        model_path = os.path.join(ML_DIR, "busy_predictor.joblib")
        if not os.path.exists(model_path):
            api.abort(503, "Model not trained yet — POST /ml/retrain first.")

        clf       = joblib.load(model_path)
        now       = datetime.now()
        next_hour = (now.hour + 1) % 24
        dow       = now.weekday()
        is_wknd   = 1 if dow in (5, 6) else 0

        X          = pd.DataFrame([[dow, next_hour, is_wknd]],
                                  columns=["day_of_week", "hour", "is_weekend"])
        prediction = clf.predict(X)[0]
        proba      = clf.predict_proba(X)[0]
        confidence = float(proba[list(clf.classes_).index(prediction)])

        return {
            "prediction":     prediction,
            "confidence":     round(confidence, 3),
            "predicted_hour": next_hour,
            "day_of_week":    dow,
            "is_weekend":     bool(is_wknd),
            "timestamp":      utc_now_iso(),
        }, 200

# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=5000)
