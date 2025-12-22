from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
from webdriver_manager.chrome import ChromeDriverManager
import time
import json

APPSYNC_HOST = "appsync-api.us-east-1.amazonaws.com"


def fetch_amazon_token(timeout=30):
    caps = DesiredCapabilities.CHROME
    caps["goog:loggingPrefs"] = {"performance": "ALL"}

    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")

    driver = webdriver.Chrome(
        ChromeDriverManager().install(),
        options=chrome_options,
        desired_capabilities=caps
    )

    driver.get("https://hiring.amazon.ca")

    start = time.time()
    token = None

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
                        token = auth
                        break
            except Exception:
                pass

        if token:
            break

        time.sleep(1)

    driver.quit()

    if not token:
        raise RuntimeError("Failed to capture Amazon auth token")

    return token
