import requests
import json
import time
import os
import random
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
# INIT FILES
# ======================
for f, default in [
    (JOBS_FILE, []),
    (NEW_JOBS_FILE, []),
    (REQUEST_LOG_FILE, []),
]:
    if not os.path.exists(f):
        json.dump(default, open(f, "w"))

# ⚠️ IMPORTANT: Railway redeploy = resume
# Always clear sleep state on startup
json.dump({}, open(SLEEP_STATE_FILE, "w"))

# ======================
# CITIES
# ======================
CANADA_CITIES = [ ("Toronto", 43.6532, -79.3832), ("Ottawa", 45.4215, -75.6972), ("Mississauga", 43.5890, -79.6441), ("Brampton", 43.7315, -79.7624), ("Hamilton", 43.2557, -79.8711), ("Kitchener", 43.4516, -80.4925), ("Waterloo", 43.4643, -80.5204), ("London", 42.9849, -81.2453), ("Windsor", 42.3149, -83.0364), ("Barrie", 44.3894, -79.6903), ("Kingston", 44.2312, -76.4860), ("Oshawa", 43.8971, -78.8658), ("Thunder Bay", 48.3809, -89.2477), ("Montreal", 45.5017, -73.5673), ("Laval", 45.5369, -73.5107), ("Longueuil", 45.5312, -73.5181), ("Quebec City", 46.8139, -71.2080), ("Gatineau", 45.4765, -75.7013), ("Sherbrooke", 45.4042, -71.8929), ("Trois-Rivières", 46.3430, -72.5479), ("Saguenay", 48.4284, -71.0685), ("Vancouver", 49.2827, -123.1207), ("Surrey", 49.1913, -122.8490), ("Burnaby", 49.2488, -122.9805), ("Richmond", 49.1666, -123.1336), ("Coquitlam", 49.2838, -122.7932), ("Victoria", 48.4284, -123.3656), ("Kelowna", 49.8880, -119.4960), ("Prince George", 53.9171, -122.7497), ("Calgary", 51.0447, -114.0719), ("Edmonton", 53.5461, -113.4938), ("Red Deer", 52.2681, -113.8112), ("Lethbridge", 49.6956, -112.8451), ("Medicine Hat", 50.0405, -110.6766), ("Fort McMurray", 56.7267, -111.3810), ("Grande Prairie", 55.1707, -118.7947), ("Winnipeg", 49.8951, -97.1384), ("Brandon", 50.4452, -99.9501), ("Saskatoon", 52.1332, -106.6700), ("Regina", 50.4452, -104.6189), ("Halifax", 44.6488, -63.5752), ("Moncton", 46.0878, -64.7782), ("St. John's", 47.5615, -52.7126), ("Whitehorse", 60.7212, -135.0568), ("Yellowknife", 62.4540, -114.3718), ]

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
    write_json(
        NEXT_RUN_FILE,
        {"next_run": (now + timedelta(seconds=INTERVAL_SECONDS)).isoformat()},
    )


def get_auth_token():
    token = os.getenv("AMAZON_AUTH_TOKEN")
    if not token:
        raise RuntimeError("AMAZON_AUTH_TOKEN missing")
    return token.strip()


# ======================
# EMAIL (SENDGRID – HTTPS SAFE)
# ======================
def send_email(subject, body):
    try:
        api_key = os.getenv("SENDGRID_API_KEY")
        to_email = os.getenv("ALERT_EMAIL_TO")

        if not api_key or not to_email:
            raise RuntimeError("SendGrid env vars missing")

        payload = {
            "personalizations": [{"to": [{"email": to_email}]}],
            "from": {"email": "alerts@monitor.local"},
            "subject": subject,
            "content": [{"type": "text/plain", "value": body}],
        }

        r = requests.post(
            "https://api.sendgrid.com/v3/mail/send",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=15,
        )

        if r.status_code not in (200, 202):
            raise RuntimeError(f"SendGrid HTTP {r.status_code}")

    except Exception as e:
        print("❌ EMAIL FAILED:", repr(e))
        log_request("SYSTEM", f"EMAIL_FAILED:{type(e).__name__}")


# ======================
# SLEEP STATE (403)
# ======================
def get_sleep_state():
    return json.load(open(SLEEP_STATE_FILE))


def set_sleep_state():
    hours = random.randint(1, 2)
    now = datetime.now(timezone.utc)

    state = {
        "sleeping": True,
        "reason": "403",
        "since": now.isoformat(),
        "wake_at": (now + timedelta(hours=hours)).isoformat(),
        "note": "Update token and redeploy Railway to resume",
    }
    write_json(SLEEP_STATE_FILE, state)

    send_email(
        "⚠️ Amazon Jobs Monitor – Sleeping (403)",
        f"""
403 detected.

System sleeping for {hours} hours.
Update AMAZON_AUTH_TOKEN in Railway and redeploy to resume.

Time: {now.isoformat()}
""",
    )


def sleep_if_needed():
    state = get_sleep_state()
    if not state.get("sleeping"):
        return False

    if datetime.now(timezone.utc) >= datetime.fromisoformat(state["wake_at"]):
        write_json(SLEEP_STATE_FILE, {})
        return False

    time.sleep(300)  # wait 5 minutes
    return True


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
        set_sleep_state()
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
        if sleep_if_needed():
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
