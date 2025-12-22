import time
import json
import os
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service


def fetch_amazon_token(timeout=40):
    # Sanity check (optional but helpful)
    print("Chromium exists:", os.path.exists("/usr/bin/chromium"))
    print("Chromedriver exists:", os.path.exists("/usr/bin/chromium-driver"))

    chrome_options = Options()

    # 🔴 CRITICAL: point Selenium to Chromium binary
    chrome_options.binary_location = "/usr/bin/chromium"

    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")

    # Enable network logging
    chrome_options.set_capability(
        "goog:loggingPrefs", {"performance": "ALL"}
    )

    # 🔴 CRITICAL: explicit chromedriver path
    service = Service("/usr/bin/chromium-driver")

    driver = webdriver.Chrome(
        service=service,
        options=chrome_options
    )

    driver.get("https://hiring.amazon.ca")

    start = time.time()
    token = None

    while time.time() - start < timeout:
        for entry in driver.get_log("performance"):
            try:
                msg = json.loads(entry["message"])["message"]
                if msg.get("method") == "Network.requestWillBeSent":
                    headers = msg["params"]["request"].get("headers", {})
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

    return token
