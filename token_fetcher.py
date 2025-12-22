import time
import json
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager


def fetch_amazon_token(timeout=40):
    """
    Launches a real headless Chrome browser,
    opens hiring.amazon.ca,
    captures the AppSync Authorization header,
    returns the FULL Bearer token.
    """

    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")

    # ✅ Selenium 4 way of enabling performance logs
    chrome_options.set_capability("goog:loggingPrefs", {"performance": "ALL"})

    driver = webdriver.Chrome(
        ChromeDriverManager().install(),
        options=chrome_options,
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
