"""
Integration tests against a local Overleaf Community Edition (CE) server, no real account needed:

    docker compose -f tests/integration/compose.yml up -d --wait     # optional, the tests start it otherwise
    pytest -m integration

Set OLSYNC_CE_URL to use an already running server instead (default http://127.0.0.1:8080). If the tests start the
stack themselves they also stop it again, unless --keep-ce is passed. Overleaf rate-limits logins and project
creation, so the fixtures log in once per test run and create one project per test module.
"""
import os
import subprocess
import time
import uuid
from pathlib import Path

import pytest
import requests
from bs4 import BeautifulSoup

from olsync.olclient import OverleafClient

COMPOSE_FILE = Path(__file__).parent / "compose.yml"
# 127.0.0.1 rather than localhost: Python's cookie jar stores "localhost" cookies as "localhost.local" and never
# sends them back, which makes every POST fail the CSRF check
CE_URL = os.environ.get("OLSYNC_CE_URL", "http://127.0.0.1:8080").rstrip("/")
ADMIN_EMAIL = "olsync-test@example.com"
ADMIN_PASSWORD = "olsync-integration-tests"


def _compose(*args, timeout=None):
    subprocess.run(["docker", "compose", "-f", str(COMPOSE_FILE), *args], check=True, timeout=timeout)


def _is_up():
    try:
        return requests.get(f"{CE_URL}/status", timeout=5).ok
    except requests.RequestException:
        return False


def csrf_token(session, path="/login"):
    """The CSRF token of the session, read from a page's ol-csrfToken meta tag (/dev/csrf is disabled in the image)"""
    r = session.get(f"{CE_URL}{path}", timeout=30)
    r.raise_for_status()
    return BeautifulSoup(r.text, "html.parser").find("meta", {"name": "ol-csrfToken"})["content"]


@pytest.fixture(scope="session")
def ce_server(request):
    started = False
    if not _is_up():
        if "OLSYNC_CE_URL" in os.environ:
            pytest.fail(f"No Overleaf server reachable at {CE_URL}")
        _compose("up", "-d", "--wait", "--wait-timeout", "900", timeout=1200)
        started = True
    deadline = time.time() + 300
    while not _is_up():
        if time.time() > deadline:
            pytest.fail(f"Overleaf at {CE_URL} did not become ready")
        time.sleep(5)
    yield CE_URL
    if started and not request.config.getoption("--keep-ce"):
        _compose("down", "-v", timeout=300)


@pytest.fixture(scope="session")
def ce_login(ce_server):
    """Create the first admin user (if needed) and log in once. Returns (cookies, csrf)."""
    session = requests.Session()
    # Only works on a fresh server; afterwards the admin already exists, which is fine
    session.post(f"{ce_server}/launchpad/register_admin", timeout=60,
                 json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD, "_csrf": csrf_token(session, "/launchpad")})
    r = session.post(f"{ce_server}/login", timeout=60,
                     json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD, "_csrf": csrf_token(session)})
    assert r.ok, f"Login failed: HTTP {r.status_code} {r.text[:200]}"
    # The session (and its CSRF token) changes on login
    return session.cookies.get_dict(), csrf_token(session, "/project")


@pytest.fixture(scope="session")
def ce_credentials(ce_login):
    """Email and password of the test admin user (which ce_login makes sure exists)"""
    return ADMIN_EMAIL, ADMIN_PASSWORD


@pytest.fixture(scope="session")
def ce_client(ce_login):
    cookies, csrf = ce_login
    return OverleafClient(cookies, csrf, base_url=CE_URL)


def create_project(ce_login):
    cookies, csrf = ce_login
    name = f"olsync-it-{uuid.uuid4().hex[:8]}"
    r = requests.post(f"{CE_URL}/project/new", cookies=cookies, headers={"X-Csrf-Token": csrf},
                      json={"projectName": name, "template": "none"}, timeout=60)
    r.raise_for_status()
    return {"id": r.json()["project_id"], "name": name}


def delete_project(ce_login, project):
    cookies, csrf = ce_login
    requests.delete(f"{CE_URL}/Project/{project['id']}", cookies=cookies, headers={"X-Csrf-Token": csrf}, timeout=60)


@pytest.fixture(scope="module")
def ce_project(ce_login):
    """A fresh project (with main.tex) per test module, deleted afterwards. Returns {"id", "name"}.
    Overleaf allows only 10 zip downloads per minute per project; modules that sync a lot override this fixture
    with ce_project_per_test (see test_cli_roundtrip.py)."""
    project = create_project(ce_login)
    yield project
    delete_project(ce_login, project)


@pytest.fixture
def ce_project_per_test(ce_login):
    """Like ce_project, but a new project for every test"""
    project = create_project(ce_login)
    yield project
    delete_project(ce_login, project)


@pytest.fixture
def ce_tree(ce_client, ce_project):
    """Returns a function that fetches the current project tree as {path: (type, id)}, folders end with '/'."""
    def tree():
        entries = {}

        def walk(folder, prefix):
            for doc in folder.get("docs", []):
                entries[prefix + doc["name"]] = ("doc", doc["_id"])
            for file in folder.get("fileRefs", []):
                entries[prefix + file["name"]] = ("file", file["_id"])
            for sub in folder.get("folders", []):
                entries[prefix + sub["name"] + "/"] = ("folder", sub["_id"])
                walk(sub, prefix + sub["name"] + "/")

        walk(ce_client.get_project_infos(ce_project["id"])["rootFolder"][0], "")
        return entries
    return tree


@pytest.fixture
def ce_content(ce_login, ce_project):
    """Returns a function that downloads one doc or file by (type, id) directly, bypassing the zip."""
    cookies, _ = ce_login

    def content(entry):
        kind, entity_id = entry
        suffix = "/download" if kind == "doc" else ""
        r = requests.get(f"{CE_URL}/project/{ce_project['id']}/{kind}/{entity_id}{suffix}", cookies=cookies, timeout=60)
        r.raise_for_status()
        return r.content
    return content
