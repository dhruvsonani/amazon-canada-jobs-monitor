import requests
import json
import time
import os
import random
from datetime import datetime, timedelta
from threading import Thread

import dashboard

API_URL = "https://e5mquma77feepi2bdn4d6h3mpu.appsync-api.us-east-1.amazonaws.com/graphql"

# ======================
# ENV TOKEN (REQUIRED)
# ======================
AUTH_TOKEN = os.environ.get("AMAZON_AUTH_TOKEN")

# ======================
# CONFIG
# ======================
INTERVAL_SECONDS = 120  # 2 minutes

BASE_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "*/*",
    "Origin": "https://hiring.amazon.ca",
    "Referer": "https://hiring.amazon.ca/",
    "User-Agent": "Mozilla/5.0",
    "Country": "Canada",
    "iscanary": "false",
}

# ======================
# FILES
# ======================
JOBS_FILE = "jobs_store.json"
NEW_JOBS_FILE = "new_jobs_log.json"
REQUEST_LOG_FILE = "request_log.json"
LAST_RUN_FILE = "last_run.json"
NEXT_RUN_FILE = "next_run.json"

for f, default in [
    (JOBS_FILE, []),
    (NEW_JOBS_FILE, []),
    (REQUEST_LOG_FILE, []),
]:
    if not os.path.exists(f):
        with open(f, "w") as fp:
            json.dump(default, fp)

# ======================
# CITIES (named)
# ======================
CANADA_CITIES = [
    ("Toronto", 43.6532, -79.3832),
    ("Ottawa", 45.4215, -75.6972),
    ("Montreal", 45.5017, -73.5673),
    ("Vancouver", 49.2827, -123.1207),
    ("Calgary", 51.0447, -114.0719),
    ("Edmonton", 53.5461, -113.4938),
    ("Winnipeg", 49.8951, -97.1384),
    ("Halifax", 44.6488, -63.5752),
]

# ======================
# GRAPHQL PAYLOAD
# ======================
PAYLOAD_TEMPLATE = {
    "operationName": "searchJobCardsByLocation",
    "variables": {
        "searchJobRequest": {
            "locale": "en-CA",
            "country": "Canada",
            "pageSize": 100,
            "geoQueryClause": None,
        }
    },
    "query": """query searchJobCardsByLocation($searchJobRequest: SearchJobRequest!) {
        searchJobCardsByLocation(searchJobRequest: $searchJobRequest) {
            jobCards { jobId jobTitle city state }
        }
    }""",
}

# ======================
# LOAD SEEN JOBS
# ======================
seen = set()
try:
    for j in json.load(open(JOBS_FILE)):
        if j.get("jobId"):
            seen.add(j["jobId"])
except Exception:
    pass


def write_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def update_run_times():
    now = datetime.utcnow()
    write_json(LAST_RUN_FILE, {"last_run": now.isoformat()})
    write_json(
        NEXT_RUN_FILE,
        {"next_run": (now + timedelta(seconds=INTERVAL_SECONDS)).isoformat()},
    )


def log_request(city, status):
    logs = json.load(open(REQUEST_LOG_FILE))
    logs.append({
        "time": datetime.utcnow().isoformat(),
        "city": city,
        "status": status
    })
    write_json(REQUEST_LOG_FILE, logs[-300:])


def fetch_jobs(city, lat, lng):
    if not AUTH_TOKEN:
        log_request(city, "NO_TOKEN")
        return []

    payload = json.loads(json.dumps(PAYLOAD_TEMPLATE))
    payload["variables"]["searchJobRequest"]["geoQueryClause"] = {
        "lat": lat,
        "lng": lng,
        "unit": "km",
        "distance": 100,
    }

    headers = BASE_HEADERS.copy()
    headers["Authorization"] = AUTH_TOKEN

    try:
        r = requests.post(API_URL, headers=headers, json=payload, timeout=30)

        if r.status_code != 200:
            log_request(city, f"HTTP_{r.status_code}")
            return []

        data = r.json()

        if "errors" in data:
            log_request(city, "GRAPHQL_ERROR")
            return []

        log_request(city, "OK")
        return data["data"]["searchJobCardsByLocation"]["jobCards"]

    except Exception:
        log_request(city, "REQUEST_FAILED")
        return []


def crawler():
    while True:
        update_run_times()
        new_jobs = []

        for city, lat, lng in CANADA_CITIES:
            jobs = fetch_jobs(city, lat, lng)
            for job in jobs:
                jid = job.get("jobId")
                if jid and jid not in seen:
                    job["timestamp"] = datetime.utcnow().isoformat()
                    seen.add(jid)
                    new_jobs.append(job)

            time.sleep(random.uniform(1.0, 2.0))

        if new_jobs:
            all_jobs = json.load(open(JOBS_FILE))
            all_jobs.extend(new_jobs)
            write_json(JOBS_FILE, all_jobs)

            log = json.load(open(NEW_JOBS_FILE))
            log.append({"time": datetime.utcnow().isoformat(), "new": new_jobs})
            write_json(NEW_JOBS_FILE, log)

        time.sleep(INTERVAL_SECONDS)


# ======================
# START DASHBOARD + CRAWLER
# ======================
Thread(
    target=dashboard.app.run,
    kwargs={"host": "0.0.0.0", "port": 8080},
    daemon=True
).start()

crawler()
