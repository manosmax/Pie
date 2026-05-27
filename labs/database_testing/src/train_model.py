import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report
import joblib
import os
import sqlite3

MIN_REAL_SAMPLES = 50   # minimum hourly slots before we trust real data
BUSY_THRESHOLD = 10   


# ── Synthetic data (cold-start fallback) ─────────────────────────────────────

def generate_training_data(days=30, seed=42):
    rng = np.random.default_rng(seed)
    rows = []

    for day in range(days):
        day_of_week = day % 7

        for hour in range(24):
            if day_of_week in (5, 6):
                base_rate = 2
            elif 8 <= hour <= 10:
                base_rate = 15
            elif 11 <= hour <= 14:
                base_rate = 25
            elif 15 <= hour <= 17:
                base_rate = 12
            elif 18 <= hour <= 20:
                base_rate = 8
            else:
                base_rate = 1

            event_count = int(rng.normal(base_rate, base_rate * 0.3))
            if event_count < 0:
                event_count = 0

            label = "busy" if event_count >= BUSY_THRESHOLD else "quiet"

            rows.append({
                "day_of_week": day_of_week,
                "hour":        hour,
                "is_weekend":  1 if day_of_week in (5, 6) else 0,
                "event_count": event_count,
                "label":       label,
            })

    return pd.DataFrame(rows)


def train_from_pseudo(output_dir="models_v_s"):
    """Train using synthetic data. Used on cold-start when DB has too few events."""
    os.makedirs(output_dir, exist_ok=True)

    df = generate_training_data()
    X  = df[["day_of_week", "hour", "is_weekend"]]
    y  = df["label"]

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42
    )

    clf = RandomForestClassifier(n_estimators=50, random_state=42)
    clf.fit(X_train, y_train)

    y_pred = clf.predict(X_test)
    report = classification_report(y_test, y_pred)

    print("Model evaluation (pseudo data):")
    print(report)

    model_path = os.path.join(output_dir, "busy_predictor.joblib")
    joblib.dump(clf, model_path, protocol=4)
    print(f"Model saved to {model_path}")

    return clf, report, len(df), model_path


# ── Real-data path ────────────────────────────────────────────────────────────

def load_real_data(db_path: str) -> pd.DataFrame:
    """
    Pull PIR_Events from the DB, group by (day_of_week, hour),
    count events per slot, label top-third as 'busy'.
    """
    conn = sqlite3.connect(db_path)
    df = pd.read_sql_query(
        """
        SELECT
            CAST(strftime('%w', event_time) AS INTEGER) AS dow_sun,
            CAST(strftime('%H', event_time) AS INTEGER) AS hour
        FROM PIR_Events
        WHERE event_time IS NOT NULL
        """,
        conn,
    )
    conn.close()

    if df.empty:
        return pd.DataFrame()

    # Convert Sunday-first (0=Sun) → Monday-first (0=Mon)
    df["day_of_week"] = (df["dow_sun"] - 1) % 7
    df["is_weekend"]  = df["day_of_week"].isin([5, 6]).astype(int)

    agg = (
        df.groupby(["day_of_week", "hour", "is_weekend"])
        .size()
        .reset_index(name="event_count")
    )

    agg["label"] = agg["event_count"].apply(
        lambda x: "busy" if x >= BUSY_THRESHOLD  else "quiet"
    )

    return agg

def train_from_csv(csv_path: str, output_dir: str = "models_v_s"):
    """Train from an uploaded CSV file (as produced by the dashboard or api.py export).
    Returns (clf, report_str, n_samples, model_path).
    Raises ValueError if the file has missing columns or too few rows.
    """
    os.makedirs(output_dir, exist_ok=True)

    df = pd.read_csv(csv_path)

    required = {"day_of_week", "hour", "is_weekend", "event_count", "label"}
    missing  = required - set(df.columns)
    if missing:
        raise ValueError(f"CSV missing required columns: {', '.join(sorted(missing))}")

    if len(df) < MIN_REAL_SAMPLES:
        raise ValueError(
            f"Only {len(df)} rows in CSV (need {MIN_REAL_SAMPLES}). "
            "Upload a larger file or use train_from_pseudo()."
        )

    bad_labels = set(df["label"].dropna().unique()) - {"busy", "quiet"}
    if bad_labels:
        raise ValueError(f"Unexpected label values in CSV: {bad_labels}")

    # Align label with shared threshold — re-derive from event_count to be safe
    df["label"] = df["event_count"].apply(
        lambda x: "busy" if x >= BUSY_THRESHOLD else "quiet"
    )

    X = df[["day_of_week", "hour", "is_weekend"]]
    y = df["label"]

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    clf = RandomForestClassifier(n_estimators=100, random_state=42)
    clf.fit(X_train, y_train)

    report     = classification_report(y_test, clf.predict(X_test))
    model_path = os.path.join(output_dir, "busy_predictor.joblib")
    joblib.dump(clf, model_path, protocol=4)

    print(f"[TRAIN] Trained on {len(df)} CSV rows. Model saved to {model_path}")
    print(report)

    return clf, report, len(df), model_path


def train_from_db(db_path: str, output_dir: str = "models_v_s"):
    """Train from real database data. Returns (clf, report_str, n_samples, model_path)."""
    os.makedirs(output_dir, exist_ok=True)

    df = load_real_data(db_path)
    if len(df) < MIN_REAL_SAMPLES:
        raise ValueError(
            f"Only {len(df)} hourly samples in DB (need {MIN_REAL_SAMPLES}). "
            "Collect more data or use train_from_pseudo()."
        )

    X = df[["day_of_week", "hour", "is_weekend"]]
    y = df["label"]

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    clf = RandomForestClassifier(n_estimators=100, random_state=42)
    clf.fit(X_train, y_train)

    y_pred = clf.predict(X_test)
    report = classification_report(y_test, y_pred)

    print(f"[TRAIN] Trained on {len(df)} real samples.")
    print(report)

    model_path = os.path.join(output_dir, "busy_predictor.joblib")
    joblib.dump(clf, model_path, protocol=4)
    print(f"Model saved to {model_path}")

    return clf, report, len(df), model_path


# ── CLI entry point ───────────────────────────────────────────────────────────

def train_and_save(output_dir="models_v_s", db_path="smartbin.db"):
    """
    Try real DB data first; fall back to pseudo if not enough rows.
    """
    if os.path.exists(db_path):
        try:
            return train_from_db(db_path, output_dir)
        except ValueError as e:
            print(f"[TRAIN] Real-data training skipped: {e}")
            print("[TRAIN] Falling back to pseudo data ...")

    return train_from_pseudo(output_dir)


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description="Train busy/quiet predictor")
    p.add_argument("--output-dir",   default="models_v_s")
    p.add_argument("--db-path",      default="smartbin.db")
    p.add_argument("--force-pseudo", action="store_true",
                   help="Skip real data, use synthetic data only")
    args = p.parse_args()

    if args.force_pseudo:
        train_from_pseudo(args.output_dir)
    else:
        train_and_save(args.output_dir, args.db_path)
