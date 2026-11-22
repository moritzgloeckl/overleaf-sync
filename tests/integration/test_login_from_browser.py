"""`ols login --browser` against a real Overleaf Community Edition server, reading a real Firefox cookie file (#130)."""

import sqlite3
import time

import pytest
from click.testing import CliRunner

from olsync import auth as olauth
from olsync import olsync as cli

pytestmark = pytest.mark.integration


def write_firefox_cookies(path, host, cookies):
    """A cookies.sqlite in Firefox's schema (moz_cookies) with the given {name: value} for `host`"""
    in_a_day = int(time.time()) + 24 * 3600
    with sqlite3.connect(path) as db:
        db.execute(
            "CREATE TABLE moz_cookies (id INTEGER PRIMARY KEY, originAttributes TEXT NOT NULL DEFAULT '', name TEXT, "
            "value TEXT, host TEXT, path TEXT, expiry INTEGER, lastAccessed INTEGER, creationTime INTEGER, "
            "isSecure INTEGER, isHttpOnly INTEGER, inBrowserElement INTEGER DEFAULT 0, sameSite INTEGER DEFAULT 0, "
            "rawSameSite INTEGER DEFAULT 0, schemeMap INTEGER DEFAULT 0)"
        )
        db.executemany(
            "INSERT INTO moz_cookies (host, name, value, path, expiry, isSecure, isHttpOnly) VALUES (?, ?, ?, '/', ?, 0, 1)",
            [(host, name, value, in_a_day) for name, value in cookies.items()],
        )
    db.close()


@pytest.fixture
def firefox_profile(tmp_path, monkeypatch):
    """Makes browser_cookie3 read Firefox's cookies from a file the test writes, instead of the user's profile"""
    browser_cookie3 = pytest.importorskip("browser_cookie3")
    db = tmp_path / "cookies.sqlite"
    real_firefox = browser_cookie3.firefox
    monkeypatch.setattr(browser_cookie3, "firefox", lambda **kwargs: real_firefox(cookie_file=str(db), **kwargs))
    return db


def test_login_with_the_session_of_a_logged_in_browser(ce_server, ce_login, ce_project, firefox_profile, tmp_path):
    cookies, _ = ce_login
    host = ce_server.split("://", 1)[1].split(":")[0].split("/")[0]
    write_firefox_cookies(firefox_profile, host, {"overleaf.sid": cookies["overleaf.sid"], "other": "not stored"})
    auth = tmp_path / "olauth"

    login = CliRunner().invoke(
        cli.main, ["login", "--browser", "firefox", "--server", ce_server, "--auth-file", str(auth)]
    )
    assert login.exit_code == 0, login.output
    store = olauth.load_auth(auth)
    assert store["cookies"] == {"overleaf.sid": cookies["overleaf.sid"]}
    assert store["server"] == ce_server

    listed = CliRunner().invoke(cli.main, ["list", "--auth-file", str(auth)], catch_exceptions=False)
    assert listed.exit_code == 0, listed.output
    assert ce_project["name"] in listed.output


def test_login_with_a_logged_out_browser_session_fails(ce_server, firefox_profile, tmp_path):
    host = ce_server.split("://", 1)[1].split(":")[0].split("/")[0]
    write_firefox_cookies(firefox_profile, host, {"overleaf.sid": "s%3Anot-a-session.signature"})
    auth = tmp_path / "olauth"
    login = CliRunner().invoke(
        cli.main, ["login", "--browser", "firefox", "--server", ce_server, "--auth-file", str(auth)]
    )
    assert login.exit_code != 0
    assert "not logged in" in login.output
    assert not auth.exists()
