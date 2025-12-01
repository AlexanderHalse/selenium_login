from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, List

from .selenium_client import create_driver, cookies_to_header
from .logins.flippa import FlippaLogin


app = FastAPI(title="Selenium Login Service")

# Register all login providers here
LOGIN_PROVIDERS = {
    FlippaLogin.site_key: FlippaLogin(),
}


class LoginRequest(BaseModel):
    site: str
    username: str
    password: str
    extra: Dict[str, Any] = {}


class LoginResponse(BaseModel):
    site: str
    cookie_header: str
    cookies: List[Dict[str, Any]]


@app.post("/login", response_model=LoginResponse)
def login(req: LoginRequest):
    if req.site not in LOGIN_PROVIDERS:
        raise HTTPException(status_code=400, detail=f"Unknown site '{req.site}'")

    provider = LOGIN_PROVIDERS[req.site]

    driver = create_driver()
    try:
        cookies = provider.login(driver, req.username, req.password, **req.extra)
        cookie_header = cookies_to_header(cookies)
    finally:
        driver.quit()

    return LoginResponse(
        site=req.site,
        cookie_header=cookie_header,
        cookies=cookies,
    )
