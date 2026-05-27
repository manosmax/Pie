import base64
import io
import os
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path

import matplotlib
matplotlib.use("Agg")         
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
import pandas as pd
import seaborn as sns
from flask import Flask, redirect, render_template_string, request, send_from_directory, url_for


app = Flask(__name__)
UPLOAD_DIR  = Path("/app/data/uploads")
MODEL_DIR   = Path("/app/models_v_s")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
MODEL_DIR.mkdir(parents=True, exist_ok=True)

REQUIRED_COLS = {"day_of_week", "hour", "is_weekend", "event_count", "label"}
DAY_NAMES     = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


PALETTE = {"busy": "#D85A30", "quiet": "#1D9E75"}
sns.set_theme(style="whitegrid", font="DejaVu Sans", font_scale=1.1)
plt.rcParams.update({
    "axes.spines.top":    False,
    "axes.spines.right":  False,
    "figure.facecolor":   "white",
    "axes.facecolor":     "#FAFAF8",
    "grid.color":         "#E8E6E0",
    "axes.edgecolor":     "#D3D1C7",
    "text.color":         "#3d3d3a",
    "axes.labelcolor":    "#3d3d3a",
    "xtick.color":        "#5F5E5A",
    "ytick.color":        "#5F5E5A",
})




def fig_to_b64(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=130, bbox_inches="tight")
    buf.seek(0)
    encoded = base64.b64encode(buf.read()).decode()
    plt.close(fig)
    return encoded


def validate_csv(df: pd.DataFrame) -> list[str]:
    warnings = []
    missing = REQUIRED_COLS - set(df.columns)
    if missing:
        warnings.append(f"Missing columns: {', '.join(sorted(missing))}")
    if df.empty:
        warnings.append("File is empty.")
    if "label" in df.columns:
        bad = set(df["label"].dropna().unique()) - {"busy", "quiet"}
        if bad:
            warnings.append(f"Unexpected label values: {bad}")
    if "hour" in df.columns:
        if df["hour"].min() < 0 or df["hour"].max() > 23:
            warnings.append("hour column has values outside 0–23.")
    if "day_of_week" in df.columns:
        if df["day_of_week"].min() < 0 or df["day_of_week"].max() > 6:
            warnings.append("day_of_week column has values outside 0–6.")
    return warnings


