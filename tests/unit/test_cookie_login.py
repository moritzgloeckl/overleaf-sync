"""`ols login --cookie`: log in without the Qt window, e.g. on a headless server (#80) or with SSO (#83)."""
import pickle
import sys
from pathlib import Path

import pytest
import responses
from click.testing import CliRunner

from olsync import olsync as cli

FIXTURES = Path(__file__).parent.parent / "fixtures"
PROJECT_URL = "https://www.overleaf.com/project"


@pytest.fixture
def no_pyside(monkeypatch):
    monkeypatch.setitem(sys.modules, "PySide6", None)


@pytest.fixture
def rsps():
    with responses.RequestsMock() as mock:
        yield mock


def dashboard_ok(rsps):
    rsps.add(responses.GET, PROJECT_URL, body=(FIXTURES / "dashboard_2026.html").read_text(),
             content_type="text/html")


def test_login_with_cookie_from_hidden_prompt_writes_auth_file(no_pyside, rsps, tmp_path):
    dashboard_ok(rsps)
    auth = tmp_path / ".olauth"
    result = CliRunner().invoke(cli.main, ["login", "--cookie", "--path", str(auth)], input="s3cret\n")
    assert result.exit_code == 0, result.output
    assert "s3cret" not in result.output
    assert pickle.loads(auth.read_bytes()) == {"cookie": {"overleaf_session2": "s3cret"}, "csrf": "csrf-from-page"}
    assert rsps.calls[0].request.headers["Cookie"] == "overleaf_session2=s3cret"


def test_login_with_cookie_from_environment(no_pyside, rsps, tmp_path, monkeypatch):
    dashboard_ok(rsps)
    monkeypatch.setenv("OLSYNC_COOKIE", "from-env")
    auth = tmp_path / ".olauth"
    result = CliRunner().invoke(cli.main, ["login", "--cookie", "--path", str(auth)])
    assert result.exit_code == 0, result.output
    assert pickle.loads(auth.read_bytes())["cookie"] == {"overleaf_session2": "from-env"}


def test_login_with_invalid_cookie_fails_and_writes_nothing(no_pyside, rsps, tmp_path):
    rsps.add(responses.GET, PROJECT_URL, status=302, headers={"Location": "/login"})
    auth = tmp_path / ".olauth"
    result = CliRunner().invoke(cli.main, ["login", "--cookie", "--path", str(auth)], input="expired\n")
    assert result.exit_code != 0
    assert "not valid" in result.output
    assert not auth.exists()
