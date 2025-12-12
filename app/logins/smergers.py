# app/logins/smergers.py
#
# SMERGERS shows a modal with tabs: SOCIAL / REGISTER / LOGIN.
# The default tab is SOCIAL (Google/LinkedIn/Facebook). You must click LOGIN
# before the email/password fields exist/are visible.
#
# This provider:
# - Opens a page that triggers the modal (login page)
# - Clicks the LOGIN tab in the modal (NOT the social buttons)
# - Fills email + password inside the modal
# - Submits and waits for the modal to close / URL to change

import time
from typing import Any, Dict, List, Optional, Tuple

from selenium.common.exceptions import (
    ElementClickInterceptedException,
    ElementNotInteractableException,
    NoSuchElementException,
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

    # Modal / overlay selectors (best-effort)
    MODAL_SELECTORS = [
        "div.modal",
        "div[role='dialog']",
        "div.modal-dialog",
    ]

    CLOSE_SELECTORS = [
        # your screenshot shows a red X button in the top-right of the modal
        "button.close",
        ".modal-header button.close",
        "button[aria-label='Close']",
        "button[title='Close']",
        "a.close",
    ]

    # Tab selectors (we will prefer clicking by text via XPath)
    LOGIN_TAB_XPATHS = [
        # “LOGIN” tab in the modal header
        "//*[self::a or self::button or self::li or self::div]"
        "[contains(translate(normalize-space(.),"
        " 'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'), 'login')]",
    ]

    # Inputs (scoped to form/modal later)
    EMAIL_SELECTORS = [
        "input[type='email']",
        "input[name='email']",
        "input[id*='email' i]",
        "input[placeholder*='email' i]",
        "input[autocomplete='username']",
        "input[type='text']",
    ]

    PASSWORD_SELECTORS = [
        "input[type='password']",
        "input[name='password']",
        "input[id*='password' i]",
        "input[autocomplete='current-password']",
    ]

    SUBMIT_SELECTORS = [
        "button[type='submit']",
        "input[type='submit']",
    ]

    def login(self, driver: WebDriver, username: str, password: str, **kwargs: Any) -> List[Dict[str, Any]]:
        self._safe_get(driver, self.LOGIN_URL)

        # Wait until either modal or some input appears
        self._wait_present(driver, "body", timeout=25)

        # Ensure we are not on Google OAuth (your previous error)
        self._fail_if_google(driver)

        # If modal exists, force switch to LOGIN tab
        self._ensure_login_tab(driver)

        # Find the "active" login container (modal/dialog) if present
        container = self._find_active_container(driver)

        email_el = self._find_visible_in(container, self.EMAIL_SELECTORS, timeout=25)
        pass_el = self._find_visible_in(container, self.PASSWORD_SELECTORS, timeout=25)

        self._focus_and_type(driver, email_el, username, clear=True)
        self._focus_and_type(driver, pass_el, password, clear=True)

        # Submit: prefer ENTER on password
        try:
            pass_el.send_keys(Keys.ENTER)
        except Exception:
            # fallback: click submit inside container
            self._click_first_visible_in(container, self.SUBMIT_SELECTORS, timeout=8)

        # Wait for login to complete: modal closes OR URL changes away from /login OR presence of account-ish link
        self._wait_logged_in(driver, timeout=35)

        self._fail_if_google(driver)
        return driver.get_cookies()

    # ---------------- core flow helpers ----------------

    def _ensure_login_tab(self, driver: WebDriver) -> None:
        # If login form is already visible, don't click anything
        if self._has_visible_password(driver):
            return

        # Wait for modal/dialog to show up (common) but do not hard-fail if site renders inline
        self._wait_any_present(driver, self.MODAL_SELECTORS + ["form", "input"], timeout=20)

        # Click the LOGIN tab by text, but avoid clicking "Login with Google"
        clicked = self._click_login_tab(driver)

        # Give the UI time to render login inputs
        time.sleep(0.4)

        # If still no password, try again after short wait
        if not self._has_visible_password(driver):
            if not clicked:
                # attempt again by scoping within modal only
                self._click_login_tab(driver, scope_modal_only=True)
                time.sleep(0.4)

        # If still no password, do not click random buttons (that leads to Google OAuth)
        if not self._has_visible_password(driver):
            raise RuntimeError(
                "SMERGERS: LOGIN tab did not reveal an email/password form. "
                "The site may be forcing social/OTP login for this session or the selectors changed. "
                f"url={driver.current_url!r} title={driver.title!r}"
            )

    def _click_login_tab(self, driver: WebDriver, scope_modal_only: bool = False) -> bool:
        # Build candidate elements
        candidates: List[WebElement] = []

        if scope_modal_only:
            modal = self._find_modal(driver)
            if modal is not None:
                # search inside modal for elements whose text is "LOGIN"
                candidates.extend(self._xpath_find_within(modal, ".//*[self::a or self::button or self::li or self::div]"))
        else:
            for xp in self.LOGIN_TAB_XPATHS:
                try:
                    candidates.extend(driver.find_elements(By.XPATH, xp))
                except Exception:
                    pass

        # Filter: must be displayed, and its text should be close to "LOGIN" (not "Login with Google")
        def is_login_tab(el: WebElement) -> bool:
            try:
                if not el.is_displayed() or not el.is_enabled():
                    return False
                txt = (el.text or "").strip().lower()
                if "login with" in txt:
                    return False
                # modal header tab is typically just "LOGIN"
                return txt == "login" or txt.endswith(" login") or txt.startswith("login ")
            except Exception:
                return False

        for el in candidates:
            if is_login_tab(el):
                if self._safe_click(driver, el):
                    return True

        # Fallback: specifically look for a tab list and click the item whose visible text == LOGIN
        modal = self._find_modal(driver)
        if modal is not None:
            try:
                tabs = modal.find_elements(By.CSS_SELECTOR, "a,button,li,div")
                for el in tabs:
                    try:
                        txt = (el.text or "").strip().lower()
                        if txt == "login" and el.is_displayed() and el.is_enabled():
                            if self._safe_click(driver, el):
                                return True
                    except Exception:
                        continue
            except Exception:
                pass

        return False

    # ---------------- element finding helpers ----------------

    def _find_active_container(self, driver: WebDriver):
        modal = self._find_modal(driver)
        return modal if modal is not None else driver

    def _find_modal(self, driver: WebDriver) -> Optional[WebElement]:
        for sel in self.MODAL_SELECTORS:
            try:
                els = driver.find_elements(By.CSS_SELECTOR, sel)
                for el in els:
                    try:
                        if el.is_displayed():
                            return el
                    except Exception:
                        continue
            except Exception:
                continue
        return None

    def _has_visible_password(self, driver: WebDriver) -> bool:
        try:
            for sel in self.PASSWORD_SELECTORS:
                els = driver.find_elements(By.CSS_SELECTOR, sel)
                for el in els:
                    if el.is_displayed() and el.is_enabled():
                        return True
        except Exception:
            return False
        return False

    def _find_visible_in(self, container, selectors: List[str], timeout: int = 20) -> WebElement:
        end = time.time() + timeout
        while time.time() < end:
            for sel in selectors:
                try:
                    els = container.find_elements(By.CSS_SELECTOR, sel)
                except Exception:
                    continue
                for el in els:
                    try:
                        if el.is_displayed() and el.is_enabled():
                            return el
                    except StaleElementReferenceException:
                        continue
            time.sleep(0.2)
        raise TimeoutException("No visible/enabled element found for selectors (container-scoped)")

    def _click_first_visible_in(self, container, selectors: List[str], timeout: int = 10) -> bool:
        end = time.time() + timeout
        while time.time() < end:
            for sel in selectors:
                try:
                    els = container.find_elements(By.CSS_SELECTOR, sel)
                except Exception:
                    continue
                for el in els:
                    try:
                        if el.is_displayed() and el.is_enabled():
                            # container-scoped click
                            return self._safe_click(container if hasattr(container, "execute_script") else container._parent, el)  # type: ignore[attr-defined]
                    except Exception:
                        continue
            time.sleep(0.2)
        return False

    def _xpath_find_within(self, root: WebElement, xpath: str) -> List[WebElement]:
        try:
            return root.find_elements(By.XPATH, xpath)
        except Exception:
            return []

    # ---------------- low-level utils ----------------

    def _fail_if_google(self, driver: WebDriver) -> None:
        url = (driver.current_url or "").lower()
        title = (driver.title or "").lower()
        if "accounts.google.com" in url or "google accounts" in title:
            raise RuntimeError(
                "SMERGERS: Redirected into Google OAuth. "
                "Do not click social login buttons; ensure the modal LOGIN tab is selected. "
                f"url={driver.current_url!r} title={driver.title!r}"
            )

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

    def _wait_any_present(self, driver: WebDriver, selectors: List[str], timeout: int = 15) -> None:
        end = time.time() + timeout
        while time.time() < end:
            for sel in selectors:
                try:
                    if driver.find_elements(By.CSS_SELECTOR, sel):
                        return
                except Exception:
                    pass
            time.sleep(0.2)

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

    def _clear_input(self, el: WebElement) -> None:
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
        self._scroll_into_view(driver, el)

        if not self._safe_click(driver, el):
            try:
                driver.execute_script("arguments[0].focus();", el)
            except Exception:
                pass

        try:
            WebDriverWait(driver, 8).until(lambda d: el.is_displayed() and el.is_enabled())
        except Exception:
            pass

        if clear:
            self._clear_input(el)

        el.send_keys(text)

    def _wait_logged_in(self, driver: WebDriver, timeout: int = 30) -> None:
        def ok(d: WebDriver) -> bool:
            url = (d.current_url or "").lower()

            # Modal closed = likely logged in (or user dismissed), but we accept it as progress
            modal = self._find_modal(d)
            if modal is None and "/login" not in url:
                return True

            # URL moved away from /login
            if "/login" not in url and "smergers.com" in url:
                return True

            # Heuristic logged-in UI anchors
            for sel in [
                "a[href*='logout']",
                "a[href*='dashboard']",
                "a[href*='account']",
                "a[href*='profile']",
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
            pass
