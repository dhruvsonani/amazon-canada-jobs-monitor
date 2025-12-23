from flask import Flask, jsonify, render_template_string
import json
import os
from datetime import datetime
from zoneinfo import ZoneInfo   # ✅ IST support

app = Flask(__name__)

IST = ZoneInfo("Asia/Kolkata")

# ======================
# FILES
# ======================
JOBS_FILE = "jobs_store.json"
NEW_JOBS_FILE = "new_jobs_log.json"
REQUEST_LOG_FILE = "request_log.json"
LAST_RUN_FILE = "last_run.json"
NEXT_RUN_FILE = "next_run.json"


# ======================
# HELPERS
# ======================
def load_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return default


def to_ist(iso_ts):
    """Convert ISO timestamp to IST-aware datetime"""
    if not iso_ts:
        return None
    try:
        dt = datetime.fromisoformat(iso_ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=ZoneInfo("UTC"))
        return dt.astimezone(IST)
    except Exception:
        return None


def human_ago(iso_ts):
    """
    Convert ISO timestamp to 'X sec/min ago' (IST)
    """
    t = to_ist(iso_ts)
    if not t:
        return "N/A"

    now = datetime.now(IST)
    seconds = int((now - t).total_seconds())

    if seconds < 60:
        return f"{seconds} sec ago"
    elif seconds < 3600:
        return f"{seconds // 60} min ago"
    else:
        return f"{seconds // 3600} hr ago"


def next_run_seconds():
    data = load_json(NEXT_RUN_FILE, {})
    t = to_ist(data.get("next_run"))
    if not t:
        return "N/A"

    now = datetime.now(IST)
    return max(0, int((t - now).total_seconds()))


def calculate_health(request_logs, window=50):
    if not request_logs:
        return 0, "N/A"

    recent = request_logs[:window]
    total = len(recent)
    ok = sum(1 for r in recent if r.get("status") == "OK")

    score = int((ok / total) * 100)

    if score >= 90:
        label = "Healthy"
    elif score >= 70:
        label = "Degraded"
    else:
        label = "Unhealthy"

    return score, label


# ======================
# ROUTES
# ======================
@app.route("/")
def dashboard():
    jobs = load_json(JOBS_FILE, [])
    new_jobs = load_json(NEW_JOBS_FILE, [])
    request_logs = load_json(REQUEST_LOG_FILE, [])[::-1][:100]

    last_run_iso = load_json(LAST_RUN_FILE, {}).get("last_run")
    last_check = human_ago(last_run_iso)
    next_run = next_run_seconds()

    health_score, health_label = calculate_health(request_logs)

    html = """
    <!doctype html>
    <html>
    <head>
      <meta name="viewport" content="width=device-width, initial-scale=1">
      <title>Amazon Jobs Monitor</title>
      <style>
        body { font-family: Arial; background:#f3f3f3; margin:0 }
        .card { background:#fff; margin:10px; padding:15px; border-radius:10px }
        .ok { color:green }
        .err { color:red }
        .warn { color:orange }
        table { width:100%; border-collapse:collapse }
        td { padding:4px 0; font-size:14px }
      </style>
    </head>
    <body>

      <div class="card">
        <h2>🇨🇦 Amazon Jobs Monitor</h2>
        <div><b>Last check (IST):</b> {{ last_check }}</div>
        <div><b>Next run in:</b> {{ next_run }} seconds</div>
        <div>
          <b>Request health:</b>
          <span style="font-weight:bold;
            color:{% if health_label=='Healthy' %}green
                  {% elif health_label=='Degraded' %}orange
                  {% else %}red{% endif %}">
            {{ health_score }}% ({{ health_label }})
          </span>
        </div>
      </div>

      <div class="card">
        <b>Total jobs:</b> {{ total }}<br>
        <b>New jobs:</b> {{ new_count }}
      </div>

      <div class="card">
        <h3>🧾 API Call Request Status (IST)</h3>
        <div style="max-height:320px; overflow-y:auto;">
          <table>
            {% for r in request_logs %}
            <tr>
              <td>{{ r.time.split("T")[1][:8] }}</td>
              <td>{{ r.city }}</td>
              <td class="{% if r.status=='OK' %}ok
                         {% elif 'HTTP' in r.status %}err
                         {% else %}warn{% endif %}">
                {{ r.status }}
              </td>
            </tr>
            {% endfor %}
          </table>
        </div>
      </div>

    </body>
    </html>
    """

    return render_template_string(
        html,
        last_check=last_check,
        next_run=next_run,
        health_score=health_score,
        health_label=health_label,
        total=len(jobs),
        new_count=sum(len(x.get("new", [])) for x in new_jobs),
        request_logs=request_logs,
    )


@app.route("/api/jobs")
def api_jobs():
    return jsonify(load_json(JOBS_FILE, []))


@app.route("/api/request-log")
def api_request_log():
    return jsonify(load_json(REQUEST_LOG_FILE, []))


# ======================
# ENTRY POINT
# ======================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
