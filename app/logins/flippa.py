import time
from typing import Any, Dict, List

from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support.ui import WebDriverWait

from .base import BaseLoginProvider


class FlippaLogin(BaseLoginProvider):
    site_key = "flippa"

    def login(
        self,
        driver: WebDriver,
        username: str,
        password: str,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        """
        Perform login on flippa.com and return cookies.

        NOTE:
        - If Flippa changes their DOM, adjust the selectors below.
        """

        # 1) Go to Flippa login page
        driver.get("https://flippa.com/login")

        # 2) Find email and password fields.
        # Adjust selectors if needed:
        #   - input[name='email']
        #   - input[id='email']
        #   - input[type='email']
        #
        email_input = driver.find_element(By.CSS_SELECTOR, "input[type='email']")
        password_input = driver.find_element(By.CSS_SELECTOR, "input[type='password']")

        email_input.clear()
        email_input.send_keys(username)
        password_input.clear()
        password_input.send_keys(password)

        # 3) Find and click the submit button.
        # Adjust if Flippa uses a different structure.
        login_button = driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
        login_button.click()

        # 4) Wait for navigation away from /login, or timeout.
        # This is a simple heuristic that usually works.
        def logged_in(driver: WebDriver) -> bool:
            url = driver.current_url
            return "login" not in url

        try:
            WebDriverWait(driver, 30).until(logged_in)
        except Exception:
            # Fallback: small sleep; you might want to add extra checks here.
            time.sleep(5)

        # 5) Return cookies
        cookies = driver.get_cookies()
        return cookies
