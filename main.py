import requests, json, time, os
from datetime import datetime
from threading import Thread
import dashboard

API_URL = "https://e5mquma77feepi2bdn4d6h3mpu.appsync-api.us-east-1.amazonaws.com/graphql"
HEADERS = {"Content-Type": "application/json"}

# ---- CANADA COORDINATES (ALL PROVINCES) ----
CANADA_COORDINATES = [
    (43.6532, -79.3832), (45.4215, -75.6972), (48.3809, -89.2477),
    (45.5017, -73.5673), (46.8139, -71.2080), (48.4284, -71.0685),
    (49.2827, -123.1207), (48.4284, -123.3656), (53.9171, -122.7497),
    (51.0447, -114.0719), (53.5461, -113.4938), (56.7267, -111.3810),
    (49.8951, -97.1384), (52.1332, -106.6700), (50.4452, -104.6189),
    (44.6488, -63.5752), (45.9636, -66.6431),
    (47.5615, -52.7126), (46.2382, -63.1311),
    (62.4540, -114.3718), (60.7212, -135.0568), (63.7467, -68.5167)
]

PAYLOAD_TEMPLATE = {
    "operationName": "searchJobCardsByLocation",
    "variables": {
        "searchJobRequest": {
            "locale": "en-CA",
            "country": "Canada",
            "pageSize": 100,
            "geoQueryClause": None
        }
    },
    "query": """query searchJobCardsByLocation($searchJobRequest: SearchJobRequest!) {
        searchJobCardsByLocation(searchJobRequest: $searchJobRequest) {
            jobCards {
                jobId jobTitle city state
            }
        }
    }"""
}

JOBS_FILE = "jobs_store.json"
NEW_JOBS_FILE = "new_jobs_log.json"

if not os.path.exists(JOBS_FILE): open(JOBS_FILE, "w").write("[]")
if not os.path.exists(NEW_JOBS_FILE): open(NEW_JOBS_FILE, "w").write("[]")

seen = set(j["jobId"] for j in json.load(open(JOBS_FILE)))

def fetch_jobs(lat, lng):
    payload = json.loads(json.dumps(PAYLOAD_TEMPLATE))
    payload["variables"]["searchJobRequest"]["geoQueryClause"] = {
        "lat": lat, "lng": lng, "unit": "km", "distance": 100
    }
    r = requests.post(API_URL, headers=HEADERS, json=payload, timeout=30)
    return r.json()["data"]["searchJobCardsByLocation"]["jobCards"]

def save(jobs):
    all_jobs = json.load(open(JOBS_FILE))
    all_jobs.extend(jobs)
    json.dump(all_jobs, open(JOBS_FILE, "w"), indent=2)

def log_new(jobs):
    log = json.load(open(NEW_JOBS_FILE))
    log.append({"time": datetime.utcnow().isoformat(), "new": jobs})
    json.dump(log, open(NEW_JOBS_FILE, "w"), indent=2)

def crawler():
    while True:
        new_jobs = []
        for lat, lng in CANADA_COORDINATES:
            for job in fetch_jobs(lat, lng):
                if job["jobId"] not in seen:
                    job["timestamp"] = datetime.utcnow().isoformat()
                    seen.add(job["jobId"])
                    new_jobs.append(job)
        if new_jobs:
            save(new_jobs)
            log_new(new_jobs)
            print(f"🆕 {len(new_jobs)} new jobs found")
        else:
            print("No new jobs")
        time.sleep(1800)  # 30 minutes

# Start dashboard
Thread(target=dashboard.app.run, kwargs={"host":"0.0.0.0","port":8080}).start()

# Start crawler
crawler()
