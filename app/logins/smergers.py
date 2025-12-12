import time
from typing import Any, Dict, List, Optional

from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from .base import BaseLoginProvider


class SmergersLogin(BaseLoginProvider):
    """Login provider for smergers.com.

    Notes:
    - SMERGERS uses a JS-heavy login page; selectors may change.
    - If your account is protected by CAPTCHA / OTP, a fully automated login
      may not be possible without manual steps.
    """

    site_key = "smergers"

    def _first_present(
        self,
        driver: WebDriver,
        selectors: List[str],
        by: By = By.CSS_SELECTOR,
        timeout: int = 25,
    ):
        last_err: Optional[Exception] = None
        for sel in selectors:
            try:
                return WebDriverWait(driver, timeout).until(
                    EC.presence_of_element_located((by, sel))
                )
            except Exception as e:
                last_err = e
        if last_err:
            raise last_err
        raise RuntimeError("No selectors provided")

    def login(
        self,
        driver: WebDriver,
        username: str,
        password: str,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        # 1) Go to login page
        driver.get("https://www.smergers.com/login/")

        # 2) Ensure we are on the Login tab (page also includes Register)
        try:
            login_tab = self._first_present(
                driver,
                selectors=[
                    "a[href*='/login']",
                    "button[aria-controls*='login']",
                    "#login-tab",
                ],
                timeout=10,
            )
            try:
                login_tab.click()
            except Exception:
                pass
        except Exception:
            pass

        # 3) Locate email + password inputs.
        email_input = self._first_present(
            driver,
            selectors=[
                "input[type='email']",
                "input[name='email']",
                "input[id*='email' i]",
            ],
        )
        password_input = self._first_present(
            driver,
            selectors=[
                "input[type='password']",
                "input[name='password']",
                "input[id*='password' i]",
            ],
        )

        try:
            WebDriverWait(driver, 10).until(EC.visibility_of(email_input))
            WebDriverWait(driver, 10).until(EC.visibility_of(password_input))
        except Exception:
            pass

        email_input.clear()
        email_input.send_keys(username)
        password_input.clear()
        password_input.send_keys(password)

        # 4) Submit
        try:
            submit_btn = self._first_present(
                driver,
                selectors=[
                    "button[type='submit']",
                    "input[type='submit']",
                    "button[name='login']",
                ],
                timeout=10,
            )
            try:
                WebDriverWait(driver, 10).until(EC.element_to_be_clickable(submit_btn))
            except Exception:
                pass
            submit_btn.click()
        except Exception:
            try:
                password_input.submit()
            except Exception:
                pass

        # 5) Wait until we're not on /login anymore or we see dashboard navigation
        def logged_in(d: WebDriver) -> bool:
            url = (d.current_url or "").lower()
            if "/login" not in url:
                return True
            try:
                d.find_element(By.CSS_SELECTOR, "a[href*='dashboard']")
                return True
            except Exception:
                return False

        try:
            WebDriverWait(driver, 35).until(logged_in)
        except Exception:
            time.sleep(6)

        return driver.get_cookies()
