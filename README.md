# ForeAI scripts

Small Python utilities for **ForeAI** end-to-end automation: creating test customers and rental reservations against Lynx / TDM-style APIs, and fetching one-time passwords from a test mail inbox.

## Requirements

- Python **3.10+** (use the `python3` from your PATH on macOS; Apple Silicon Macs ship with a native arm64 build)
- Dependencies: `requests`, `python-dotenv` (see `requirements.txt` or `pyproject.toml`)

The commands below assume **zsh** (default login shell on current macOS on MacBook Pro, including Apple Silicon) and a normal terminal session.

## Setup

Create a virtual environment, **activate** it, install dependencies, and configure environment variables.

```zsh
cd /path/to/com.sixt.testautomation.foreai-scripts
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Your prompt should show `(.venv)` when the environment is active. Run `deactivate` when you want to leave it.

Copy `.env.example` to `.env` in the project root and set real values for your environment (URLs and client secret from your team’s configuration). The application loads `.env` from the same directory as the scripts.

**Never commit `.env` or real secrets.** `.env.example` is a template only.

### Environment variables

| Variable | Purpose |
|----------|---------|
| `TEST_PARAM_AUTH_TOKEN_URL` | OAuth2 token endpoint (client credentials) |
| `TEST_PARAM_CLIENT_SECRET` | Client secret for `e2e-test` client credentials flow |
| `TEST_PARAM_SHARE_CAR_USER_URL` | Share-a-car user creation API |
| `TEST_PARAM_RENTAL_RESERVATION_V2_URL` | Rental reservation (v2) API |
| `TEST_PARAM_GET_PROFILES_BY_EMAIL_URL` | Resolve profiles / person by email |
| `TEST_PARAM_EMAIL_SEARCH_URL` | Test mail search (used by OTP helper) |

## Project layout

| File | Role |
|------|------|
| `tdm_adapter.py` | TDM-style helpers: token, Share-a-car user, guest/logged-in reservations, profile lookup, `create_user_and_reservation()` |
| `get_otp_code.py` | Fetch OTP from the email search API (with optional retries) |
| `main.py` | Minimal CLI: creates a user and reservation, prints the reservation number |
| `test_tdm_adapter.py` | Unit tests for `tdm_adapter` (mocked HTTP) |

## Usage

On macOS with **zsh**, open a terminal, go to the repository root, and activate the virtual environment **each time** you open a new shell (or after `deactivate`):

```zsh
cd /path/to/com.sixt.testautomation.foreai-scripts
source .venv/bin/activate
```

**Run the sample flow** (creates a Share-a-car user, then a logged-in reservation; prints the reservation number). Keep the venv activated:

```zsh
python main.py
```

**Use as a library** (from this directory or with the package on `PYTHONPATH`). Configure your editor or `python` to use the `.venv` interpreter, or run scripts with the venv activated as above:

```python
from tdm_adapter import (
    create_user_and_reservation,
    create_customer_share_a_car,
    create_reservation_guest_user,
    create_reservation_logged_in_user,
    get_profiles_by_email_address,
)

email, reservation_no = create_user_and_reservation()
```

```python
from get_otp_code import get_otp_code, get_otp_with_retries

otp = get_otp_with_retries("user@example.com")
```

Reservation payloads use Lynx/TDM placeholders such as `@@date(+3d)` and `@@person.email` where applicable; defaults match the adapters in code.

## Tests

With the repository root as the current directory and the venv active (`source .venv/bin/activate`):

```zsh
python -m unittest test_tdm_adapter.py -v
```

Tests do not call real services; they mock `requests` and token retrieval.

## Linting and format

[Ruff](https://docs.astral.sh/ruff/) is configured in `pyproject.toml`. With the venv active (install Ruff into the venv first if you use it there, or use a global install):

```zsh
ruff check .
ruff format .
```

## License and ownership

This repository is internal Sixt test automation tooling. Use and distribution are restricted to the Sixt organisation only and must follow Sixt’s internal policies.
