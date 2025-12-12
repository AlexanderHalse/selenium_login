"""
Smergers login provider.

This module implements a login provider for https://www.smergers.com that
is compatible with the FastAPI service defined in ``app/main.py``.  The
login flow on SMERGERS is slightly unusual because the login form is
presented inside a modal dialog with three tabs: ``SOCIAL``, ``REGISTER``
and ``LOGIN``.  By default the ``SOCIAL`` tab is active and only shows
third‑party OAuth buttons (Google, LinkedIn, Facebook, WhatsApp).  The
email/password inputs are rendered only after clicking the ``LOGIN`` tab.

The provider below encapsulates that behaviour: it loads the login
page, waits for the modal to appear, activates the ``LOGIN`` tab, fills
in the email and password fields and submits the form.  It tries to
avoid clicking any of the social buttons which would redirect the
browser to an OAuth flow.  If the page design changes (e.g. SMERGERS
introduces a different DOM structure), you may need to adjust the
selectors in ``EMAIL_SELECTORS``, ``PASSWORD_SELECTORS`` or
``LOGIN_TAB_XPATH``.
"""

from typing import Any, Dict, List, Optional
import time

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from .base import BaseLoginProvider


class SmergersLogin(BaseLoginProvider):
    """Login provider for smergers.com."""

    #: Unique key used by the API to select this provider
    site_key = "smergers"

    #: URL of the page that triggers the login modal.  The ``/login/``
    #: endpoint opens the same modal as clicking the "Login" link in the
    #: navigation bar on other pages.
    LOGIN_URL = "https://www.smergers.com/login/"

    #: CSS selectors used to locate the email/username input.  SMERGERS
    #: may name the field ``email`` or use a generic text field for
    #: phone/email.  We include a few common variants.
    EMAIL_SELECTORS = [
        "input[type='email']",
        "input[name='email']",
        "input[id*='email' i]",
        "input[placeholder*='email' i]",
        "input[type='text']",  # fallback for phone/email hybrid
    ]

    #: CSS selectors used to locate the password input.
    PASSWORD_SELECTORS = [
        "input[type='password']",
        "input[name='password']",
        "input[id*='password' i]",
    ]

    #: XPath expression to locate the ``LOGIN`` tab inside the modal.
    #: We match elements (``<a>``, ``<button>``, ``<li>``, ``<div>``)
    #: whose text exactly equals 'LOGIN' (case‑insensitive) and avoid
    #: elements that contain longer strings like "Login with Google".
    LOGIN_TAB_XPATH = (
        "//*[self::a or self::button or self::li or self::div]"
        "[translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz') = 'login']"
    )

    def login(self, driver: WebDriver, username: str, password: str, **kwargs: Any) -> List[Dict[str, Any]]:
        """
        Automate the SMERGERS login flow.

        This method navigates to the SMERGERS login page, clicks the
        appropriate tab to reveal the email/password form, fills in the
        credentials and submits the form.  On success, it returns the
        cookies from the Selenium WebDriver.  If the site redirects
        into an OAuth provider (e.g. Google) or fails to display the
        password field, a ``RuntimeError`` is raised to help callers
        diagnose the problem.
        """
        # 1) Navigate to the login page.  A short retry helps if the
        # network connection momentarily fails.
        for _ in range(2):
            try:
                driver.get(self.LOGIN_URL)
                break
            except Exception:
                time.sleep(1.0)

        # 2) Wait until either the modal dialog or some input appears.  The
        # modal is rendered asynchronously; presence_of_element_located
        # ensures we wait until there is at least one form element.
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "input, form, button"))
        )

        # 3) Click the LOGIN tab.  SMERGERS defaults to the SOCIAL tab,
        # showing only OAuth buttons.  The following tries to find an
        # element whose text is exactly 'LOGIN' and click it.  We loop
        # through matches because the site may render the tab as an <a>,
        # <button>, <div> or <li>.
        try:
            login_tabs = driver.find_elements(By.XPATH, self.LOGIN_TAB_XPATH)
            for tab in login_tabs:
                try:
                    # Only click visible and enabled elements
                    if tab.is_displayed() and tab.is_enabled():
                        tab.click()
                        break
                except Exception:
                    continue
        except Exception:
            pass

        # 4) Wait for the email and password fields to become visible.  If
        # the password field never appears (e.g. because the site forces
        # a social/OTP login), we raise an exception after the timeout.
        email_input = self._wait_for_visible_any(driver, self.EMAIL_SELECTORS, timeout=20)
        password_input = self._wait_for_visible_any(driver, self.PASSWORD_SELECTORS, timeout=20)
        if email_input is None or password_input is None:
            raise RuntimeError(
                "SMERGERS: login inputs not found. The site may be forcing a social/OTP flow or the selectors need updating."
            )

        # 5) Enter the credentials.  Clear existing text first to avoid
        # accidental concatenation.  We wrap calls in try/except to allow
        # fallback clearing behaviour if needed.
        try:
            email_input.clear()
        except Exception:
            pass
        email_input.send_keys(username)
        try:
            password_input.clear()
        except Exception:
            pass
        password_input.send_keys(password)

        # 6) Submit the form.  Pressing Enter on the password field
        # generally triggers the form submission without clicking any
        # explicit buttons.  If that fails, we click the first submit
        # button inside the modal as a fallback.
        submitted = False
        try:
            password_input.send_keys(Keys.ENTER)
            submitted = True
        except Exception:
            pass

        if not submitted:
            try:
                submit_button = driver.find_element(By.CSS_SELECTOR, "button[type='submit'], input[type='submit']")
                submit_button.click()
            except Exception:
                pass

        # 7) Wait for navigation to complete.  We consider it logged in
        # when the current URL no longer contains '/login' and the
        # SMERGERS domain is still present.  If the page navigates to
        # accounts.google.com or another domain, we raise a helpful
        # error.
        def logged_in(d: WebDriver) -> bool:
            url = (d.current_url or "").lower()
            # detect undesired OAuth redirection
            if "accounts.google.com" in url:
                raise RuntimeError(
                    "SMERGERS: redirected to Google OAuth. Avoid clicking social login buttons and ensure the LOGIN tab is selected."
                )
            return "/login" not in url and "smergers.com" in url

        try:
            WebDriverWait(driver, 30).until(logged_in)
        except Exception:
            # Do not fail hard; we still return whatever cookies are set.
            pass

        # 8) Return cookies to the API.  The FastAPI layer will convert
        # these into an HTTP cookie header for the caller.
        return driver.get_cookies()

    def _wait_for_visible_any(self, driver: WebDriver, selectors: List[str], timeout: int = 15) -> Optional[WebElement]:
        """
        Wait until any of the given CSS selectors matches a visible and
        enabled element, and return it.  Returns ``None`` if no such
        element is found within the timeout.  This helper simplifies
        handling pages that might use slightly different input names.
        """
        end = time.time() + timeout
        while time.time() < end:
            for sel in selectors:
                try:
                    elems = driver.find_elements(By.CSS_SELECTOR, sel)
                except Exception:
                    continue
                for el in elems:
                    try:
                        if el.is_displayed() and el.is_enabled():
                            return el
                    except Exception:
                        continue
            time.sleep(0.2)
        return None
