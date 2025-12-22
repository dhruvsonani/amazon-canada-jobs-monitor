from flask import Flask, jsonify, render_template_string
import json
import os
from datetime import datetime, timezone

app = Flask(__name__)

JOBS_FILE = "jobs_store.json"
NEW_JOBS_FILE = "new_jobs_log.json"
REQUEST_LOG_FILE = "request_log.json"
LAST_RUN_FILE = "last_run.json"
NEXT_RUN_FILE = "next_run.json"


def load(path, default):
    if not os.path.exists(path):
        return default
    return json.load(open(path))


def human_ago(ts):
    t = datetime.fromisoformat(ts).replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    sec = int((now - t).total_seconds())
    if sec < 60:
        return f"{sec} sec ago"
    return f"{sec // 60} min ago"


def next_run_seconds():
    if not os.path.exists(NEXT_RUN_FILE):
        return "N/A"
    t = datetime.fromisoformat(load(NEXT_RUN_FILE, {})["next_run"]).replace(tzinfo=timezone.utc)
    return max(0, int((t - datetime.now(timezone.utc)).total_seconds()))


def calculate_health(logs, window=50):
    if not logs:
        return 0, "N/A"
    recent = logs[:window]
    ok = sum(1 for r in recent if r["status"] == "OK")
    score = int((ok / len(recent)) * 100)

    if score >= 90:
        label = "Healthy"
    elif score >= 70:
        label = "Degraded"
    else:
        label = "Unhealthy"

    return score, label


@app.route("/")
def dashboard():
    jobs = load(JOBS_FILE, [])
    new_jobs = load(NEW_JOBS_FILE, [])
    logs = load(REQUEST_LOG_FILE, [])[::-1][:100]

    last_check = human_ago(load(LAST_RUN_FILE, {}).get("last_run")) if os.path.exists(LAST_RUN_FILE) else "N/A"
    next_run = next_run_seconds()

    health_score, health_label = calculate_health(logs)

    html = """
    <html><head>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
      body { font-family: Arial; background:#f3f3f3 }
      .card { background:#fff; margin:10px; padding:15px; border-radius:10px }
      .ok { color:green }
      .err { color:red }
      .warn { color:orange }
      table { width:100% }
    </style>
    </head><body>

    <div class="card">
      <h2>🇨🇦 Amazon Jobs Monitor</h2>
      <div>Last check: {{ last_check }}</div>
      <div>Next run in: {{ next_run }} seconds</div>
      <div>
        Request health:
        <b style="color:{% if health_label=='Healthy' %}green{% elif health_label=='Degraded' %}orange{% else %}red{% endif %}">
          {{ health_score }}% ({{ health_label }})
        </b>
      </div>
    </div>

    <div class="card">
      <b>Total jobs:</b> {{ total }}<br>
      <b>New jobs:</b> {{ new_count }}
    </div>

    <div class="card">
      <h3>🧾 Request Status</h3>
      <div style="max-height:300px; overflow-y:auto">
        <table>
          {% for r in logs %}
          <tr>
            <td>{{ r.time.split("T")[1][:8] }}</td>
            <td>{{ r.city }}</td>
            <td class="{% if r.status=='OK' %}ok{% elif 'HTTP' in r.status %}err{% else %}warn{% endif %}">
              {{ r.status }}
            </td>
          </tr>
          {% endfor %}
        </table>
      </div>
    </div>

    </body></html>
    """

    return render_template_string(
        html,
        last_check=last_check,
        next_run=next_run,
        health_score=health_score,
        health_label=health_label,
        total=len(jobs),
        new_count=sum(len(x["new"]) for x in new_jobs),
        logs=logs,
    )


@app.route("/api/jobs")
def api_jobs():
    return jsonify(load(JOBS_FILE, []))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)