def make_charts(df: pd.DataFrame) -> dict[str, str]:
    charts = {}

    
    fig, ax = plt.subplots(figsize=(4.5, 3.2))
    counts   = df["label"].value_counts().reindex(["busy", "quiet"], fill_value=0)
    bars     = ax.bar(counts.index, counts.values,
                      color=[PALETTE[l] for l in counts.index],
                      width=0.45, zorder=3)
    for bar, val in zip(bars, counts.values):
        ax.text(bar.get_x() + bar.get_width() / 2, val + 2,
                str(val), ha="center", va="bottom", fontsize=11, color="#3d3d3a")
    ax.set_title("Class balance", fontsize=13, fontweight="bold", pad=10)
    ax.set_ylabel("Rows")
    ax.set_xlabel("")
    ax.set_ylim(0, counts.max() * 1.15)
    charts["class_balance"] = fig_to_b64(fig)

    
    fig, ax = plt.subplots(figsize=(6, 3.5))
    for label, color in PALETTE.items():
        subset = df[df["label"] == label]["event_count"]
        if not subset.empty:
            sns.kdeplot(subset, ax=ax, color=color, fill=True,
                        alpha=0.35, linewidth=1.8, label=label.capitalize())
    ax.axvline(10, color="#888780", linewidth=1, linestyle="--", alpha=0.7)
    ax.text(10.4, ax.get_ylim()[1] * 0.9, "threshold = 10",
            fontsize=9, color="#888780")
    ax.set_title("Event count distribution", fontsize=13, fontweight="bold", pad=10)
    ax.set_xlabel("event_count")
    ax.set_ylabel("Density")
    ax.legend(frameon=False)
    charts["event_dist"] = fig_to_b64(fig)

    
    if {"hour", "is_weekend", "event_count"}.issubset(df.columns):
        fig, ax = plt.subplots(figsize=(8, 3.5))
        for is_wknd, label, color, ls in [
            (0, "Weekday", "#185FA5", "-"),
            (1, "Weekend", "#D85A30", "--"),
        ]:
            subset = df[df["is_weekend"] == is_wknd].groupby("hour")["event_count"].mean()
            ax.plot(subset.index, subset.values, color=color, linewidth=2,
                    linestyle=ls, label=label, marker="o", markersize=3.5)
        ax.set_title("Mean events by hour", fontsize=13, fontweight="bold", pad=10)
        ax.set_xlabel("Hour of day")
        ax.set_ylabel("Mean event count")
        ax.set_xticks(range(0, 24, 2))
        ax.legend(frameon=False)
        charts["hourly_pattern"] = fig_to_b64(fig)

    
    if {"hour", "day_of_week", "event_count"}.issubset(df.columns):
        pivot = (
            df.groupby(["day_of_week", "hour"])["event_count"]
            .mean()
            .unstack(level=1)
            .reindex(range(7))
        )
        pivot.index = [DAY_NAMES[i] if i < 7 else str(i) for i in pivot.index]
        pivot.columns = pivot.columns.astype(int)

        fig, ax = plt.subplots(figsize=(10, 3.2))
        sns.heatmap(
            pivot, ax=ax,
            cmap=sns.color_palette("YlOrRd", as_cmap=True),
            linewidths=0.3, linecolor="#F1EFE8",
            annot=False, cbar_kws={"shrink": 0.7, "label": "mean events"},
        )
        ax.set_title("Activity heatmap  (day × hour)", fontsize=13,
                     fontweight="bold", pad=10)
        ax.set_xlabel("Hour of day")
        ax.set_ylabel("")
        ax.tick_params(axis="x", rotation=0)
        ax.tick_params(axis="y", rotation=0)
        charts["heatmap"] = fig_to_b64(fig)

    
    if {"day_of_week", "label"}.issubset(df.columns):
        day_label = (
            df.groupby(["day_of_week", "label"])
            .size()
            .unstack(fill_value=0)
            .reindex(range(7), fill_value=0)
        )
        day_label.index = [DAY_NAMES[i] if i < 7 else str(i) for i in day_label.index]
        day_label = day_label.reindex(columns=["busy", "quiet"])

        fig, ax = plt.subplots(figsize=(6, 3.5))
        bottom = np.zeros(len(day_label))
        for col, color in PALETTE.items():
            if col in day_label.columns:
                ax.bar(day_label.index, day_label[col], bottom=bottom,
                       color=color, label=col.capitalize(), zorder=3, width=0.55)
                bottom += day_label[col].values
        ax.set_title("Busy vs quiet rows by day", fontsize=13,
                     fontweight="bold", pad=10)
        ax.set_ylabel("Row count")
        ax.set_xlabel("")
        ax.legend(frameon=False, loc="upper right")
        charts["day_balance"] = fig_to_b64(fig)

    return charts


def summary_stats(df: pd.DataFrame) -> dict:
    """Return a small dict of headline numbers for the dashboard."""
    stats = {
        "rows":          len(df),
        "busy_pct":      0,
        "quiet_pct":     0,
        "mean_events":   round(df["event_count"].mean(), 1) if "event_count" in df.columns else "–",
        "max_events":    int(df["event_count"].max())       if "event_count" in df.columns else "–",
        "unique_days":   int(df["day_of_week"].nunique())   if "day_of_week" in df.columns else "–",
    }
    if "label" in df.columns:
        vc = df["label"].value_counts(normalize=True) * 100
        stats["busy_pct"]  = round(vc.get("busy",  0), 1)
        stats["quiet_pct"] = round(vc.get("quiet", 0), 1)
    return stats




PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Training Data Upload — Smart Wastebin</title>
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  :root {
    --bg:        #F8F7F3;
    --surface:   #FFFFFF;
    --border:    #E0DED6;
    --text:      #2C2C2A;
    --muted:     #5F5E5A;
    --accent:    #185FA5;
    --busy:      #D85A30;
    --quiet:     #1D9E75;
    --radius:    10px;
    --shadow:    0 1px 4px rgba(0,0,0,.07);
  }

  body { background: var(--bg); color: var(--text);
         font-family: system-ui, sans-serif; font-size: 15px;
         line-height: 1.6; padding: 0 0 60px; }

  header { background: var(--surface); border-bottom: 1px solid var(--border);
           padding: 18px 32px; display: flex; align-items: center;
           justify-content: space-between; }
  header h1 { font-size: 17px; font-weight: 600; color: var(--text); }
  header span { font-size: 13px; color: var(--muted); }

  .wrap { max-width: 1060px; margin: 0 auto; padding: 28px 24px 0; }

  /* ── stat pills ── */
  .stats { display: flex; gap: 14px; flex-wrap: wrap; margin-bottom: 28px; }
  .stat  { background: var(--surface); border: 1px solid var(--border);
           border-radius: var(--radius); padding: 14px 20px;
           min-width: 130px; box-shadow: var(--shadow); }
  .stat .val { font-size: 26px; font-weight: 700; line-height: 1; color: var(--accent); }
  .stat .lbl { font-size: 12px; color: var(--muted); margin-top: 4px; }

  /* ── upload card ── */
  .card { background: var(--surface); border: 1px solid var(--border);
          border-radius: var(--radius); padding: 24px 28px;
          margin-bottom: 28px; box-shadow: var(--shadow); }
  .card h2 { font-size: 15px; font-weight: 600; margin-bottom: 16px; }

  .drop-zone { border: 2px dashed var(--border); border-radius: 8px;
               padding: 36px; text-align: center; cursor: pointer;
               transition: border-color .2s, background .2s; }
  .drop-zone:hover, .drop-zone.over { border-color: var(--accent);
                                      background: #EFF6FF; }
  .drop-zone input[type=file] { display: none; }
  .drop-zone .hint { color: var(--muted); font-size: 13px; margin-top: 8px; }
  .drop-zone .icon { font-size: 36px; line-height: 1; margin-bottom: 8px;
                     color: var(--accent); }

  .btn { display: inline-block; padding: 9px 20px; border-radius: 7px;
         font-size: 14px; font-weight: 600; cursor: pointer; border: none;
         transition: opacity .15s; }
  .btn-primary { background: var(--accent); color: #fff; }
  .btn-success { background: var(--quiet); color: #fff; }
  .btn-danger  { background: var(--busy);  color: #fff; }
  .btn:hover   { opacity: .88; }

  .btn-row { display: flex; gap: 10px; flex-wrap: wrap; margin-top: 16px; }

  /* ── alerts ── */
  .alert { padding: 12px 16px; border-radius: 8px; font-size: 13px;
           margin-bottom: 20px; border-left: 4px solid; }
  .alert-ok   { background: #EAF6F0; border-color: var(--quiet); color: #0F6E56; }
  .alert-warn { background: #FEF3CD; border-color: #BA7517; color: #633806; }
  .alert-err  { background: #FAECE7; border-color: var(--busy); color: #4A1B0C; }

  /* ── charts grid ── */
  .charts { display: grid;
            grid-template-columns: repeat(auto-fit, minmax(420px, 1fr));
            gap: 20px; margin-bottom: 28px; }
  .chart-card { background: var(--surface); border: 1px solid var(--border);
                border-radius: var(--radius); padding: 20px;
                box-shadow: var(--shadow); }
  .chart-card h3 { font-size: 13px; font-weight: 600; color: var(--muted);
                   text-transform: uppercase; letter-spacing: .04em;
                   margin-bottom: 14px; }
  .chart-card img { width: 100%; height: auto; display: block;
                    border-radius: 6px; }

  /* full-width chart cards */
  .chart-full { grid-column: 1 / -1; }

  /* ── file list ── */
  table { width: 100%; border-collapse: collapse; font-size: 13px; }
  th { background: #F1EFE8; font-weight: 600; padding: 9px 12px;
       text-align: left; border-bottom: 1px solid var(--border); }
  td { padding: 8px 12px; border-bottom: 1px solid #F1EFE8; }
  tr:hover td { background: #FAFAF8; }
  a { color: var(--accent); text-decoration: none; }
  a:hover { text-decoration: underline; }

  /* progress bar while uploading */
  #progress-wrap { display: none; margin-top: 14px; }
  #progress-bar { height: 6px; background: var(--border); border-radius: 3px; overflow: hidden; }
  #progress-fill { height: 100%; width: 0%; background: var(--accent);
                   transition: width .3s; border-radius: 3px; }

  /* retrain status */
  #retrain-status { display: none; font-size: 13px; color: var(--muted);
                    margin-top: 10px; }
</style>
</head>
<body>

<header>
  <h1>📦 Training Data Upload</h1>
  <span>Smart Wastebin — virtual sensor retraining</span>
</header>

<div class="wrap">

  {% if message %}
  <div class="alert {{ 'alert-ok' if ok else 'alert-err' }}">{{ message }}</div>
  {% endif %}

  {% if warnings %}
  {% for w in warnings %}
  <div class="alert alert-warn">⚠ {{ w }}</div>
  {% endfor %}
  {% endif %}

  <!-- upload card -->
  <div class="card">
    <h2>Upload new training CSV</h2>
    <form id="upload-form" method="POST" action="/upload" enctype="multipart/form-data">
      <div class="drop-zone" id="drop-zone" onclick="document.getElementById('file-input').click()">
        <div class="icon">⬆</div>
        <div><strong id="file-label">Click to choose or drag &amp; drop</strong></div>
        <div class="hint">Accepts .csv — columns: day_of_week, hour, is_weekend, event_count, label</div>
        <input type="file" id="file-input" name="file" accept=".csv"
               onchange="updateLabel(this)">
      </div>
      <div id="progress-wrap">
        <div id="progress-bar"><div id="progress-fill"></div></div>
      </div>
      <div class="btn-row">
        <button type="submit" class="btn btn-primary">Upload &amp; visualise</button>
        {% if files %}
        <button type="button" class="btn btn-success" onclick="triggerRetrain()">
          Retrain model with latest file
        </button>
        {% endif %}
      </div>
    </form>
    <div id="retrain-status"></div>
  </div>

  <!-- stats -->
  {% if stats %}
  <div class="stats">
    <div class="stat"><div class="val">{{ stats.rows }}</div><div class="lbl">Total rows</div></div>
    <div class="stat"><div class="val">{{ stats.busy_pct }}%</div><div class="lbl">Busy label</div></div>
    <div class="stat"><div class="val">{{ stats.quiet_pct }}%</div><div class="lbl">Quiet label</div></div>
    <div class="stat"><div class="val">{{ stats.mean_events }}</div><div class="lbl">Mean events/hour</div></div>
    <div class="stat"><div class="val">{{ stats.max_events }}</div><div class="lbl">Peak events</div></div>
    <div class="stat"><div class="val">{{ stats.unique_days }}</div><div class="lbl">Day types</div></div>
  </div>
  {% endif %}

  <!-- charts -->
  {% if charts %}
  <div class="charts">
    {% if charts.class_balance %}
    <div class="chart-card">
      <h3>Class balance</h3>
      <img src="data:image/png;base64,{{ charts.class_balance }}" alt="Class balance chart">
    </div>
    {% endif %}

    {% if charts.event_dist %}
    <div class="chart-card">
      <h3>Event count distribution</h3>
      <img src="data:image/png;base64,{{ charts.event_dist }}" alt="Event count distribution">
    </div>
    {% endif %}

    {% if charts.day_balance %}
    <div class="chart-card">
      <h3>Labels by day of week</h3>
      <img src="data:image/png;base64,{{ charts.day_balance }}" alt="Label by day">
    </div>
    {% endif %}

    {% if charts.hourly_pattern %}
    <div class="chart-card chart-full">
      <h3>Mean events by hour — weekday vs weekend</h3>
      <img src="data:image/png;base64,{{ charts.hourly_pattern }}" alt="Hourly pattern">
    </div>
    {% endif %}

    {% if charts.heatmap %}
    <div class="chart-card chart-full">
      <h3>Activity heatmap — day × hour</h3>
      <img src="data:image/png;base64,{{ charts.heatmap }}" alt="Heatmap">
    </div>
    {% endif %}
  </div>
  {% endif %}

  <!-- file list -->
  {% if files %}
  <div class="card">
    <h2>Saved training files</h2>
    <table>
      <thead><tr><th>Filename</th><th>Size</th><th></th></tr></thead>
      <tbody>
        {% for f in files %}
        <tr>
          <td>{{ f.name }}</td>
          <td>{{ f.size }}</td>
          <td><a href="/uploads/{{ f.name }}">Download</a></td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
  {% endif %}

</div><!-- /wrap -->

<script>
/* drag-and-drop styling */
const dz = document.getElementById('drop-zone');
dz.addEventListener('dragover',  e => { e.preventDefault(); dz.classList.add('over'); });
dz.addEventListener('dragleave', () => dz.classList.remove('over'));
dz.addEventListener('drop', e => {
  e.preventDefault();
  dz.classList.remove('over');
  const fi = document.getElementById('file-input');
  fi.files = e.dataTransfer.files;
  updateLabel(fi);
});

function updateLabel(input) {
  const lbl = document.getElementById('file-label');
  lbl.textContent = input.files.length ? input.files[0].name : 'Click to choose or drag & drop';
}

/* fake upload progress bar */
document.getElementById('upload-form').addEventListener('submit', () => {
  const wrap = document.getElementById('progress-wrap');
  const fill = document.getElementById('progress-fill');
  wrap.style.display = 'block';
  let pct = 0;
  const iv = setInterval(() => {
    pct = Math.min(pct + Math.random() * 18, 92);
    fill.style.width = pct + '%';
    if (pct >= 92) clearInterval(iv);
  }, 200);
});

/* retrain via fetch */
function triggerRetrain() {
  const status = document.getElementById('retrain-status');
  status.style.display = 'block';
  status.textContent = '⏳ Retraining model — this may take a few seconds…';
  fetch('/retrain', { method: 'POST' })
    .then(r => r.json())
    .then(d => {
      status.textContent = d.ok
        ? '✅ Model retrained successfully! New model saved to models_v_s/busy_predictor.joblib'
        : '❌ Retraining failed: ' + (d.error || 'unknown error');
    })
    .catch(() => { status.textContent = '❌ Request failed — is the service running?'; });
}
</script>
</body>
</html>
"""




def _file_list():
    rows = []
    for p in sorted(UPLOAD_DIR.glob("*.csv"), reverse=True):
        size_kb = p.stat().st_size / 1024
        rows.append({"name": p.name,
                     "size": f"{size_kb:.1f} KB" if size_kb < 1024
                              else f"{size_kb/1024:.1f} MB"})
    return rows


@app.route("/", methods=["GET"])
def index():
    return render_template_string(
        PAGE,
        files=_file_list(),
        charts={}, stats=None,
        message=None, ok=True, warnings=[],
    )


@app.route("/upload", methods=["POST"])
def upload():
    if "file" not in request.files:
        return render_template_string(
            PAGE, files=_file_list(), charts={}, stats=None,
            message="No file field in request.", ok=False, warnings=[],
        )

    f = request.files["file"]
    if not f.filename.endswith(".csv"):
        return render_template_string(
            PAGE, files=_file_list(), charts={}, stats=None,
            message="Only .csv files are accepted.", ok=False, warnings=[],
        )

    
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    safe_name = f"{timestamp}_{uuid.uuid4().hex[:8]}.csv"
    save_path = UPLOAD_DIR / safe_name
    f.save(save_path)

    
    try:
        df = pd.read_csv(save_path)
    except Exception as exc:
        return render_template_string(
            PAGE, files=_file_list(), charts={}, stats=None,
            message=f"Could not parse CSV: {exc}", ok=False, warnings=[],
        )

    warnings = validate_csv(df)
    charts   = {} if warnings and "Missing columns" in warnings[0] else make_charts(df)
    stats    = summary_stats(df)

    return render_template_string(
        PAGE,
        files=_file_list(),
        charts=charts,
        stats=stats,
        message=f"✓ File saved as {safe_name} ({len(df):,} rows).",
        ok=True,
        warnings=warnings,
    )


@app.route("/uploads/<path:filename>")
def download(filename):
    return send_from_directory(UPLOAD_DIR, filename, as_attachment=True)


@app.route("/retrain", methods=["POST"])
def retrain():
    
    csv_files = sorted(UPLOAD_DIR.glob("*.csv"), reverse=True)
    if not csv_files:
        return {"ok": False, "error": "No CSV files uploaded yet."}, 400

    latest = csv_files[0]
    try:
        
        import sys
        sys.path.insert(0, "/app")
        from train_model import generate_training_data, train_and_save  # noqa: F401

        df = pd.read_csv(latest)
        warnings = validate_csv(df)
        if any("Missing columns" in w for w in warnings):
            return {"ok": False, "error": "; ".join(warnings)}, 400

        
        from sklearn.ensemble import RandomForestClassifier
        from sklearn.model_selection import train_test_split
        from sklearn.metrics import classification_report
        import joblib

        X = df[["day_of_week", "hour", "is_weekend"]]
        y = df["label"]
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42
        )
        clf = RandomForestClassifier(n_estimators=50, random_state=42)
        clf.fit(X_train, y_train)
        report = classification_report(y_test, clf.predict(X_test), output_dict=True)
        model_path = MODEL_DIR / "busy_predictor.joblib"
        joblib.dump(clf, model_path)

        acc = round(report["accuracy"] * 100, 1)
        return {
            "ok": True,
            "accuracy": acc,
            "model_path": str(model_path),
            "source_csv": latest.name,
            "rows_used": len(df),
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}, 500



if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=False)
