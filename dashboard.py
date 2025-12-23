from flask import Flask, render_template_string
import json
import os

app = Flask(__name__)

SLEEP_STATE_FILE = "sleep_state.json"
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


@app.route("/")
def dashboard():
    sleep_state = load_json(SLEEP_STATE_FILE, {})
    logs = load_json(REQUEST_LOG_FILE, [])[::-1][:100]
    jobs = load_json(JOBS_FILE, [])
    new_jobs = load_json(NEW_JOBS_FILE, [])

    is_sleeping = sleep_state.get("sleeping", False)

    html = """
    <!doctype html>
    <html>
    <head>
      <meta name="viewport" content="width=device-width, initial-scale=1">
      <meta http-equiv="refresh" content="15">
      <title>Amazon Jobs Monitor</title>

      <style>
        body {
          margin: 0;
          font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial;
          background: #f4f6f8;
          color: #1f2937;
        }

        header {
          background: #111827;
          color: white;
          padding: 16px 20px;
          position: sticky;
          top: 0;
          z-index: 10;
        }

        header h1 {
          margin: 0;
          font-size: 20px;
          font-weight: 600;
        }

        header span {
          font-size: 13px;
          opacity: 0.8;
        }

        .container {
          padding: 20px;
          max-width: 1100px;
          margin: auto;
        }

        .status-card {
          background: white;
          border-radius: 10px;
          padding: 20px;
          margin-bottom: 20px;
          display: flex;
          justify-content: space-between;
          align-items: center;
          box-shadow: 0 4px 10px rgba(0,0,0,0.05);
        }

        .badge {
          padding: 6px 14px;
          border-radius: 999px;
          font-weight: 600;
          font-size: 13px;
        }

        .badge.green {
          background: #dcfce7;
          color: #166534;
        }

        .badge.red {
          background: #fee2e2;
          color: #991b1b;
        }

        .grid {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
          gap: 16px;
          margin-bottom: 20px;
        }

        .metric {
          background: white;
          padding: 18px;
          border-radius: 10px;
          box-shadow: 0 4px 10px rgba(0,0,0,0.05);
        }

        .metric h3 {
          margin: 0;
          font-size: 14px;
          color: #6b7280;
          font-weight: 500;
        }

        .metric p {
          margin: 6px 0 0;
          font-size: 22px;
          font-weight: 600;
        }

        .log-card {
          background: white;
          border-radius: 10px;
          box-shadow: 0 4px 10px rgba(0,0,0,0.05);
          overflow: hidden;
        }

        .log-card h3 {
          margin: 0;
          padding: 16px;
          font-size: 16px;
          border-bottom: 1px solid #e5e7eb;
        }

        .logs {
          max-height: 420px;
          overflow-y: auto;
          font-size: 13px;
        }

        .log-row {
          display: grid;
          grid-template-columns: 80px 1fr 120px;
          gap: 10px;
          padding: 10px 16px;
          border-bottom: 1px solid #f1f5f9;
        }

        .log-row:last-child {
          border-bottom: none;
        }

        .ok { color: #15803d; font-weight: 600; }
        .err { color: #b91c1c; font-weight: 600; }
        .warn { color: #d97706; font-weight: 600; }
      </style>
    </head>

    <body>

      <header>
        <h1>🇨🇦 Amazon Jobs Monitor</h1>
        <span>Railway Deployment</span>
      </header>

      <div class="container">

        <div class="status-card">
          <div>
            <h2 style="margin:0;font-size:18px">
              System Status
            </h2>
            {% if is_sleeping %}
              <p style="margin:4px 0;color:#6b7280">
                Sleeping due to 403 — redeploy to resume
              </p>
            {% else %}
              <p style="margin:4px 0;color:#6b7280">
                Monitoring active
              </p>
            {% endif %}
          </div>

          {% if is_sleeping %}
            <span class="badge red">SLEEPING</span>
          {% else %}
            <span class="badge green">RUNNING</span>
          {% endif %}
        </div>

        {% if is_sleeping %}
        <div class="metric" style="margin-bottom:20px">
          <h3>Sleep Window</h3>
          <p>
            Since: {{ sleep_state.since }} <br>
            Wake at: {{ sleep_state.wake_at }}
          </p>
        </div>
        {% endif %}

        <div class="grid">
          <div class="metric">
            <h3>Total Jobs</h3>
            <p>{{ total }}</p>
          </div>
          <div class="metric">
            <h3>New Jobs Logged</h3>
            <p>{{ new_count }}</p>
          </div>
          <div class="metric">
            <h3>Recent Requests</h3>
            <p>{{ logs|length }}</p>
          </div>
        </div>

        <div class="log-card">
          <h3>Request Log</h3>
          <div class="logs">
            {% for r in logs %}
            <div class="log-row">
              <div>{{ r.time.split("T")[1][:8] }}</div>
              <div>{{ r.city }}</div>
              <div class="
                {% if r.status == 'OK' %}ok
                {% elif '403' in r.status %}err
                {% else %}warn{% endif %}
              ">
                {{ r.status }}
              </div>
            </div>
            {% endfor %}
          </div>
        </div>

      </div>

    </body>
    </html>
    """

    return render_template_string(
        html,
        sleep_state=sleep_state,
        is_sleeping=is_sleeping,
        total=len(jobs),
        new_count=sum(len(x.get("new", [])) for x in new_jobs),
        logs=logs,
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
