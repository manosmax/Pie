"""
database.py — SQLite schema initialisation for the Smart Waste Bin project.

Tables
------
Bins            — one row per physical bin (expandable)
Sensors         — one row per sensor (expandable)
Mounted_On      — M:M relationship: which sensor lives in which bin
PIR_Events      — every motion observation from every PIR sensor
Bin_Usage       — hourly usage counts, keyed by (bin_id, day_of_week, hour)
MQTT_Messages   — raw MQTT payloads for crash/debug recovery
"""

import sqlite3
import os
from datetime import datetime, timezone

DB_PATH = os.environ.get("DB_PATH", "smartbin.db")


def get_connection(db_path: str = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def init_db(db_path: str = DB_PATH) -> None:
    conn = get_connection(db_path)
    c = conn.cursor()

    # ------------------------------------------------------------------ Bins
    c.execute("""
        CREATE TABLE IF NOT EXISTS Bins (
            bin_id      TEXT PRIMARY KEY,          -- e.g. "bin-01"
            bin_uri     TEXT UNIQUE,               -- full URN e.g. "urn:wastebin:bin-01"
            name        TEXT,
            location    TEXT,
            status      TEXT DEFAULT 'active',
            created_at  TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
        )
    """)

    # --------------------------------------------------------------- Sensors
    c.execute("""
        CREATE TABLE IF NOT EXISTS Sensors (
            sensor_id   TEXT PRIMARY KEY,          -- e.g. "pir-01"
            sensor_uri  TEXT UNIQUE,               -- full URN e.g. "urn:dev:team08:pir-01"
            sensor_type TEXT DEFAULT 'PIR',
            model       TEXT,
            status      TEXT DEFAULT 'active',
            created_at  TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
        )
    """)

    # ------------------------------------------------------------ Mounted_On
    # Defines which sensor is mounted in which bin (many sensors per bin allowed)
    c.execute("""
        CREATE TABLE IF NOT EXISTS Mounted_On (
            sensor_id   TEXT NOT NULL REFERENCES Sensors(sensor_id) ON DELETE CASCADE,
            bin_id      TEXT NOT NULL REFERENCES Bins(bin_id)       ON DELETE CASCADE,
            mounted_at  TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
            PRIMARY KEY (sensor_id, bin_id)
        )
    """)

    # ---------------------------------------------------------- PIR_Events
    # Every motion observation.  Maps back to JSON-LD fields from producer.py.
    c.execute("""
        CREATE TABLE IF NOT EXISTS PIR_Events (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id            TEXT UNIQUE,        -- JSON-LD "@id"  e.g. "urn:event:<run>:<seq>"
            sensor_id           TEXT NOT NULL REFERENCES Sensors(sensor_id),
            bin_id              TEXT NOT NULL REFERENCES Bins(bin_id),
            event_time          TEXT NOT NULL,      -- sosa:resultTime  (ISO-8601 UTC)
            ingest_time         TEXT,               -- pipeline:ingestTime
            motion_state        TEXT DEFAULT 'detected',  -- sosa:hasSimpleResult
            event_type          TEXT,               -- sosa:observedProperty URN
            seq                 INTEGER,            -- pipeline:sequenceNumber
            run_id              TEXT,               -- pipeline:runId
            item_count          INTEGER,            -- pipeline:itemCount
            fill_level          INTEGER,            -- pipeline:fillLevel  (0-100)
            pipeline_latency_ms REAL
        )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_pir_bin_time  ON PIR_Events(bin_id, event_time)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_pir_sensor    ON PIR_Events(sensor_id)")

    # ----------------------------------------------------------- Bin_Usage
    # Hourly usage aggregates — one row per (bin_id, day_of_week, hour).
    # day_of_week: 0=Monday … 6=Sunday  (matches Python weekday())
    # usage_count is incremented by the consumer / API on every new PIR event.
    c.execute("""
        CREATE TABLE IF NOT EXISTS Bin_Usage (
            bin_id      TEXT NOT NULL REFERENCES Bins(bin_id) ON DELETE CASCADE,
            day_of_week INTEGER NOT NULL CHECK(day_of_week BETWEEN 0 AND 6),
            hour        INTEGER NOT NULL CHECK(hour BETWEEN 0 AND 23),
            usage_count INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (bin_id, day_of_week, hour)
        )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_usage_bin ON Bin_Usage(bin_id)")

    # --------------------------------------------------------- MQTT_Messages
    # Raw broker payloads — used for post-crash debugging.
    c.execute("""
        CREATE TABLE IF NOT EXISTS MQTT_Messages (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            bin_id      TEXT REFERENCES Bins(bin_id),  -- NULL if topic not tied to a bin
            topic       TEXT NOT NULL,
            payload     TEXT NOT NULL,                  -- raw UTF-8 string
            qos         INTEGER DEFAULT 1,
            retained    INTEGER DEFAULT 0,              -- BOOLEAN (0/1)
            received_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
        )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_mqtt_bin      ON MQTT_Messages(bin_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_mqtt_received ON MQTT_Messages(received_at)")

    conn.commit()
    conn.close()
    print(f"[DB] Schema initialised at '{db_path}'")


# ── Convenience helpers used by api.py ──────────────────────────────────────

def upsert_bin(conn: sqlite3.Connection, bin_id: str, bin_uri: str,
               name: str = "", location: str = "", status: str = "active") -> None:
    conn.execute("""
        INSERT INTO Bins (bin_id, bin_uri, name, location, status)
        VALUES (?,?,?,?,?)
        ON CONFLICT(bin_id) DO UPDATE SET
            bin_uri  = excluded.bin_uri,
            name     = excluded.name,
            location = excluded.location,
            status   = excluded.status
    """, (bin_id, bin_uri, name, location, status))
    conn.commit()


def upsert_sensor(conn: sqlite3.Connection, sensor_id: str, sensor_uri: str,
                  sensor_type: str = "PIR", model: str = "",
                  status: str = "active") -> None:
    conn.execute("""
        INSERT INTO Sensors (sensor_id, sensor_uri, sensor_type, model, status)
        VALUES (?,?,?,?,?)
        ON CONFLICT(sensor_id) DO UPDATE SET
            sensor_uri  = excluded.sensor_uri,
            sensor_type = excluded.sensor_type,
            model       = excluded.model,
            status      = excluded.status
    """, (sensor_id, sensor_uri, sensor_type, model, status))
    conn.commit()


def upsert_mounted_on(conn: sqlite3.Connection, sensor_id: str, bin_id: str) -> None:
    conn.execute("""
        INSERT OR IGNORE INTO Mounted_On (sensor_id, bin_id) VALUES (?,?)
    """, (sensor_id, bin_id))
    conn.commit()


def insert_pir_event(conn: sqlite3.Connection, record: dict) -> None:
    """Insert a JSON-LD event record (from producer / consumer) into PIR_Events
    and increment the matching Bin_Usage counter."""
    

    event_time_str = record.get("event_time", "")
    try:
        et = datetime.fromisoformat(event_time_str.replace("Z", "+00:00"))
    except Exception:
        et = datetime.now(timezone.utc)

    dow  = et.weekday()    # 0=Mon … 6=Sun
    hour = et.hour

    # Resolve short IDs
    raw_sensor_uri = record.get("device_id", "")
    raw_bin_uri    = record.get("mounted_on", "")
    sensor_id = raw_sensor_uri.split(":")[-1]
    bin_id    = raw_bin_uri.split(":")[-1]

    conn.execute("""
        INSERT OR IGNORE INTO PIR_Events
            (event_id, sensor_id, bin_id, event_time, ingest_time,
             motion_state, event_type, seq, run_id,
             item_count, fill_level, pipeline_latency_ms)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        record.get("@id"),
        sensor_id,
        bin_id,
        event_time_str,
        record.get("ingest_time"),
        record.get("motion_state", "detected"),
        record.get("event_type"),
        record.get("seq"),
        record.get("run_id"),
        record.get("item_count"),
        record.get("fill_level"),
        record.get("pipeline_latency_ms"),
    ))

    # Upsert usage counter
    conn.execute("""
        INSERT INTO Bin_Usage (bin_id, day_of_week, hour, usage_count)
        VALUES (?,?,?,1)
        ON CONFLICT(bin_id, day_of_week, hour) DO UPDATE SET
            usage_count = usage_count + 1
    """, (bin_id, dow, hour))

    conn.commit()


def insert_mqtt_message(conn: sqlite3.Connection, topic: str, payload: str,
                        qos: int = 1, retained: bool = False,
                        bin_id: str | None = None) -> None:
    conn.execute("""
        INSERT INTO MQTT_Messages (bin_id, topic, payload, qos, retained)
        VALUES (?,?,?,?,?)
    """, (bin_id, topic, payload, qos, int(retained)))
    conn.commit()


# ── Useful analytical queries (for reference / direct use) ──────────────────

QUERY_PEAK_HOUR = """
-- Peak usage hour for a given bin on a given day-of-week
SELECT hour, usage_count
FROM   Bin_Usage
WHERE  bin_id = :bin_id
  AND  day_of_week = :day_of_week
ORDER  BY usage_count DESC
LIMIT  1;
"""

QUERY_LEAST_HOUR = """
-- Least active hour for a given bin on a given day-of-week
SELECT hour, usage_count
FROM   Bin_Usage
WHERE  bin_id = :bin_id
  AND  day_of_week = :day_of_week
  AND  usage_count > 0
ORDER  BY usage_count ASC
LIMIT  1;
"""

QUERY_WEEKLY_HEATMAP = """
-- Full weekly heatmap for a bin (all 7 days × 24 hours)
SELECT day_of_week, hour, usage_count
FROM   Bin_Usage
WHERE  bin_id = :bin_id
ORDER  BY day_of_week, hour;
"""


if __name__ == "__main__":
    init_db()
