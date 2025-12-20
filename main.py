import requests
import json
import time
import os
import random
from datetime import datetime
from threading import Thread

import dashboard

API_URL = "https://e5mquma77feepi2bdn4d6h3mpu.appsync-api.us-east-1.amazonaws.com/graphql"

# ---- REQUIRED ENV TOKEN ----
AUTH_TOKEN = os.environ.get("AMAZON_AUTH_TOKEN")

# ---- BASE HEADERS (browser-like) ----
BASE_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "*/*",
    "Origin": "https://hiring.amazon.ca",
    "Referer": "https://hiring.amazon.ca/",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
    "Country": "Canada",
    "iscanary": "false"
}

# ---- CANADA COORDINATES (ALL PROVINCES) ----
CANADA_COORDINATES = [
    (43.6532, -79.3832), (45.4215, -75.6972),
    (45.5017, -73.5673), (46.8139, -71.2080),
    (49.2827, -123.1207), (48.4284, -123.3656),
    (51.0447, -114.0719), (53.5461, -113.4938),
    (49.8951, -97.1384), (52.1332, -106.6700),
    (44.6488, -63.5752), (45.9636, -66.6431),
    (47.5615, -52.7126), (46.2382, -63.1311),
    (62.4540, -114.3718), (60.7212, -135.0568),
    (63.7467, -68.5167)
]

# ---- GRAPHQL PAYLOAD ----
PAYLOAD_TEMPLATE = {
    "operationName": "searchJobCardsByLocation",
    "variables": {
        "searchJobRequest": {
            "locale": "en-CA",
            "country": "Canada",
            "pageSize": 100,
            "geoQueryClause": None,
            "dateFilters": [
                {
                    "key": "firstDayOnSite",
                    "range": {"startDate": "2025-12-18"}
                }
            ]
        }
    },
    "query": """query searchJobCardsByLocation($searchJobRequest: SearchJobRequest!) {
        searchJobCardsByLocation(searchJobRequest: $searchJobRequest) {
            jobCards {
                jobId
                jobTitle
                city
                state
            }
        }
    }"""
}

# ---- STORAGE FILES ----
JOBS_FILE = "jobs_store.json"
NEW_JOBS_FILE = "new_jobs_log.json"

if not os.path.exists(JOBS_FILE):
    open(JOBS_FILE, "w").write("[]")

if not os.path.exists(NEW_JOBS_FILE):
    open(NEW_JOBS_FILE, "w").write("[]")

seen = {j["jobId"] for j in json.load(open(JOBS_FILE))}


def fetch_jobs(lat, lng):
    if not AUTH_TOKEN:
        print("❌ AMAZON_AUTH_TOKEN is missing")
        return []

    payload = json.loads(json.dumps(PAYLOAD_TEMPLATE))
    payload["variables"]["searchJobRequest"]["geoQueryClause"] = {
        "lat": lat,
        "lng": lng,
        "unit": "km",
        "distance": 100
    }

    headers = BASE_HEADERS.copy()
    headers["Authorization"] = AUTH_TOKEN

    r = requests.post(API_URL, headers=headers, json=payload, timeout=30)

    try:
        data = r.json()
    except Exception:
        print("❌ Non-JSON response")
        return []

    if "errors" in data:
        print("⚠️ GraphQL error:", data["errors"])
        return []

    return data["data"]["searchJobCardsByLocation"]["jobCards"]


def save_jobs(new_jobs):
    all_jobs = json.load(open(JOBS_FILE))
    all_jobs.extend(new_jobs)
    json.dump(all_jobs, open(JOBS_FILE, "w"), indent=2)


def log_new(new_jobs):
    log = json.load(open(NEW_JOBS_FILE))
    log.append({"time": datetime.utcnow().isoformat(), "new": new_jobs})
    json.dump(log, open(NEW_JOBS_FILE, "w"), indent=2)


def crawler():
    while True:
        batch = []

        for lat, lng in CANADA_COORDINATES:
            jobs = fetch_jobs(lat, lng)

            for job in jobs:
                if job["jobId"] not in seen:
                    job["timestamp"] = datetime.utcnow().isoformat()
                    seen.add(job["jobId"])
                    batch.append(job)

            # small delay to avoid rate limits
            time.sleep(random.uniform(1.2, 2.5))

        if batch:
            save_jobs(batch)
            log_new(batch)
            print(f"🆕 {len(batch)} new jobs found")
        else:
            print("No new jobs")

        # wait 30 minutes before next scan
        time.sleep(1800)


# ---- START DASHBOARD SERVER ----
Thread(
    target=dashboard.app.run,
    kwargs={"host": "0.0.0.0", "port": 8080}
).start()

# ---- START CRAWLER ----
crawler()
