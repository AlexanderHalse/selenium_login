# app/logins/smergers.py
#
# SMERGERS login is often a multi-step flow:
# 1) enter email/phone
# 2) click Continue/Next/Login
# 3) password input appears
#
# Your TimeoutException ("no visible password") is consistent with step (2)
# never being completed, or the password field being rendered only after
# selecting a "Password" login option (vs OTP), or an overlay blocking the UI.

import time
from typing import Any, Dict, List, Optional

from selenium.common.exceptions import (
    ElementClickInterceptedException,
    ElementNotInteractableException,
    StaleElementReferenceException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from .base import BaseLoginProvider


class SmergersLogin(BaseLoginProvider):
    site_key = "smergers"
    LOGIN_URL = "https://www.smergers.com/login/"

    # Overlays / consent close buttons (best effort)
    OVERLAY_CLOSE_SELECTORS = [
        "#onetrust-accept-btn-handler",
        "button[id*='accept' i]",
        "button[aria-label*='accept' i]",
        "button[aria-label*='close' i]",
        "button[title*='close' i]",
        ".modal-close, .dialog-close, .popup-close, .close",
        "[role='dialog'] button[aria-label*='close' i]",
    ]

    # Step-1 identity field can be email OR phone OR generic text
    IDENTITY_SELECTORS = [
        "form input[type='email']",
        "input[type='email']",
        "form input[type='tel']",
        "input[type='tel']",
        "form input[name='email']",
        "input[name='email']",
        "input[id*='email' i]",
        "input[placeholder*='email' i]",
        "input[placeholder*='phone' i]",
        "input[autocomplete='username']",
        # fallback: some sites use text for email/phone
        "form input[type='text']",
    ]

    PASSWORD_SELECTORS = [
        "form input[type='password']",
        "input[type='password']",
        "input[name='password']",
        "input[id*='password' i]",
        "input[autocomplete='current-password']",
    ]

    # Buttons that commonly advance step 1 → step 2 or submit final login
    # Use XPath with case-insensitive text match via translate().
    BUTTON_XPATH_CANDIDATES = [
        # Continue / Next / Login / Sign in
        "//button[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'continue')]",
        "//button[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'next')]",
        "//button[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'login')]",
        "//button[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'sign in')]",
        "//button[@type='submit']",
        "//input[@type='submit']",
    ]

    # Tabs/links that may be needed to select "Login" (vs Register) or "Password" (vs OTP)
    TAB_XPATH_CANDIDATES = [
        "//a[contains(@href, '/login')]",
        "//button[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'login')]",
        "//button[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'password')]",
        "//a[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'password')]",
        "//button[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'sign in')]",
    ]

    def login(self, driver: WebDriver, username: str, password: str, **kwargs: Any) -> List[Dict[str, Any]]:
        self._safe_get(driver, self.LOGIN_URL)
        self._wait_present(driver, "input, form, button", timeout=25)
        self._dismiss_overlays(driver)

        # Try to ensure we're on the Login tab, and also try selecting "Password" mode if present
        self._try_click_any_xpath(driver, self.TAB_XPATH_CANDIDATES, timeout=3)
        self._dismiss_overlays(driver)

        # STEP 1: find identity input (email/phone/text)
        ident = self._find_visible_css(driver, self.IDENTITY_SELECTORS, timeout=25)
        self._focus_and_type(driver, ident, username, clear=True)

        self._dismiss_overlays(driver)

        # STEP 2: if password is not visible yet, click a "Continue/Next/Login" style button
        pass_el = self._try_find_visible_css(driver, self.PASSWORD_SELECTORS, timeout=2)
        if pass_el is None:
            clicked = self._try_click_any_xpath(driver, self.BUTTON_XPATH_CANDIDATES, timeout=6)
            self._dismiss_overlays(driver)

            # Wait again for password field after advancing
            pass_el = self._try_find_visible_css(driver, self.PASSWORD_SELECTORS, timeout=12)

            # If still no password, try again selecting "Password" mode and re-check
            if pass_el is None:
                self._try_click_any_xpath(driver, self.TAB_XPATH_CANDIDATES, timeout=3)
                self._dismiss_overlays(driver)
                pass_el = self._try_find_visible_css(driver, self.PASSWORD_SELECTORS, timeout=8)

            if pass_el is None:
                # At this point, the page likely expects OTP flow, has bot protection,
                # or uses non-standard fields. Raise a useful error instead of a vague timeout.
                raise RuntimeError(
                    "SMERGERS: Could not find a visible password input. "
                    "This usually means the site is using an OTP-only flow for this session, "
                    "the password field appears only after a different UI choice, "
                    "or an overlay/bot-check is blocking inputs. "
                    f"url={driver.current_url!r} title={driver.title!r}"
                )

        # STEP 3: enter password
        self._focus_and_type(driver, pass_el, password, clear=True)
        self._dismiss_overlays(driver)

        # STEP 4: submit (Enter first, then click submit buttons)
        submitted = self._send_enter(pass_el)
        if not submitted:
            self._try_click_any_xpath(driver, self.BUTTON_XPATH_CANDIDATES, timeout=6)

        # STEP 5: wait for "logged in"
        self._wait_logged_in(driver, timeout=35)

        return driver.get_cookies()

    # ---------------- helpers ----------------

    def _safe_get(self, driver: WebDriver, url: str) -> None:
        try:
            driver.get(url)
        except WebDriverException:
            time.sleep(1.0)
            driver.get(url)

    def _wait_present(self, driver: WebDriver, css: str, timeout: int = 15) -> None:
        WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, css))
        )

    def _dismiss_overlays(self, driver: WebDriver) -> None:
        for _ in range(2):
            for sel in self.OVERLAY_CLOSE_SELECTORS:
                try:
                    els = driver.find_elements(By.CSS_SELECTOR, sel)
                except Exception:
                    continue
                for el in els:
                    try:
                        if el.is_displayed() and el.is_enabled():
                            self._safe_click(driver, el)
                            time.sleep(0.25)
                    except Exception:
                        continue

    def _scroll_into_view(self, driver: WebDriver, el: WebElement) -> None:
        try:
            driver.execute_script(
                "arguments[0].scrollIntoView({block:'center', inline:'center'});", el
            )
        except Exception:
            pass

    def _safe_click(self, driver: WebDriver, el: WebElement) -> bool:
        try:
            self._scroll_into_view(driver, el)
            WebDriverWait(driver, 6).until(lambda d: el.is_displayed() and el.is_enabled())
            el.click()
            return True
        except (ElementClickInterceptedException, ElementNotInteractableException, TimeoutException, StaleElementReferenceException):
            try:
                self._scroll_into_view(driver, el)
                driver.execute_script("arguments[0].click();", el)
                return True
            except Exception:
                return False

    def _find_visible_css(self, driver: WebDriver, selectors: List[str], timeout: int = 20) -> WebElement:
        end = time.time() + timeout
        while time.time() < end:
            for sel in selectors:
                try:
                    els = driver.find_elements(By.CSS_SELECTOR, sel)
                except Exception:
                    continue
                for el in els:
                    try:
                        if el.is_displayed() and el.is_enabled():
                            return el
                    except StaleElementReferenceException:
                        continue
            time.sleep(0.2)
        raise TimeoutException("No visible/enabled element found for CSS selectors")

    def _try_find_visible_css(self, driver: WebDriver, selectors: List[str], timeout: int = 4) -> Optional[WebElement]:
        end = time.time() + timeout
        while time.time() < end:
            for sel in selectors:
                try:
                    els = driver.find_elements(By.CSS_SELECTOR, sel)
                except Exception:
                    continue
                for el in els:
                    try:
                        if el.is_displayed() and el.is_enabled():
                            return el
                    except StaleElementReferenceException:
                        continue
            time.sleep(0.2)
        return None

    def _clear_input(self, el: WebElement) -> None:
        # Some sites block clear(); use robust clear
        try:
            el.clear()
            return
        except Exception:
            pass
        try:
            el.send_keys(Keys.CONTROL, "a")
            el.send_keys(Keys.BACKSPACE)
        except Exception:
            try:
                el.send_keys("\b" * 40)
            except Exception:
                pass

    def _focus_and_type(self, driver: WebDriver, el: WebElement, text: str, clear: bool = True) -> None:
        self._dismiss_overlays(driver)
        self._scroll_into_view(driver, el)

        if not self._safe_click(driver, el):
            try:
                driver.execute_script("arguments[0].focus();", el)
            except Exception:
                pass

        # Wait until interactable
        try:
            WebDriverWait(driver, 8).until(lambda d: el.is_displayed() and el.is_enabled())
        except Exception:
            pass

        if clear:
            self._clear_input(el)

        try:
            el.send_keys(text)
        except ElementNotInteractableException:
            try:
                driver.execute_script("arguments[0].focus();", el)
            except Exception:
                pass
            el.send_keys(text)

    def _send_enter(self, el: WebElement) -> bool:
        try:
            el.send_keys(Keys.ENTER)
            return True
        except Exception:
            return False

    def _try_click_any_xpath(self, driver: WebDriver, xpaths: List[str], timeout: int = 5) -> bool:
        end = time.time() + timeout
        while time.time() < end:
            for xp in xpaths:
                try:
                    els = driver.find_elements(By.XPATH, xp)
                except Exception:
                    continue
                for el in els:
                    try:
                        if el.is_displayed() and el.is_enabled():
                            if self._safe_click(driver, el):
                                return True
                    except StaleElementReferenceException:
                        continue
            time.sleep(0.2)
        return False

    def _wait_logged_in(self, driver: WebDriver, timeout: int = 30) -> None:
        def ok(d: WebDriver) -> bool:
            url = (d.current_url or "").lower()
            if "/login" not in url:
                return True
            for sel in [
                "a[href*='logout']",
                "a[href*='dashboard']",
                "a[href*='account']",
                "button[aria-label*='account' i]",
            ]:
                try:
                    el = d.find_element(By.CSS_SELECTOR, sel)
                    if el and el.is_displayed():
                        return True
                except Exception:
                    pass
            return False

        try:
            WebDriverWait(driver, timeout).until(ok)
        except TimeoutException:
            # Still return cookies; detection may be too strict
            pass
