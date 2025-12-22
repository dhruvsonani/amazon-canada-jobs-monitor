import time
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


def fetch_amazon_token(timeout=30):
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

    service = Service(chromedriver_path)

    driver = webdriver.Chrome(
        service=service,
        options=chrome_options
    )

    # 1️⃣ Load Amazon hiring site
    driver.get("https://hiring.amazon.ca")

    # 2️⃣ Allow frontend JS + Cognito to initialize
    time.sleep(8)

    # 3️⃣ Read localStorage directly
    storage = driver.execute_script("return window.localStorage;")

    driver.quit()

    # 4️⃣ Find the AppSync unauth token
    token = None
    for key, value in storage.items():
        if "appsync" in key.lower() or "cognito" in key.lower():
            if isinstance(value, str) and "eyJ" in value:
                token = value
                break

    if not token:
        raise RuntimeError("❌ Failed to capture Amazon auth token from localStorage")

    # 5️⃣ Build Authorization header exactly like browser
    auth_header = f"Bearer Status|unauthenticated|Session|{token}"

    print("✅ Amazon auth token captured from localStorage")
    return auth_header
