import requests
import json
import time
import os
import random
import hashlib
import smtplib
from email.message import EmailMessage
from datetime import datetime, timedelta, timezone
from threading import Thread

import dashboard

# ======================
# CANADIAN CITIES
# ======================
CANADA_CITIES = [
    ("Toronto", 43.6532, -79.3832),
    ("Ottawa", 45.4215, -75.6972),
    ("Mississauga", 43.5890, -79.6441),
    ("Brampton", 43.7315, -79.7624),
    ("Hamilton", 43.2557, -79.8711),
    ("Kitchener", 43.4516, -80.4925),
    ("Waterloo", 43.4643, -80.5204),
    ("London", 42.9849, -81.2453),
    ("Windsor", 42.3149, -83.0364),
    ("Barrie", 44.3894, -79.6903),
    ("Kingston", 44.2312, -76.4860),
    ("Oshawa", 43.8971, -78.8658),
    ("Thunder Bay", 48.3809, -89.2477),

    ("Montreal", 45.5017, -73.5673),
    ("Laval", 45.5369, -73.5107),
    ("Longueuil", 45.5312, -73.5181),
    ("Quebec City", 46.8139, -71.2080),
    ("Gatineau", 45.4765, -75.7013),
    ("Sherbrooke", 45.4042, -71.8929),
    ("Trois-Rivières", 46.3430, -72.5479),
    ("Saguenay", 48.4284, -71.0685),

    ("Vancouver", 49.2827, -123.1207),
    ("Surrey", 49.1913, -122.8490),
    ("Burnaby", 49.2488, -122.9805),
    ("Richmond", 49.1666, -123.1336),
    ("Coquitlam", 49.2838, -122.7932),
    ("Victoria", 48.4284, -123.3656),
    ("Kelowna", 49.8880, -119.4960),
    ("Prince George", 53.9171, -122.7497),

    ("Calgary", 51.0447, -114.0719),
    ("Edmonton", 53.5461, -113.4938),
    ("Red Deer", 52.2681, -113.8112),
    ("Lethbridge", 49.6956, -112.8451),
    ("Medicine Hat", 50.0405, -110.6766),
    ("Fort McMurray", 56.7267, -111.3810),
    ("Grande Prairie", 55.1707, -118.7947),

    ("Winnipeg", 49.8951, -97.1384),
    ("Brandon", 50.4452, -99.9501),
    ("Saskatoon", 52.1332, -106.6700),
    ("Regina", 50.4452, -104.6189),
    ("Halifax", 44.6488, -63.5752),
    ("Moncton", 46.0878, -64.7782),
    ("St. John's", 47.5615, -52.7126),
    ("Whitehorse", 60.7212, -135.0568),
    ("Yellowknife", 62.4540, -114.3718),
]


API_URL = "https://e5mquma77feepi2bdn4d6h3mpu.appsync-api.us-east-1.amazonaws.com/graphql"

INTERVAL_SECONDS = 210  # 3.5 minutes

# ======================
# EMAIL CONFIG
# ======================
SMTP_CONFIG = {
    "host": "smtp.office365.com",   # Outlook SMTP
    "port": 587,
    "user": os.getenv("ALERT_EMAIL_USER"),
    "password": os.getenv("ALERT_EMAIL_PASS"),
    "to": os.getenv("ALERT_EMAIL_TO"),
}

EMAIL_ENABLED = all(SMTP_CONFIG.values())

# ======================
# FILES
# ======================
JOBS_FILE = "jobs_store.json"
NEW_JOBS_FILE = "new_jobs_log.json"
REQUEST_LOG_FILE = "request_log.json"
LAST_RUN_FILE = "last_run.json"
NEXT_RUN_FILE = "next_run.json"
AUTH_STATE_FILE = "auth_state.json"

for f, default in [
    (JOBS_FILE, []),
    (NEW_JOBS_FILE, []),
    (REQUEST_LOG_FILE, []),
]:
    if not os.path.exists(f):
        json.dump(default, open(f, "w"))

if not os.path.exists(AUTH_STATE_FILE):
    json.dump({"state": "running", "token_hash": ""}, open(AUTH_STATE_FILE, "w"))

# ======================
# HELPERS
# ======================
def write_json(path, data):
    json.dump(data, open(path, "w"), indent=2)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def get_auth_state():
    return json.load(open(AUTH_STATE_FILE))


def set_auth_state(state, token=None, status=None):
    data = get_auth_state()
    data["state"] = state
    if token:
        data["token_hash"] = token_hash(token)
    if status:
        data["status"] = status
        data["time"] = datetime.now(timezone.utc).isoformat()
    write_json(AUTH_STATE_FILE, data)


def send_auth_alert(status):
    if not EMAIL_ENABLED:
        return

    msg = EmailMessage()
    msg["Subject"] = "🚨 Amazon Jobs Monitor – AUTH TOKEN FAILED"
    msg["From"] = SMTP_CONFIG["user"]
    msg["To"] = SMTP_CONFIG["to"]

    msg.set_content(
        f"""
Amazon Jobs Monitor has been PAUSED.

Reason: Auth failure ({status})
Time: {datetime.now(timezone.utc).isoformat()}

Update AMAZON_AUTH_TOKEN to auto-resume.
"""
    )

    try:
        with smtplib.SMTP(SMTP_CONFIG["host"], SMTP_CONFIG["port"]) as s:
            s.starttls()
            s.login(SMTP_CONFIG["user"], SMTP_CONFIG["password"])
            s.send_message(msg)
    except Exception as e:
        print("Email alert failed:", e)


def log_request(city, status):
    logs = json.load(open(REQUEST_LOG_FILE))
    logs.append({
        "time": datetime.now(timezone.utc).isoformat(),
        "city": city,
        "status": status,
    })
    write_json(REQUEST_LOG_FILE, logs[-300:])


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
# FETCH
# ======================
def fetch_jobs(city, lat, lng):
    if get_auth_state()["state"] == "paused":
        return []

    token = get_auth_token()

    headers = {
        "accept": "*/*",
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

    if r.status_code in (401, 403, 404):
        set_auth_state("paused", token=token, status=r.status_code)
        send_auth_alert(r.status_code)
        log_request(city, f"AUTH_{r.status_code}")
        return []

    if r.status_code != 200:
        log_request(city, f"HTTP_{r.status_code}")
        return []

    data = r.json()
    if "errors" in data:
        set_auth_state("paused", token=token, status="GRAPHQL_AUTH")
        send_auth_alert("GRAPHQL_AUTH")
        return []

    log_request(city, "OK")
    return data["data"]["searchJobCardsByLocation"]["jobCards"]


# ======================
# CRAWLER
# ======================
def crawler():
    seen = set(j.get("jobId") for j in json.load(open(JOBS_FILE)) if j.get("jobId"))

    while True:
        state = get_auth_state()

        # 🔁 AUTO-RESUME
        if state["state"] == "paused":
            try:
                new_token = get_auth_token()
                if token_hash(new_token) != state.get("token_hash"):
                    print("✅ Token updated – resuming")
                    set_auth_state("running", token=new_token)
                else:
                    time.sleep(30)
                    continue
            except Exception:
                time.sleep(30)
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
