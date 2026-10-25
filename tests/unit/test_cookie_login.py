"""`ols login --cookie`: log in without the Qt window, e.g. on a headless server (#80) or with SSO (#83)."""

import sys
from pathlib import Path

import pytest
import responses
from click.testing import CliRunner

from olsync import auth as olauth
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
    rsps.add(responses.GET, PROJECT_URL, body=(FIXTURES / "dashboard_2026.html").read_text(), content_type="text/html")


def test_login_with_cookie_from_hidden_prompt_writes_auth_file(no_pyside, rsps, tmp_path):
    dashboard_ok(rsps)
    auth = tmp_path / ".olauth"
    result = CliRunner().invoke(cli.main, ["login", "--cookie", "--auth-file", str(auth)], input="s3cret\n")
    assert result.exit_code == 0, result.output
    assert "s3cret" not in result.output
    assert olauth.load_auth(auth) == {
        "cookies": {"overleaf_session2": "s3cret"},
        "csrf": "csrf-from-page",
        "server": "https://www.overleaf.com",
    }
    assert rsps.calls[0].request.headers["Cookie"] == "overleaf_session2=s3cret"


def test_login_with_cookie_from_environment(no_pyside, rsps, tmp_path, monkeypatch):
    dashboard_ok(rsps)
    monkeypatch.setenv("OLSYNC_COOKIE", "from-env")
    auth = tmp_path / ".olauth"
    result = CliRunner().invoke(cli.main, ["login", "--cookie", "--auth-file", str(auth)])
    assert result.exit_code == 0, result.output
    assert olauth.load_auth(auth)["cookies"] == {"overleaf_session2": "from-env"}


def test_login_with_invalid_cookie_fails_and_writes_nothing(no_pyside, rsps, tmp_path):
    rsps.add(responses.GET, PROJECT_URL, status=302, headers={"Location": "/login"})
    auth = tmp_path / ".olauth"
    result = CliRunner().invoke(cli.main, ["login", "--cookie", "--auth-file", str(auth)], input="expired\n")
    assert result.exit_code != 0
    assert "not valid" in result.output
    assert not auth.exists()


@pytest.fixture
def broken_pyside(monkeypatch):
    """PySide6 is installed but can't be loaded, e.g. next to Anaconda's Qt on Windows (#59)."""
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name.startswith("PySide6"):
            raise ImportError("DLL load failed while importing QtWidgets: The specified procedure could not be found.")
        return real_import(name, *args, **kwargs)

    monkeypatch.delitem(sys.modules, "olsync.olbrowserlogin", raising=False)
    monkeypatch.setattr(builtins, "__import__", fake_import)


def test_login_window_failing_to_load_explains_the_problem_and_the_cookie_login(broken_pyside, tmp_path):
    result = CliRunner().invoke(cli.main, ["login", "--auth-file", str(tmp_path / ".olauth")])
    assert result.exit_code != 0
    assert "No module named 'olbrowserlogin'" not in str(result.exception) + result.output
    assert "DLL load failed" in result.output
    assert "ols login --cookie" in result.output


def test_missing_pyside6_mentions_the_cookie_login(no_pyside, tmp_path):
    # #74: on older Linux distributions (glibc < 2.34) PySide6 >= 6.5 can't be installed at all
    result = CliRunner().invoke(cli.main, ["login", "--auth-file", str(tmp_path / ".olauth")])
    assert result.exit_code != 0
    assert "ols login --cookie" in result.output
