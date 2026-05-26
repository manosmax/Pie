import json
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
import os
from datetime import datetime

sns.set_theme(style="whitegrid")

CHARTS_DIR = "charts"

os.makedirs(CHARTS_DIR, exist_ok=True)

def load_events(filepath):
    records = []
    
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            
            if not line:
                continue
            
            try:
                record = json.loads(line)
                records.append(record)
            except json.JSONDecodeError:
                continue
    
    df = pd.DataFrame(records)
    
    if "resultTime" in df.columns:
        df["timestamp"] = pd.to_datetime(df["resultTime"])
    elif "event_time" in df.columns:
        df["timestamp"] = pd.to_datetime(df["event_time"])
        
    if "timestamp" in df.columns:
        df["hour"] = df["timestamp"].dt.hour
        df["day_of_week"] = df["timestamp"].dt.day_name()
        df["date"] = df["timestamp"].dt.date
        df["minute"] = df["timestamp"].dt.minute
        
    return df


def plot_events_per_hour(df):
    hourly = df.groupby("hour").size().reset_index(name="event_count")

    fig, ax = plt.subplots(figsize=(10, 5))

    sns.barplot(data=hourly, x="hour", y="event_count", color="blue", ax=ax)

    ax.set_xlabel("Hour of Day")
    ax.set_ylabel("Number of Events")
    ax.set_title("Motion Events by Hour of Day")

    plt.tight_layout()

    filepath = os.path.join(CHARTS_DIR, "events_per_hour.png")
    plt.savefig(filepath, dpi=150)
    plt.close(fig)

    print(f"[Saved] Το γράφημα αποθηκεύτηκε: {filepath}")


def plot_latency_distribution(df):
    if "pipeline_latency_ms" not in df.columns:
        print("[Skipped] Δεν βρέθηκε η στήλη 'pipeline_latency_ms'. Παράλειψη γραφήματος distribution.")
        return

    fig, ax = plt.subplots(figsize=(10, 5))

    sns.histplot(data=df, x="pipeline_latency_ms", kde=True, color="green", ax=ax)

    ax.set_xlabel("Pipeline Latency (ms)")
    ax.set_ylabel("Frequency")
    ax.set_title("Distribution of Pipeline Latency")

    plt.tight_layout()

    filepath = os.path.join(CHARTS_DIR, "latency_distribution.png")
    plt.savefig(filepath, dpi=150)
    plt.close(fig)

    print(f"[Saved] Το γράφημα αποθηκεύτηκε: {filepath}")


def plot_events_over_time(df):
    daily = df.groupby("date").size().reset_index(name="event_count")

    fig, ax = plt.subplots(figsize=(10, 5))

    sns.lineplot(data=daily, x="date", y="event_count", marker="o", color="orangered", ax=ax)

    ax.set_xlabel("Date")
    ax.set_ylabel("Number of Events")
    ax.set_title("Daily Motion Events Over Time")

    plt.xticks(rotation=45)

    plt.tight_layout()

    filepath = os.path.join(CHARTS_DIR, "events_over_time.png")
    plt.savefig(filepath, dpi=150)
    plt.close(fig)

    print(f"[Saved] Το γράφημα αποθηκεύτηκε: {filepath}")


def plot_heatmap(df):
    day_order = [
        "Monday", "Tuesday", "Wednesday", "Thursday", 
        "Friday", "Saturday", "Sunday"
    ]

    pivot_data = df.groupby(["day_of_week", "hour"]).size().reset_index(name="count")

    pivot_table = pivot_data.pivot(index="day_of_week", columns="hour", values="count")

    pivot_table = pivot_table.fillna(0).reindex(day_order)

    fig, ax = plt.subplots(figsize=(12, 5))

    sns.heatmap(data=pivot_table, cmap="YlOrRd", annot=True, fmt="g", linewidths=0.5, ax=ax)

    ax.set_xlabel("Hour of Day")
    ax.set_ylabel("")
    ax.set_title("Motion Events: Hour × Day of Week")

    plt.tight_layout()

    filepath = os.path.join(CHARTS_DIR, "heatmap_hour_day.png")
    plt.savefig(filepath, dpi=150)
    plt.close(fig)

    print(f"[Saved] Το γράφημα αποθηκεύτηκε: {filepath}")


def plot_latency_over_time(df):
    if "pipeline_latency_ms" not in df.columns or "timestamp" not in df.columns:
        print("[Skipped] Λείπουν απαραίτητες στήλες. Παράλειψη γραφήματος latency-over-time.")
        return

    fig, ax = plt.subplots(figsize=(10, 5))

    sns.scatterplot(
        data=df, x="timestamp", y="pipeline_latency_ms", 
        alpha=0.5, s=15, color="purple", ax=ax
    )

    ax.set_xlabel("Time")
    ax.set_ylabel("Pipeline Latency (ms)")
    ax.set_title("Pipeline Latency Over Time")

    plt.xticks(rotation=45)

    plt.tight_layout()

if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        filepath = sys.argv[1]
    else:
        filepath = "data/motion_events.jsonl"

    print(f"Φόρτωση δεδομένων από: {filepath}")

    df = load_events(filepath)

    print(f"Φορτώθηκαν {len(df)} συμβάντα.")

    if df.empty:
        print("Δεν βρέθηκαν δεδομένα. Παρακαλώ εκτελέστε πρώτα το pipeline.")
        sys.exit(1)

    plot_events_per_hour(df)
    plot_latency_distribution(df)
    plot_events_over_time(df)
    plot_heatmap(df)
    plot_latency_over_time(df)

    print(f"Όλα τα γραφήματα αποθηκεύτηκαν επιτυχώς στον φάκελο: {CHARTS_DIR}")