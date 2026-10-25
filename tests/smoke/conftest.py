"""
Smoke tests against overleaf.com. They run LOCALLY ONLY, with a real session, and are skipped unless configured.

Configure them once in a git-ignored `.env` file in the repository root (see `.env.example`), or via environment
variables, then run:

    pytest -m smoke -v

Authentication uses a session, never a password (Overleaf's login has a captcha). Either:
  - OLSYNC_SMOKE_COOKIE: the value of the `overleaf_session2` cookie from a browser logged in to the smoke account, or
  - OLSYNC_SMOKE_AUTH: path to an auth file created with `ols login --path <file>`.
When the session expires, the tests fail with "session expired"; refresh the cookie or log in again.

Safety rules: tests only act on the pinned OLSYNC_SMOKE_PROJECT_ID, whose name must start with "olsync-smoke".
The tests in this folder are read-only; destructive tests are added once remote deletion is fixed.
"""

import os
from pathlib import Path

import pytest
import requests
from bs4 import BeautifulSoup

from olsync import auth as olauth
from olsync.olclient import OverleafClient

NAME_PREFIX = "olsync-smoke"
PROJECT_URL = "https://www.overleaf.com/project"
DOTENV = Path(__file__).resolve().parents[2] / ".env"


def load_dotenv(path=DOTENV):
    """Minimal .env reader (KEY=VALUE lines, # comments). Existing environment variables take precedence."""
    if not path.is_file():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


load_dotenv()


def _env(name):
    value = os.environ.get(name)
    if not value:
        pytest.skip(f"{name} is not set (see tests/smoke/conftest.py and .env.example)")
    return value


def _dashboard(cookies):
    """Fetch the project dashboard, failing clearly if the session is no longer valid."""
    r = requests.get(PROJECT_URL, cookies=cookies, allow_redirects=False, timeout=30)
    if r.is_redirect or r.status_code in (401, 403):
        pytest.fail("Overleaf session expired or invalid: refresh OLSYNC_SMOKE_COOKIE or run `ols login` again")
    r.raise_for_status()
    return r


@pytest.fixture(scope="session")
def smoke_client():
    if os.environ.get("OLSYNC_SMOKE_COOKIE"):
        cookies = {"overleaf_session2": os.environ["OLSYNC_SMOKE_COOKIE"]}
        csrf_tag = BeautifulSoup(_dashboard(cookies).content, "html.parser").find("meta", {"name": "ol-csrfToken"})
        return OverleafClient(cookies, csrf_tag.get("content"))

    if not os.environ.get("OLSYNC_SMOKE_AUTH"):
        pytest.skip("Set OLSYNC_SMOKE_COOKIE or OLSYNC_SMOKE_AUTH (see tests/smoke/conftest.py and .env.example)")
    auth_path = Path(os.environ["OLSYNC_SMOKE_AUTH"]).expanduser()
    store = olauth.load_auth(auth_path)
    _dashboard(store["cookies"])
    return OverleafClient(store["cookies"], store["csrf"], base_url=store["server"])


@pytest.fixture(scope="session")
def smoke_project(smoke_client):
    project_id = _env("OLSYNC_SMOKE_PROJECT_ID")
    project = next((p for p in smoke_client.all_projects() if p["id"] == project_id), None)
    assert project is not None, f"Project {project_id} not found in the smoke account's project list"
    assert project["name"].startswith(NAME_PREFIX), (
        f"Refusing to run: project {project_id} is named {project['name']!r}, not {NAME_PREFIX}*"
    )
    return project
