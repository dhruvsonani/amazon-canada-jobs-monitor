import requests
import json
import time
import os
import random
import smtplib
from email.message import EmailMessage
from datetime import datetime, timedelta, timezone
from threading import Thread

import dashboard

API_URL = "https://e5mquma77feepi2bdn4d6h3mpu.appsync-api.us-east-1.amazonaws.com/graphql"
INTERVAL_SECONDS = 210

# ======================
# FILES
# ======================
JOBS_FILE = "jobs_store.json"
NEW_JOBS_FILE = "new_jobs_log.json"
REQUEST_LOG_FILE = "request_log.json"
LAST_RUN_FILE = "last_run.json"
NEXT_RUN_FILE = "next_run.json"
SLEEP_STATE_FILE = "sleep_state.json"

# ======================
# EMAIL CONFIG (NO SILENT DISABLE)
# ======================
SMTP_HOST = "smtp.office365.com"
SMTP_PORT = 587
SMTP_USER = os.getenv("ALERT_EMAIL_USER")
SMTP_PASS = os.getenv("ALERT_EMAIL_PASS")
SMTP_TO = os.getenv("ALERT_EMAIL_TO")

# ======================
# INIT FILES
# ======================
for f, default in [
    (JOBS_FILE, []),
    (NEW_JOBS_FILE, []),
    (REQUEST_LOG_FILE, []),
]:
    if not os.path.exists(f):
        json.dump(default, open(f, "w"))

if not os.path.exists(SLEEP_STATE_FILE):
    json.dump({}, open(SLEEP_STATE_FILE, "w"))

# ======================
# CITIES
# ======================
CANADA_CITIES = [
    ("Toronto", 43.6532, -79.3832),
    ("Ottawa", 45.4215, -75.6972),
    ("Montreal", 45.5017, -73.5673),
    ("Vancouver", 49.2827, -123.1207),
    ("Calgary", 51.0447, -114.0719),
]

# ======================
# HELPERS
# ======================
def write_json(path, data):
    json.dump(data, open(path, "w"), indent=2)


def log_request(city, status):
    logs = json.load(open(REQUEST_LOG_FILE))
    logs.append({
        "time": datetime.now(timezone.utc).isoformat(),
        "city": city,
        "status": status,
    })
    write_json(REQUEST_LOG_FILE, logs[-500:])


def update_run_times():
    now = datetime.now(timezone.utc)
    write_json(LAST_RUN_FILE, {"last_run": now.isoformat()})
    write_json(NEXT_RUN_FILE, {"next_run": (now + timedelta(seconds=INTERVAL_SECONDS)).isoformat()})


def get_auth_token():
    token = os.getenv("AMAZON_AUTH_TOKEN")
    if not token:
        raise RuntimeError("AMAZON_AUTH_TOKEN missing")
    return token.strip()


# ======================
# EMAIL (FORCED + LOGGED)
# ======================
def send_email(subject, body):
    try:
        if not SMTP_USER or not SMTP_PASS or not SMTP_TO:
            raise RuntimeError("SMTP env vars missing")

        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = SMTP_USER
        msg["To"] = SMTP_TO
        msg.set_content(body)

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as s:
            s.starttls()
            s.login(SMTP_USER, SMTP_PASS)
            s.send_message(msg)

        print("📧 Email sent successfully")

    except Exception as e:
        print("❌ EMAIL FAILED:", repr(e))
        log_request("SYSTEM", f"EMAIL_FAILED:{type(e).__name__}")


# ======================
# SLEEP STATE
# ======================
def get_sleep_state():
    return json.load(open(SLEEP_STATE_FILE))


def set_sleep_state(token):
    hours = random.randint(6, 12)
    now = datetime.now(timezone.utc)

    state = {
        "sleeping": True,
        "reason": "403",
        "since": now.isoformat(),
        "wake_at": (now + timedelta(hours=hours)).isoformat(),
        "token_snapshot": token,
    }
    write_json(SLEEP_STATE_FILE, state)

    send_email(
        "⚠️ Amazon Jobs Monitor – Sleeping (403)",
        f"""403 detected.

System sleeping for {hours} hours.
Will resume automatically if token changes.

Time: {now.isoformat()}
"""
    )


def clear_sleep_state():
    write_json(SLEEP_STATE_FILE, {})


def sleep_or_resume():
    while True:
        state = get_sleep_state()
        if not state.get("sleeping"):
            return

        current_token = os.getenv("AMAZON_AUTH_TOKEN", "").strip()
        if current_token and current_token != state.get("token_snapshot"):
            print("🔓 Token updated — resuming immediately")
            clear_sleep_state()
            return

        if datetime.now(timezone.utc) >= datetime.fromisoformat(state["wake_at"]):
            print("⏰ Sleep window expired — resuming")
            clear_sleep_state()
            return

        time.sleep(60)


# ======================
# FETCH
# ======================
def fetch_jobs(city, lat, lng):
    token = get_auth_token()

    headers = {
        "content-type": "application/json",
        "country": "Canada",
        "origin": "https://hiring.amazon.ca",
        "referer": "https://hiring.amazon.ca/",
        "user-agent": "Mozilla/5.0",
        "Authorization": token,
    }

    payload = {
        "operationName": "searchJobCardsByLocation",
        "variables": {
            "searchJobRequest": {
                "locale": "en-CA",
                "country": "Canada",
                "pageSize": 100,
                "geoQueryClause": {
                    "lat": lat,
                    "lng": lng,
                    "unit": "km",
                    "distance": 100,
                },
            }
        },
        "query": """query searchJobCardsByLocation($searchJobRequest: SearchJobRequest!) {
            searchJobCardsByLocation(searchJobRequest: $searchJobRequest) {
                jobCards { jobId jobTitle city state }
            }
        }""",
    }

    r = requests.post(API_URL, headers=headers, json=payload, timeout=(10, 30))

    if r.status_code == 403:
        set_sleep_state(token)
        log_request(city, "403_SLEEP")
        return []

    if r.status_code != 200:
        log_request(city, f"HTTP_{r.status_code}")
        return []

    log_request(city, "OK")
    return r.json()["data"]["searchJobCardsByLocation"]["jobCards"]


# ======================
# CRAWLER
# ======================
def crawler():
    seen = set(j.get("jobId") for j in json.load(open(JOBS_FILE)) if j.get("jobId"))

    while True:
        if get_sleep_state().get("sleeping"):
            sleep_or_resume()
            continue

        update_run_times()
        new_jobs = []

        for city, lat, lng in CANADA_CITIES:
            jobs = fetch_jobs(city, lat, lng)
            for job in jobs:
                jid = job.get("jobId")
                if jid and jid not in seen:
                    job["timestamp"] = datetime.now(timezone.utc).isoformat()
                    seen.add(jid)
                    new_jobs.append(job)
            time.sleep(random.uniform(2.5, 4.0))

        if new_jobs:
            all_jobs = json.load(open(JOBS_FILE))
            all_jobs.extend(new_jobs)
            write_json(JOBS_FILE, all_jobs)

            log = json.load(open(NEW_JOBS_FILE))
            log.append({"time": datetime.now(timezone.utc).isoformat(), "new": new_jobs})
            write_json(NEW_JOBS_FILE, log)

        time.sleep(INTERVAL_SECONDS)


# ======================
# START
# ======================
Thread(
    target=dashboard.app.run,
    kwargs={"host": "0.0.0.0", "port": 8080},
    daemon=True,
).start()

crawler()
