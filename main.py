import requests
import json
import time
import os
import random
from datetime import datetime
from threading import Thread

import dashboard

API_URL = "https://e5mquma77feepi2bdn4d6h3mpu.appsync-api.us-east-1.amazonaws.com/graphql"

# ===============================
# ENV TOKEN (SET IN RAILWAY)
# ===============================
AUTH_TOKEN = os.environ.get("AMAZON_AUTH_TOKEN")

# ===============================
# HEADERS (browser-like)
# ===============================
BASE_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "*/*",
    "Origin": "https://hiring.amazon.ca",
    "Referer": "https://hiring.amazon.ca/",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
    "Country": "Canada",
    "iscanary": "false",
}

# ===============================
# ~40 CANADIAN CITIES (lat, lng)
# ===============================
CANADA_COORDINATES = [
    # Ontario
    (43.6532, -79.3832), (45.4215, -75.6972), (43.5890, -79.6441),
    (43.7315, -79.7624), (43.2557, -79.8711), (43.4516, -80.4925),
    (43.4643, -80.5204), (42.9849, -81.2453), (42.3149, -83.0364),
    (48.3809, -89.2477),

    # Quebec
    (45.5017, -73.5673), (45.5369, -73.5107), (45.5312, -73.5181),
    (46.8139, -71.2080), (45.4042, -71.8929), (46.3430, -72.5479),
    (48.4284, -71.0685), (45.4765, -75.7013),

    # British Columbia
    (49.2827, -123.1207), (49.1913, -122.8490), (49.2488, -122.9805),
    (49.1666, -123.1336), (48.4284, -123.3656), (49.8880, -119.4960),
    (53.9171, -122.7497),

    # Alberta
    (51.0447, -114.0719), (53.5461, -113.4938), (52.2681, -113.8112),
    (49.6956, -112.8451), (56.7267, -111.3810), (50.0405, -110.6766),

    # Manitoba
    (49.8951, -97.1384), (50.4452, -99.9501),

    # Saskatchewan
    (52.1332, -106.6700), (50.4452, -104.6189),

    # Atlantic
    (44.6488, -63.5752), (46.2382, -63.1311), (47.5615, -52.7126),

    # Territories
    (60.7212, -135.0568), (62.4540, -114.3718),
]

# ===============================
# GRAPHQL PAYLOAD
# ===============================
PAYLOAD_TEMPLATE = {
    "operationName": "searchJobCardsByLocation",
    "variables": {
        "searchJobRequest": {
            "locale": "en-CA",
            "country": "Canada",
            "pageSize": 100,
            "geoQueryClause": None,
            "dateFilters": [
                {"key": "firstDayOnSite", "range": {"startDate": "2025-12-18"}}
            ],
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
    }""",
}

# ===============================
# FILES
# ===============================
JOBS_FILE = "jobs_store.json"
NEW_JOBS_FILE = "new_jobs_log.json"
LAST_RUN_FILE = "last_run.json"

for f in [JOBS_FILE, NEW_JOBS_FILE]:
    if not os.path.exists(f):
        open(f, "w").write("[]")

# load seen jobIds (safe if file empty)
seen = set()
try:
    seen = {j.get("jobId") for j in json.load(open(JOBS_FILE)) if j.get("jobId")}
except Exception:
    seen = set()


def update_last_run():
    """Heartbeat: ALWAYS write last run time."""
    with open(LAST_RUN_FILE, "w") as f:
        json.dump({"last_run": datetime.utcnow().isoformat()}, f)


def fetch_jobs(lat, lng):
    if not AUTH_TOKEN:
        print("❌ AMAZON_AUTH_TOKEN missing")
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
        data = r.json()
    except Exception as e:
        print("❌ Request/JSON error:", e)
        return []

    if "errors" in data:
        print("⚠️ GraphQL error:", data["errors"])
        return []

    return data.get("data", {}).get("searchJobCardsByLocation", {}).get("jobCards", [])


def crawler():
    while True:
        # 🔹 HEARTBEAT FIRST — ALWAYS UPDATES TIME
        update_last_run()

        batch = []

        for lat, lng in CANADA_COORDINATES:
            jobs = fetch_jobs(lat, lng)
            for job in jobs:
                jid = job.get("jobId")
                if jid and jid not in seen:
                    job["timestamp"] = datetime.utcnow().isoformat()
                    seen.add(jid)
                    batch.append(job)

            # gentle delay to reduce rate limits
            time.sleep(random.uniform(1.2, 2.5))

        if batch:
            all_jobs = json.load(open(JOBS_FILE))
            all_jobs.extend(batch)
            json.dump(all_jobs, open(JOBS_FILE, "w"), indent=2)

            log = json.load(open(NEW_JOBS_FILE))
            log.append({"time": datetime.utcnow().isoformat(), "new": batch})
            json.dump(log, open(NEW_JOBS_FILE, "w"), indent=2)

            print(f"🆕 {len(batch)} new jobs found")
        else:
            print("No new jobs")

        # 🔁 RUN EVERY 5 MINUTES
        time.sleep(300)


# ===============================
# START DASHBOARD + CRAWLER
# ===============================
Thread(
    target=dashboard.app.run,
    kwargs={"host": "0.0.0.0", "port": 8080},
    daemon=True,
).start()

crawler()
