import requests
import json
import time
import os
import random
from datetime import datetime, timedelta, timezone
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
# CITIES
# ======================
CANADA_CITIES = [
    # ===== Ontario (14) =====
    ("Toronto", 43.6532, -79.3832),
    ("Ottawa", 45.4215, -75.6972),
    ("Mississauga", 43.5890, -79.6441),
    ("Brampton", 43.7315, -79.7624),
    ("Hamilton", 43.2557, -79.8711),
    ("Kitchener", 43.4516, -80.4925),
    ("Waterloo", 43.4643, -80.5204),
    ("London", 42.9849, -81.2453),
    ("Windsor", 42.3149, -83.0364),
    ("Guelph", 43.5448, -80.2482),
    ("Barrie", 44.3894, -79.6903),
    ("Kingston", 44.2312, -76.4860),
    ("Oshawa", 43.8971, -78.8658),
    ("Thunder Bay", 48.3809, -89.2477),

    # ===== Quebec (10) =====
    ("Montreal", 45.5017, -73.5673),
    ("Laval", 45.5369, -73.5107),
    ("Longueuil", 45.5312, -73.5181),
    ("Quebec City", 46.8139, -71.2080),
    ("Gatineau", 45.4765, -75.7013),
    ("Sherbrooke", 45.4042, -71.8929),
    ("Trois-Rivières", 46.3430, -72.5479),
    ("Drummondville", 45.8833, -72.4834),
    ("Saguenay", 48.4284, -71.0685),
    ("Saint-Hyacinthe", 45.6300, -72.9560),

    # ===== British Columbia (8) =====
    ("Vancouver", 49.2827, -123.1207),
    ("Surrey", 49.1913, -122.8490),
    ("Burnaby", 49.2488, -122.9805),
    ("Richmond", 49.1666, -123.1336),
    ("Coquitlam", 49.2838, -122.7932),
    ("Victoria", 48.4284, -123.3656),
    ("Kelowna", 49.8880, -119.4960),
    ("Prince George", 53.9171, -122.7497),

    # ===== Alberta (7) =====
    ("Calgary", 51.0447, -114.0719),
    ("Edmonton", 53.5461, -113.4938),
    ("Red Deer", 52.2681, -113.8112),
    ("Lethbridge", 49.6956, -112.8451),
    ("Medicine Hat", 50.0405, -110.6766),
    ("Fort McMurray", 56.7267, -111.3810),
    ("Grande Prairie", 55.1707, -118.7947),

    # ===== Prairies & Atlantic (7) =====
    ("Winnipeg", 49.8951, -97.1384),
    ("Brandon", 50.4452, -99.9501),
    ("Saskatoon", 52.1332, -106.6700),
    ("Regina", 50.4452, -104.6189),
    ("Halifax", 44.6488, -63.5752),
    ("Moncton", 46.0878, -64.7782),
    ("St. John's", 47.5615, -52.7126),

    # ===== Territories (2) =====
    ("Whitehorse", 60.7212, -135.0568),
    ("Yellowknife", 62.4540, -114.3718),
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
# LOAD SEEN JOB IDS
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
    now = datetime.now(timezone.utc)
    write_json(LAST_RUN_FILE, {"last_run": now.isoformat()})
    write_json(
        NEXT_RUN_FILE,
        {"next_run": (now + timedelta(seconds=INTERVAL_SECONDS)).isoformat()},
    )


def log_request(city, status):
    logs = json.load(open(REQUEST_LOG_FILE))
    logs.append({
        "time": datetime.now(timezone.utc).isoformat(),
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
                    job["timestamp"] = datetime.now(timezone.utc).isoformat()
                    seen.add(jid)
                    new_jobs.append(job)

            time.sleep(random.uniform(1.0, 2.0))

        if new_jobs:
            all_jobs = json.load(open(JOBS_FILE))
            all_jobs.extend(new_jobs)
            write_json(JOBS_FILE, all_jobs)

            log = json.load(open(NEW_JOBS_FILE))
            log.append({
                "time": datetime.now(timezone.utc).isoformat(),
                "new": new_jobs
            })
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
