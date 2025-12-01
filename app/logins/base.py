from abc import ABC, abstractmethod
from typing import Any, Dict, List
from selenium.webdriver.remote.webdriver import WebDriver


class BaseLoginProvider(ABC):
    site_key: str  # e.g. "flippa"

    @abstractmethod
    def login(
        self,
        driver: WebDriver,
        username: str,
        password: str,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        """
        Perform login on the target site and return driver.get_cookies().
        """
        raise NotImplementedError
