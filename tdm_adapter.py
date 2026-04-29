from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import TypedDict

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

# TDM (Test Data Management): standalone functions for test data setup.

# Seconds for all ``requests`` calls in this module.
HTTP_TIMEOUT_SECONDS = 30

MAX_STATION_ID = 9_999_999
MIN_RESERVATION_NUMBER = 1_000_000_000
MAX_RESERVATION_NUMBER = 9_999_999_999


class ProfileInfo(TypedDict):
    profile_id: str
    corporate_customer_id: str


class ProfilesByEmailResult(TypedDict):
    profiles: list[ProfileInfo]
    person_id: str
    member_id: str


# --- private helpers ---


def _get_first(d: dict[str, object], *keys: str) -> object | None:
    for k in keys:
        if k in d:
            return d[k]
    return None


def _scalar_to_str(value: object, field: str) -> str:
    if isinstance(value, bool):
        raise TypeError(f"Unexpected boolean for {field}")
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, int):
        return str(value)
    raise TypeError(f"{field} must be a string, int, or null")


def _validate_station_id(field: str, value: int) -> None:
    if isinstance(value, bool):
        raise TypeError(f"{field} must be an int, not bool")
    if value < 0 or value > MAX_STATION_ID:
        raise ValueError(
            f"{field} must be between 0 and {MAX_STATION_ID} (at most 7 decimal digits)"
        )


def _id_argument_as_str(field: str, value: object) -> str:
    """Coerce person/profile id to ``str`` for validation.

    ``int`` is allowed; ``bool`` is rejected (``bool`` is a subclass of ``int``).
    """
    if isinstance(value, bool):
        raise TypeError(f"{field} must be str or int, not bool")
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        return value
    raise TypeError(f"{field} must be str or int, not {type(value).__name__}")


def _require_nonblank_numeric_id(field: str, value: str) -> str:
    """Return stripped ``value`` or raise if it is blank or not all decimal digits."""
    text = value.strip()
    if not text:
        raise ValueError(f"{field} must be a non-empty string of decimal digits")
    if not text.isdigit():
        raise ValueError(f"{field} must contain only decimal digits (got {value!r})")
    return text


def _require_ten_digit_reservation_number(value: int) -> int:
    if value < MIN_RESERVATION_NUMBER or value > MAX_RESERVATION_NUMBER:
        raise ValueError(
            "Reservation number must be a 10-digit integer "
            f"({MIN_RESERVATION_NUMBER} … {MAX_RESERVATION_NUMBER})"
        )
    return value


def _address_from_share_car_name_field(payload: object) -> str:
    """Return the address string from the response ``name`` field (JSON string)."""
    if not isinstance(payload, dict):
        raise ValueError("ShareCarUser response must be a JSON object")

    raw = payload.get("name")
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError(
            "ShareCarUser response must contain a non-empty string field 'name' "
            f"(top-level keys: {list(payload.keys())})"
        )

    text = raw.strip()
    try:
        decoded = json.loads(text)
    except json.JSONDecodeError:
        return text

    if isinstance(decoded, str) and decoded.strip():
        return decoded.strip()

    raise ValueError(
        "'name' must be a JSON string (or JSON text that decodes to a string)"
    )


def _rental_reservation_v2_payload(
    pickup_station: int,
    return_station: int,
    pickup_date: str,
    return_date: str,
    prepaid: bool,
    profile_id: str = "",
    person_id: str = "",
) -> dict:
    """JSON body for ``RentalReservationV2`` (Lynx / TDM template placeholders)."""
    return {
        "pickup_station": str(pickup_station),
        "return_station": str(return_station),
        "pickup_date": pickup_date,
        "return_date": return_date,
        "pickup_time": "0900",
        "return_time": "1700",
        "prepaid": prepaid,
        "young_driver": False,
        "carGroup": "",
        "customer": {
            "corporate_customer_id": "",
            "profile_id": profile_id,
            "person_id": person_id,
            "contact": {
                "salutation": "@@person.salutation",
                "first_name": "@@person.firstname",
                "last_name": "@@person.lastname",
                "email": "@@person.email",
                "phone_number": "@@person.phone",
            },
            "birth_date": "@@person.birthdate",
        },
        "maestro": False,
        "wholesaler_reservation": False,
    }


