from flask import Flask, render_template_string
import json
import os
from datetime import datetime
from zoneinfo import ZoneInfo

app = Flask(__name__)
IST = ZoneInfo("Asia/Kolkata")

AUTH_STATE_FILE = "auth_state.json"
REQUEST_LOG_FILE = "request_log.json"
JOBS_FILE = "jobs_store.json"
NEW_JOBS_FILE = "new_jobs_log.json"


def load_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        return json.load(open(path))
    except Exception:
        return default


def human_ago(ts):
    if not ts:
        return "N/A"
    t = datetime.fromisoformat(ts).astimezone(IST)
    diff = int((datetime.now(IST) - t).total_seconds())
    if diff < 60:
        return f"{diff}s ago"
    if diff < 3600:
        return f"{diff//60}m ago"
    return f"{diff//3600}h ago"


@app.route("/")
def dashboard():
    auth = load_json(AUTH_STATE_FILE, {})
    logs = load_json(REQUEST_LOG_FILE, [])[::-1][:50]
    jobs = load_json(JOBS_FILE, [])
    new_jobs = load_json(NEW_JOBS_FILE, [])

    html = """
    <html>
    <head>
      <meta http-equiv="refresh" content="10">
    </head>
    <body style="font-family:Arial;background:#f3f3f3">

    {% if auth.state == 'paused' %}
    <div style="background:#ffe5e5;padding:15px;border:2px solid red">
      <h3>⛔ MONITOR PAUSED</h3>
      <div>Status: {{ auth.status }}</div>
      <div>Time: {{ auth.time }}</div>
      <b>Update AMAZON_AUTH_TOKEN — auto resume enabled</b>
    </div>
    {% endif %}

    <div style="background:#fff;padding:15px;margin-top:10px">
      <b>Total jobs:</b> {{ total }}<br>
      <b>New jobs:</b> {{ new_count }}
    </div>

    <div style="background:#fff;padding:15px;margin-top:10px">
      <h3>Request Log</h3>
      {% for r in logs %}
        {{ r.time.split("T")[1][:8] }} — {{ r.city }} — {{ r.status }}<br>
      {% endfor %}
    </div>

    </body>
    </html>
    """

    return render_template_string(
        html,
        auth=auth,
        total=len(jobs),
        new_count=sum(len(x.get("new", [])) for x in new_jobs),
        logs=logs,
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
