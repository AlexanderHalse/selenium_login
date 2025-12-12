import time
from typing import Any, Dict, List, Optional

from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support.ui import WebDriverWait

from .base import BaseLoginProvider


class SmergersLogin(BaseLoginProvider):
    site_key = "smergers"
    LOGIN_URL = "https://www.smergers.com/login/"

    # We anchor the "login box" via the tab labels rendered together.
    # This avoids picking up header search inputs etc.
    TAB_LABELS = ("SOCIAL", "REGISTER", "LOGIN")

    def login(self, driver: WebDriver, username: str, password: str, **kwargs: Any) -> List[Dict[str, Any]]:
        debug = bool(kwargs.get("debug", False))

        driver.get(self.LOGIN_URL)

        # Wait for page to have the tab bar somewhere
        WebDriverWait(driver, 25).until(lambda d: self._find_login_box(d) is not None)

        self._fail_if_google(driver)

        box = self._find_login_box(driver)
        if box is None:
            raise RuntimeError(self._dbg("SMERGERS: could not locate login box", driver, debug))

        # Click LOGIN tab INSIDE the box
        if not self._click_login_tab_in_box(driver, box):
            raise RuntimeError(self._dbg("SMERGERS: could not click LOGIN tab", driver, debug))

        # Wait until password is visible inside the box
        email_el = self._wait_visible_in(box, [
            "input[type='email']",
            "input[name='email']",
            "input[id*='email' i]",
            "input[placeholder*='email' i]",
        ], timeout=20)

        pass_el = self._wait_visible_in(box, [
            "input[type='password']",
            "input[name='password']",
            "input[id*='password' i]",
        ], timeout=20)

        if email_el is None or pass_el is None:
            raise RuntimeError(self._dbg("SMERGERS: login inputs not found inside login box", driver, debug))

        # Fill fields
        self._clear_and_type(email_el, username)
        self._clear_and_type(pass_el, password)

        # Submit (prefer Enter on password)
        try:
            pass_el.send_keys(Keys.ENTER)
        except Exception:
            # fallback: find a submit button inside box
            btn = self._first_visible_in(box, [
                "button[type='submit']",
                "input[type='submit']",
                "button",
            ])
            if btn:
                btn.click()

        # Wait a bit for cookies/session to set; also detect OAuth bounce
        def done(d: WebDriver) -> bool:
            self._fail_if_google(d)
            url = (d.current_url or "").lower()
            return ("/login" not in url) and ("smergers.com" in url)

        try:
            WebDriverWait(driver, 30).until(done)
        except Exception:
            # Not fatal; sometimes it stays on /login but still sets cookies
            pass

        self._fail_if_google(driver)
        return driver.get_cookies()

    # -------- helpers --------

    def _find_login_box(self, driver: WebDriver) -> Optional[WebElement]:
        # Strategy: find elements containing the 3 tab labels and pick the smallest common container.
        # We do this by locating the "SOCIAL" text near "REGISTER" and "LOGIN".
        # On current page, these are in the right-side card.
        try:
            candidates = driver.find_elements(By.XPATH, "//*[normalize-space()='SOCIAL']")
        except Exception:
            return None

        for el in candidates:
            try:
                # Climb a few levels up and check if that container contains REGISTER and LOGIN too
                container = el
                for _ in range(6):
                    parent = container.find_element(By.XPATH, "..")
                    text = (parent.text or "")
                    if all(lbl in text for lbl in self.TAB_LABELS):
                        return parent
                    container = parent
            except Exception:
                continue
        return None

    def _click_login_tab_in_box(self, driver: WebDriver, box: WebElement) -> bool:
        # Click element whose visible text is exactly LOGIN (avoid "Login with Google")
        try:
            els = box.find_elements(By.XPATH, ".//*[self::a or self::button or self::div or self::li]")
        except Exception:
            return False

        for el in els:
            try:
                txt = (el.text or "").strip()
                if txt == "LOGIN" and el.is_displayed() and el.is_enabled():
                    el.click()
                    time.sleep(0.3)
                    return True
            except Exception:
                continue

        # Fallback: click by XPath exact match within box
        try:
            el = box.find_element(By.XPATH, ".//*[normalize-space()='LOGIN']")
            if el.is_displayed() and el.is_enabled():
                el.click()
                time.sleep(0.3)
                return True
        except Exception:
            pass

        return False

    def _wait_visible_in(self, root: WebElement, selectors: List[str], timeout: int = 15) -> Optional[WebElement]:
        end = time.time() + timeout
        while time.time() < end:
            el = self._first_visible_in(root, selectors)
            if el is not None:
                return el
            time.sleep(0.2)
        return None

    def _first_visible_in(self, root: WebElement, selectors: List[str]) -> Optional[WebElement]:
        for sel in selectors:
            try:
                els = root.find_elements(By.CSS_SELECTOR, sel)
            except Exception:
                continue
            for el in els:
                try:
                    if el.is_displayed() and el.is_enabled():
                        return el
                except Exception:
                    continue
        return None

    def _clear_and_type(self, el: WebElement, text: str) -> None:
        try:
            el.clear()
        except Exception:
            pass
        try:
            el.send_keys(Keys.CONTROL, "a")
            el.send_keys(Keys.BACKSPACE)
        except Exception:
            pass
        el.send_keys(text)

    def _fail_if_google(self, driver: WebDriver) -> None:
        url = (driver.current_url or "").lower()
        title = (driver.title or "").lower()
        if "accounts.google.com" in url or "google accounts" in title:
            raise RuntimeError(
                f"SMERGERS: redirected to Google OAuth unexpectedly. url={driver.current_url!r} title={driver.title!r}"
            )

    def _dbg(self, msg: str, driver: WebDriver, debug: bool) -> str:
        if not debug:
            return msg
        try:
            return f"{msg}. url={driver.current_url!r} title={driver.title!r}"
        except Exception:
            return msg