def _rental_reservation_number_from_response(data: object) -> int:
    """Parse ``rental_reservation_number`` (plain or JSON-encoded string) to a 10-digit
    ``int``."""
    if not isinstance(data, dict):
        raise ValueError("Reservation response must be a JSON object")

    raw = data.get("rental_reservation_number")
    if raw is None:
        raise ValueError(
            "Reservation response missing rental_reservation_number "
            f"(top-level keys: {list(data.keys())})"
        )
    if isinstance(raw, bool):
        raise TypeError("Unexpected boolean for rental_reservation_number")

    if isinstance(raw, int):
        digits = str(raw)
    elif isinstance(raw, str):
        text = raw.strip()
        try:
            decoded = json.loads(text)
        except json.JSONDecodeError:
            decoded = None
        if isinstance(decoded, str):
            digits = decoded.strip()
        elif isinstance(decoded, int):
            digits = str(decoded)
        else:
            digits = text
    else:
        raise TypeError("rental_reservation_number must be a string or int")

    if len(digits) != 10 or not digits.isdigit():
        raise ValueError(
            "rental_reservation_number must be exactly 10 decimal digits "
            f"(got {digits!r})"
        )
    return _require_ten_digit_reservation_number(int(digits))


def _profile_info_from_row(row: object) -> ProfileInfo:
    if not isinstance(row, dict):
        raise ValueError("Each entry in profiles must be a JSON object")
    raw: dict[str, object] = row
    pid_raw = _get_first(raw, "profile_id", "ProfileId", "profileId")
    if pid_raw is None:
        raise ValueError(
            "Profile missing profile_id "
            f"(tried snake/Pascal/camel keys; keys: {list(raw.keys())})"
        )
    profile_id = _scalar_to_str(pid_raw, "profile_id")
    corp_raw = _get_first(
        raw,
        "corporate_customer_id",
        "CorporateCustomerId",
        "corporateCustomerId",
    )
    if corp_raw is None:
        corporate_customer_id = ""
    else:
        corporate_customer_id = _scalar_to_str(corp_raw, "corporate_customer_id")
    return ProfileInfo(
        profile_id=profile_id,
        corporate_customer_id=corporate_customer_id,
    )


def _profiles_by_email_from_response(data: object) -> ProfilesByEmailResult:
    if not isinstance(data, dict):
        raise ValueError("GetProfilesByEmailAddress response must be a JSON object")
    raw: dict[str, object] = data
    raw_list = _get_first(raw, "profiles", "Profiles")
    if raw_list is None:
        raise ValueError(
            "Response missing profiles list "
            f"(tried 'profiles', 'Profiles'; top-level keys: {list(raw.keys())})"
        )
    if not isinstance(raw_list, list):
        raise TypeError("profiles must be a JSON array")

    profiles = [_profile_info_from_row(item) for item in raw_list]

    person_raw = _get_first(raw, "person_id", "PersonId", "personId")
    if person_raw is None:
        raise ValueError(
            "Response missing person_id "
            f"(tried snake/Pascal/camel; top-level keys: {list(raw.keys())})"
        )
    member_raw = _get_first(raw, "member_id", "MemberId", "memberId")
    if member_raw is None:
        raise ValueError(
            "Response missing member_id "
            f"(tried snake/Pascal/camel; top-level keys: {list(raw.keys())})"
        )
    return ProfilesByEmailResult(
        profiles=profiles,
        person_id=_scalar_to_str(person_raw, "person_id"),
        member_id=_scalar_to_str(member_raw, "member_id"),
    )


# --- public API ---


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


def create_customer_share_a_car(
    user_type: str = "SAC",
    test_case_id: str = "tdm-generated",
) -> str:
    """Create a Share-a-car customer and return the new user's email address."""
    if not isinstance(user_type, str) or not isinstance(test_case_id, str):
        raise TypeError("user_type and test_case_id must be strings")
    user_type_s = user_type.strip()
    test_case_id_s = test_case_id.strip()
    if not user_type_s:
        raise ValueError("user_type must be a non-empty string")
    if not test_case_id_s:
        raise ValueError("test_case_id must be a non-empty string")

    access_token = get_client_credentials_access_token()
    share_car_user_url = require_env("TEST_PARAM_SHARE_CAR_USER_URL")

    response = requests.post(
        share_car_user_url,
        headers={
            "Accept": "application/json, text/plain, */*",
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "Origin": "https://lynx-stage.goorange.sixt.com",
            "Referer": "https://lynx-stage.goorange.sixt.com/",
            "X-Correlation-Id": str(uuid.uuid4()),
        },
        json={"userType": user_type_s, "tcId": test_case_id_s},
        timeout=HTTP_TIMEOUT_SECONDS,
    )
    response.raise_for_status()

    return _address_from_share_car_name_field(response.json())


