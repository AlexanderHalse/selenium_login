from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from typing import List, Dict, Any
import os


def create_driver() -> webdriver.Chrome:
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")

    service = Service(executable_path=os.environ.get("CHROMEDRIVER_PATH", "/usr/bin/chromedriver"))
    driver = webdriver.Chrome(service=service, options=chrome_options)
    driver.set_page_load_timeout(60)
    return driver


def cookies_to_header(cookies: List[Dict[str, Any]]) -> str:
    parts = []
    for c in cookies:
        name = c.get("name")
        value = c.get("value")
        if name is not None and value is not None:
            parts.append(f"{name}={value}")
    return "; ".join(parts)
