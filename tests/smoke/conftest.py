"""
Smoke tests against overleaf.com. They run LOCALLY ONLY, with your own session, and are skipped unless configured:

    ols login --path ~/.config/olsync-smoke/.olauth
    export OLSYNC_SMOKE_AUTH=~/.config/olsync-smoke/.olauth
    export OLSYNC_SMOKE_PROJECT_ID=<id of your "olsync-smoke" project>   # from its URL: overleaf.com/project/<id>
    pytest -m smoke -v

Safety rules: tests only act on the pinned project id, whose name must start with "olsync-smoke".
The tests in this folder are read-only; destructive tests are added once remote deletion is fixed.
"""
import os
import pickle
from pathlib import Path

import pytest

from olsync.olclient import OverleafClient

NAME_PREFIX = "olsync-smoke"


def _env(name):
    value = os.environ.get(name)
    if not value:
        pytest.skip(f"{name} is not set (see tests/smoke/conftest.py)")
    return value


@pytest.fixture(scope="session")
def smoke_client():
    auth_path = Path(_env("OLSYNC_SMOKE_AUTH")).expanduser()
    with open(auth_path, "rb") as f:
        store = pickle.load(f)
    return OverleafClient(store["cookie"], store["csrf"])


@pytest.fixture(scope="session")
def smoke_project(smoke_client):
    project_id = _env("OLSYNC_SMOKE_PROJECT_ID")
    project = next((p for p in smoke_client.all_projects() if p["id"] == project_id), None)
    assert project is not None, f"Project {project_id} not found in your project list"
    assert project["name"].startswith(NAME_PREFIX), \
        f"Refusing to run: project {project_id} is named {project['name']!r}, not {NAME_PREFIX}*"
    return project
