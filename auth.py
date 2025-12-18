import requests
import time

SESSION_URL = "https://hiring.amazon.ca/api/session"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
    "Accept": "application/json",
    "Referer": "https://hiring.amazon.ca/",
    "Origin": "https://hiring.amazon.ca",
}

_token = None
_expiry = 0


def get_auth_token():
    global _token, _expiry

    # reuse token if valid (5 min buffer)
    if _token and time.time() < (_expiry - 300):
        return _token

    print("🔄 Refreshing Amazon session token")

    r = requests.get(SESSION_URL, headers=HEADERS, timeout=20)
    r.raise_for_status()

    data = r.json()

    # expected response shape
    # { "token": "Status|unauthenticated|Session|...", "expiresIn": 3600 }

    _token = f"Bearer {data['token']}"
    _expiry = time.time() + data.get("expiresIn", 3600)

    return _token
