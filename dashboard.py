from flask import Flask, jsonify, render_template_string
import json
import os
from datetime import datetime, timezone

app = Flask(__name__)

JOBS_FILE = "jobs_store.json"
NEW_JOBS_FILE = "new_jobs_log.json"
LAST_RUN_FILE = "last_run.json"


def load_json(path):
    if not os.path.exists(path):
        return []
    with open(path, "r") as f:
        return json.load(f)


def humanize_last_run():
    if not os.path.exists(LAST_RUN_FILE):
        return "N/A"

    try:
        with open(LAST_RUN_FILE, "r") as f:
            ts = json.load(f).get("last_run")
            if not ts:
                return "N/A"

        last_run = datetime.fromisoformat(ts).replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        delta = (now - last_run).total_seconds()

        if delta < 60:
            return f"{int(delta)} seconds ago"
        elif delta < 3600:
            return f"{int(delta // 60)} minutes ago"
        else:
            return f"{int(delta // 3600)} hours ago"

    except Exception:
        return "N/A"


@app.route("/")
def dashboard():
    jobs = load_json(JOBS_FILE)
    new_jobs = load_json(NEW_JOBS_FILE)
    last_check = humanize_last_run()

    cities = {}
    for job in jobs:
        city = job.get("city", "Unknown")
        cities[city] = cities.get(city, 0) + 1

    html = """
    <!doctype html>
    <html>
    <head>
      <meta name="viewport" content="width=device-width, initial-scale=1">
      <title>Amazon Jobs Monitor</title>
      <style>
        body { font-family: Arial; background:#f3f3f3; margin:0 }
        .card { background:#fff; margin:10px; padding:15px; border-radius:10px }
        .count { font-size:28px; font-weight:bold }
        table { width:100%; border-collapse:collapse }
        td { padding:6px 0; border-bottom:1px solid #eee }
      </style>
    </head>
    <body>

      <div class="card">
        <h2>🇨🇦 Amazon Jobs Monitor</h2>
        <div>Last check: {{ last_check }}</div>
      </div>

      <div class="card">
        <div class="count">{{ total }}</div>
        <div>Total jobs collected</div>
      </div>

      <div class="card">
        <div class="count">{{ new_count }}</div>
        <div>New jobs detected</div>
      </div>

      <div class="card">
        <h3>📍 Jobs by City</h3>
        <table>
          {% for city, count in cities.items() %}
          <tr>
            <td>{{ city }}</td>
            <td style="text-align:right">{{ count }}</td>
          </tr>
          {% endfor %}
        </table>
      </div>

    </body>
    </html>
    """

    return render_template_string(
        html,
        total=len(jobs),
        new_count=sum(len(x.get("new", [])) for x in new_jobs),
        cities=dict(sorted(cities.items(), key=lambda x: -x[1])),
        last_check=last_check,
    )


@app.route("/api/jobs")
def api_jobs():
    return jsonify(load_json(JOBS_FILE))


@app.route("/api/new-jobs")
def api_new_jobs():
    return jsonify(load_json(NEW_JOBS_FILE))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
