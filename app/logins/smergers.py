# app/logins/smergers.py

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
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from .base import BaseLoginProvider


class SmergersLogin(BaseLoginProvider):
    site_key = "smergers"

    LOGIN_URL = "https://www.smergers.com/login/"

    # Best-effort cookie/consent/modal close selectors (site may change)
    OVERLAY_CLOSE_SELECTORS = [
        # common consent frameworks
        "#onetrust-accept-btn-handler",
        "button[id*='accept' i]",
        "button[aria-label*='accept' i]",
        "button[aria-label*='close' i]",
        "button[title*='close' i]",
        # generic modal close patterns
        ".modal .close, .modal-close, .dialog-close, .popup-close",
        "[role='dialog'] button[aria-label*='close' i]",
        "[role='dialog'] .close",
    ]

    # Candidate selectors for fields/buttons
    EMAIL_SELECTORS = [
        "form input[type='email']",
        "input[type='email']",
        "form input[name='email']",
        "input[name='email']",
        "input[id*='email' i]",
        "input[placeholder*='email' i]",
        "input[autocomplete='username']",
    ]
    PASSWORD_SELECTORS = [
        "form input[type='password']",
        "input[type='password']",
        "form input[name='password']",
        "input[name='password']",
        "input[id*='password' i]",
        "input[autocomplete='current-password']",
    ]
    SUBMIT_SELECTORS = [
        "form button[type='submit']",
        "button[type='submit']",
        "form input[type='submit']",
        "input[type='submit']",
        "button[name='login']",
        "button[id*='login' i]",
    ]
    LOGIN_TAB_SELECTORS = [
        "a[href*='/login']",
        "button[aria-controls*='login' i]",
        "[role='tab'][aria-controls*='login' i]",
        "[role='tab'][id*='login' i]",
        "#login-tab",
    ]

    # ---------- public ----------
    def login(
        self,
        driver: WebDriver,
        username: str,
        password: str,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        self._safe_get(driver, self.LOGIN_URL)

        # Wait for something interactive to exist
        self._wait_present(driver, "input, form, button", timeout=25)

        # Try to close cookie banners / overlays that commonly block inputs
        self._dismiss_overlays(driver)

        # Ensure we are on Login (not Register) if there are tabs
        self._try_click_any(driver, self.LOGIN_TAB_SELECTORS, timeout=3)
        self._dismiss_overlays(driver)

        # Some sites render login inside iframes; try main doc first, then iframes
        ctx = self._find_login_context(driver)
        if ctx is not None:
            ctx_type, frame_el = ctx
            if ctx_type == "iframe" and frame_el is not None:
                driver.switch_to.frame(frame_el)

        try:
            email_el = self._find_visible(driver, self.EMAIL_SELECTORS, timeout=25)
            pass_el = self._find_visible(driver, self.PASSWORD_SELECTORS, timeout=25)

            self._focus_and_type(driver, email_el, username, clear=True)
            self._focus_and_type(driver, pass_el, password, clear=True)

            self._dismiss_overlays(driver)

            # Submit
            submitted = self._try_submit(driver, pass_el)
            if not submitted:
                submitted = self._try_click_any(driver, self.SUBMIT_SELECTORS, timeout=6)

            # Wait for URL change away from /login OR presence of a likely logged-in element
            self._wait_logged_in(driver, timeout=35)

        finally:
            # Always return to default context
            try:
                driver.switch_to.default_content()
            except Exception:
                pass

        return driver.get_cookies()

    # ---------- helpers ----------
    def _safe_get(self, driver: WebDriver, url: str) -> None:
        try:
            driver.get(url)
        except WebDriverException:
            # occasional navigation flake; retry once
            time.sleep(1.0)
            driver.get(url)

    def _wait_present(self, driver: WebDriver, css: str, timeout: int = 15) -> None:
        WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, css))
        )

    def _find_visible(
        self,
        driver: WebDriver,
        selectors: List[str],
        timeout: int = 20,
    ) -> WebElement:
        end = time.time() + timeout
        last_err: Optional[Exception] = None

        while time.time() < end:
            for sel in selectors:
                try:
                    els = driver.find_elements(By.CSS_SELECTOR, sel)
                    for el in els:
                        try:
                            if el.is_displayed() and el.is_enabled():
                                return el
                        except StaleElementReferenceException:
                            continue
                except Exception as e:
                    last_err = e
            time.sleep(0.2)

        if last_err:
            raise last_err
        raise TimeoutException("No visible/enabled element found for selectors")

    def _scroll_into_view(self, driver: WebDriver, el: WebElement) -> None:
        try:
            driver.execute_script(
                "arguments[0].scrollIntoView({block:'center', inline:'center'});",
                el,
            )
        except Exception:
            pass

    def _safe_click(self, driver: WebDriver, el: WebElement) -> bool:
        try:
            self._scroll_into_view(driver, el)
            WebDriverWait(driver, 8).until(lambda d: el.is_displayed() and el.is_enabled())
            el.click()
            return True
        except (ElementClickInterceptedException, ElementNotInteractableException, TimeoutException, StaleElementReferenceException):
            # JS click fallback
            try:
                self._scroll_into_view(driver, el)
                driver.execute_script("arguments[0].click();", el)
                return True
            except Exception:
                return False

    def _clear_input(self, el: WebElement) -> None:
        # Some sites block clear(); use robust clear sequence
        try:
            el.clear()
            return
        except Exception:
            pass
        try:
            el.send_keys(Keys.CONTROL, "a")
            el.send_keys(Keys.BACKSPACE)
        except Exception:
            # last resort: send a bunch of backspaces
            try:
                el.send_keys("\b" * 30)
            except Exception:
                pass

    def _focus_and_type(self, driver: WebDriver, el: WebElement, text: str, clear: bool = True) -> None:
        # Avoid "element not interactable" by ensuring visible + scrolled + clicked
        self._scroll_into_view(driver, el)
        self._dismiss_overlays(driver)

        if not self._safe_click(driver, el):
            # last resort focus
            try:
                driver.execute_script("arguments[0].focus();", el)
            except Exception:
                pass

        # Wait until interactable
        try:
            WebDriverWait(driver, 10).until(lambda d: el.is_displayed() and el.is_enabled())
        except Exception:
            pass

        if clear:
            self._clear_input(el)

        # Type (with fallback)
        try:
            el.send_keys(text)
        except ElementNotInteractableException:
            # try focus then send keys again
            try:
                driver.execute_script("arguments[0].focus();", el)
            except Exception:
                pass
            el.send_keys(text)

    def _try_click_any(self, driver: WebDriver, selectors: List[str], timeout: int = 5) -> bool:
        end = time.time() + timeout
        while time.time() < end:
            for sel in selectors:
                try:
                    els = driver.find_elements(By.CSS_SELECTOR, sel)
                    for el in els:
                        try:
                            if el.is_displayed() and el.is_enabled():
                                if self._safe_click(driver, el):
                                    return True
                        except StaleElementReferenceException:
                            continue
                except Exception:
                    continue
            time.sleep(0.2)
        return False

    def _dismiss_overlays(self, driver: WebDriver) -> None:
        # Best-effort: try a couple of passes
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
                            time.sleep(0.3)
                    except Exception:
                        continue

    def _try_submit(self, driver: WebDriver, password_el: WebElement) -> bool:
        # submit by Enter on password field
        try:
            password_el.send_keys(Keys.ENTER)
            return True
        except Exception:
            return False

    def _wait_logged_in(self, driver: WebDriver, timeout: int = 30) -> None:
        def ok(d: WebDriver) -> bool:
            url = (d.current_url or "").lower()
            if "/login" not in url:
                return True
            # heuristic: common logged-in UI anchors
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
            # allow cookies to still be returned (could still be logged-in but not detected)
            pass

    def _find_login_context(self, driver: WebDriver) -> Optional[Tuple[str, Optional[WebElement]]]:
        """
        Try main document first. If no visible email/password found, scan iframes.
        Returns:
            ("main", None) or ("iframe", iframe_element) or None
        """
        try:
            _ = self._find_visible(driver, self.EMAIL_SELECTORS, timeout=4)
            _ = self._find_visible(driver, self.PASSWORD_SELECTORS, timeout=4)
            return ("main", None)
        except Exception:
            pass

        # Scan iframes
        try:
            frames = driver.find_elements(By.CSS_SELECTOR, "iframe")
        except Exception:
            frames = []

        for fr in frames:
            try:
                if not fr.is_displayed():
                    continue
            except Exception:
                continue

            try:
                driver.switch_to.default_content()
                driver.switch_to.frame(fr)
                self._dismiss_overlays(driver)
                _ = self._find_visible(driver, self.EMAIL_SELECTORS, timeout=2)
                _ = self._find_visible(driver, self.PASSWORD_SELECTORS, timeout=2)
                driver.switch_to.default_content()
                return ("iframe", fr)
            except Exception:
                try:
                    driver.switch_to.default_content()
                except Exception:
                    pass
                continue

        return None
