import time
import json
import os
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service


def find_chromedriver():
    candidates = [
        "/usr/bin/chromedriver",
        "/usr/lib/chromium/chromedriver",
        "/usr/lib/chromium-browser/chromedriver",
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    raise RuntimeError("Chromedriver not found")


def fetch_amazon_token(timeout=60):
    print("Chromium exists:", os.path.exists("/usr/bin/chromium"))

    chromedriver_path = find_chromedriver()
    print("Using chromedriver:", chromedriver_path)

    chrome_options = Options()
    chrome_options.binary_location = "/usr/bin/chromium"

    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")

    chrome_options.set_capability(
        "goog:loggingPrefs", {"performance": "ALL"}
    )

    service = Service(chromedriver_path)

    driver = webdriver.Chrome(
        service=service,
        options=chrome_options
    )

    # 1️⃣ Open page
    driver.get("https://hiring.amazon.ca")

    # 2️⃣ Give JS time to bootstrap
    time.sleep(5)

    # 3️⃣ Force scroll to trigger job search
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    time.sleep(2)
    driver.execute_script("window.scrollTo(0, 0);")

    start = time.time()
    token = None

    # 4️⃣ Capture AppSync auth header
    while time.time() - start < timeout:
        logs = driver.get_log("performance")

        for entry in logs:
            try:
                msg = json.loads(entry["message"])["message"]

                if msg.get("method") == "Network.requestWillBeSent":
                    req = msg["params"]["request"]
                    headers = req.get("headers", {})
                    auth = headers.get("authorization") or headers.get("Authorization")

                    if auth and "Status|unauthenticated|Session" in auth:
                        token = auth.strip()
                        break
            except Exception:
                pass

        if token:
            break

        time.sleep(1)

    driver.quit()

    if not token:
        raise RuntimeError("❌ Failed to capture Amazon auth token")

    print("✅ Amazon auth token captured")
    return token
