from __future__ import annotations

import os
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

# Seconds for all ``requests`` calls in this module (not a secret; keep in code).
HTTP_TIMEOUT_SECONDS = 30


def require_env(name: str) -> str:
    """Return the non-empty environment variable ``name`` or raise ``RuntimeError``."""
    if not isinstance(name, str) or not name.strip():
        raise ValueError("Environment variable name must be a non-empty string")

    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing or empty environment variable: {name}")
    return value


def get_client_credentials_access_token() -> str:
    """Authenticates and fetches the access token."""
    auth_token_url = require_env("TEST_PARAM_AUTH_TOKEN_URL")
    client_secret = require_env("TEST_PARAM_CLIENT_SECRET")

    auth_response = requests.post(
        auth_token_url,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "grant_type": "client_credentials",
            "client_secret": client_secret,
            "client_id": "e2e-test",
        },
        timeout=HTTP_TIMEOUT_SECONDS,
    )
    auth_response.raise_for_status()

    payload = auth_response.json()
    if not isinstance(payload, dict):
        raise RuntimeError("Auth token response must be a JSON object")
    token = payload.get("access_token")
    if not isinstance(token, str) or not token.strip():
        raise RuntimeError(
            "Auth token response did not contain a usable string 'access_token'"
        )
    return token.strip()


def get_otp_code(email_address: str) -> str:
    """Get OTP from email server with authentication."""
    if not isinstance(email_address, str):
        raise TypeError("email_address must be a string")
    email_address = email_address.strip().lower()
    if not email_address:
        raise ValueError("email_address must be a non-empty string")

    email_search_url = require_env("TEST_PARAM_EMAIL_SEARCH_URL")

    bearer_token = get_client_credentials_access_token()

    # Wait and get emails
    time.sleep(3)

    email_response = requests.post(
        email_search_url,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {bearer_token}",
        },
        json={"to": email_address},
        timeout=HTTP_TIMEOUT_SECONDS,
    )
    email_response.raise_for_status()

    email_payload = email_response.json()
    if not isinstance(email_payload, dict):
        raise RuntimeError("Email search response must be a JSON object")
    emails = email_payload.get("emails", [])
    if not isinstance(emails, list):
        raise RuntimeError("Email search response 'emails' must be a JSON array")
    if not emails:
        raise ValueError("No emails found")

    first = emails[0]
    if not isinstance(first, dict):
        raise RuntimeError("Email search response item must be a JSON object")
    dtd = first.get("dynamic_template_data", {})
    if not isinstance(dtd, dict):
        raise RuntimeError("dynamic_template_data must be a JSON object")
    otp = dtd.get("otp_code")
    if not otp:
        raise ValueError("OTP not found")
    return str(otp)


def get_otp_with_retries(
    email_address: str,
    retries: int = 10,
    delay_seconds: int = 1,
) -> str:
    if isinstance(retries, bool) or isinstance(delay_seconds, bool):
        raise TypeError("retries and delay_seconds must be integers, not bool")
    if not isinstance(retries, int) or not isinstance(delay_seconds, int):
        raise TypeError("retries and delay_seconds must be integers")
    if retries < 1:
        raise ValueError("retries must be at least 1")
    if delay_seconds < 0:
        raise ValueError("delay_seconds must be >= 0")

    last_exception: BaseException | None = None

    for attempt in range(1, retries + 1):
        try:
            return get_otp_code(email_address)
        except (
            KeyError,
            OSError,
            RuntimeError,
            TypeError,
            ValueError,
            requests.RequestException,
        ) as exc:
            last_exception = exc
            if attempt < retries:
                time.sleep(delay_seconds)

    if last_exception is not None:
        raise last_exception

    raise RuntimeError("Failed to retrieve OTP")