def create_reservation_guest_user(
    pickup_station: int = 4,
    return_station: int = 4,
    pickup_date: str = "@@date(+3d)",
    return_date: str = "@@date(+6d)",
    prepaid: bool = False,
) -> int:
    """creates a rental reservation for a guest user and returns the reservation
    number."""
    if not isinstance(prepaid, bool):
        raise TypeError("prepaid must be a bool")
    if not isinstance(pickup_date, str) or not isinstance(return_date, str):
        raise TypeError("pickup_date and return_date must be strings")
    _validate_station_id("pickup_station", pickup_station)
    _validate_station_id("return_station", return_station)

    access_token = get_client_credentials_access_token()
    reservation_url = require_env("TEST_PARAM_RENTAL_RESERVATION_V2_URL")
    payload = _rental_reservation_v2_payload(
        pickup_station=pickup_station,
        return_station=return_station,
        pickup_date=pickup_date,
        return_date=return_date,
        prepaid=prepaid,
    )

    response = requests.post(
        reservation_url,
        headers={
            "Accept": "application/json, text/plain, */*",
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "Referer": "https://lynx-stage.goorange.sixt.com/",
            "X-Correlation-Id": str(uuid.uuid4()),
        },
        json=payload,
        timeout=HTTP_TIMEOUT_SECONDS,
    )
    response.raise_for_status()

    return _rental_reservation_number_from_response(response.json())


def create_reservation_logged_in_user(
    email_address: str,
    pickup_station: int = 4,
    return_station: int = 4,
    pickup_date: str = "@@date(+3d)",
    return_date: str = "@@date(+6d)",
    prepaid: bool = False,
) -> int:
    """creates a rental reservation for a logged-in user and returns the reservation
    number."""
    if not isinstance(prepaid, bool):
        raise TypeError("prepaid must be a bool")
    if not isinstance(pickup_date, str) or not isinstance(return_date, str):
        raise TypeError("pickup_date and return_date must be strings")
    if not isinstance(email_address, str):
        raise TypeError("email_address must be a string")
    assert email_address.strip(), "email_address must be non-blank"
    email_for_lookup = email_address.strip()
    _validate_station_id("pickup_station", pickup_station)
    _validate_station_id("return_station", return_station)

    access_token = get_client_credentials_access_token()
    profiles_result = get_profiles_by_email_address(email_for_lookup)
    if not profiles_result["profiles"]:
        raise ValueError(
            "get_profiles_by_email_address returned an empty profiles list "
            f"for email_address={email_for_lookup!r}"
        )
    person_id_clean = _require_nonblank_numeric_id(
        "person_id",
        _id_argument_as_str("person_id", profiles_result["person_id"]),
    )
    first_profile = profiles_result["profiles"][0]
    profile_id_clean = _require_nonblank_numeric_id(
        "profile_id",
        _id_argument_as_str("profile_id", first_profile["profile_id"]),
    )

    reservation_url = require_env("TEST_PARAM_RENTAL_RESERVATION_V2_URL")
    payload = _rental_reservation_v2_payload(
        pickup_station=pickup_station,
        return_station=return_station,
        pickup_date=pickup_date,
        return_date=return_date,
        prepaid=prepaid,
        profile_id=profile_id_clean,
        person_id=person_id_clean,
    )

    response = requests.post(
        reservation_url,
        headers={
            "Accept": "application/json, text/plain, */*",
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "Referer": "https://lynx-stage.goorange.sixt.com/",
            "X-Correlation-Id": str(uuid.uuid4()),
        },
        json=payload,
        timeout=HTTP_TIMEOUT_SECONDS,
    )
    response.raise_for_status()

    return _rental_reservation_number_from_response(response.json())


def create_user_and_reservation() -> tuple[str, int]:
    """Create a Share-a-car user and a rental reservation for that user.

    Returns ``(email_address, reservation_number)`` from
    ``create_customer_share_a_car`` and ``create_reservation_logged_in_user``.
    """
    email_address = create_customer_share_a_car()
    reservation_number = create_reservation_logged_in_user(email_address)
    return email_address, reservation_number


def get_profiles_by_email_address(email: str) -> ProfilesByEmailResult:
    """returns the list of profiles and the person id for the given email address"""
    if not isinstance(email, str):
        raise TypeError("email must be a string")
    text = email.strip()
    if not text:
        raise ValueError("email must be a non-empty string")

    access_token = get_client_credentials_access_token()
    url = require_env("TEST_PARAM_GET_PROFILES_BY_EMAIL_URL")

    response = requests.post(
        url,
        headers={
            "Accept": "application/json, text/plain, */*",
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "Origin": "https://lynx-stage.goorange.sixt.com",
            "Referer": "https://lynx-stage.goorange.sixt.com/",
            "X-Correlation-Id": str(uuid.uuid4()),
        },
        json={"email_address": text},
        timeout=HTTP_TIMEOUT_SECONDS,
    )
    response.raise_for_status()

    return _profiles_by_email_from_response(response.json())


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
