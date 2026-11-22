"""`ols login --browser`: reuse the Overleaf session of a browser that is already logged in (#130)."""

import http.cookiejar
import sqlite3
import sys
import time
import types

import pytest
import responses
from click.testing import CliRunner

from olsync import auth as olauth
from olsync import olsync as cli
from pathlib import Path

FIXTURES = Path(__file__).parent.parent / "fixtures"
PROJECT_URL = "https://www.overleaf.com/project"

SELF_HOSTED = "https://overleaf.example.com"


def make_cookie(name, value, domain, expires=None):
    return http.cookiejar.Cookie(
        version=0,
        name=name,
        value=value,
        port=None,
        port_specified=False,
        domain=domain,
        domain_specified=domain.startswith("."),
        domain_initial_dot=domain.startswith("."),
        path="/",
        path_specified=True,
        secure=True,
        expires=expires,
        discard=expires is None,
        comment=None,
        comment_url=None,
        rest={},
    )


@pytest.fixture
def no_pyside(monkeypatch):
    monkeypatch.setitem(sys.modules, "PySide6", None)


@pytest.fixture
def rsps():
    with responses.RequestsMock() as mock:
        yield mock


@pytest.fixture
def browsers(monkeypatch):
    """
    A fake browser_cookie3: `browsers.stores[name]` is the list of cookies of that browser (or an exception it raises);
    `browsers.calls` records (browser, domain_name) of every read
    """
    fake = types.ModuleType("browser_cookie3")
    fake.stores = {}
    fake.calls = []

    def loader(name):
        def load(cookie_file=None, domain_name="", key_file=None):
            fake.calls.append((name, domain_name))
            store = fake.stores.get(name, [])
            if isinstance(store, Exception):
                raise store
            jar = http.cookiejar.CookieJar()
            for cookie in store:
                # Like the real library: a substring match on the domain
                if domain_name in cookie.domain:
                    jar.set_cookie(cookie)
            return jar

        return load

    from olsync import browsercookies

    for name in browsercookies.BROWSERS:
        setattr(fake, name, loader(name))
    monkeypatch.setitem(sys.modules, "browser_cookie3", fake)
    return fake


def dashboard_ok(rsps, url=PROJECT_URL):
    rsps.add(responses.GET, url, body=(FIXTURES / "dashboard_2026.html").read_text(), content_type="text/html")


def invoke(*args, input=None):
    return CliRunner().invoke(cli.main, ["login", *args], input=input)


def test_login_from_chrome_stores_the_overleaf_session_and_nothing_else(no_pyside, browsers, rsps, tmp_path):
    browsers.stores["chrome"] = [
        make_cookie("overleaf_session2", "s3cret", ".overleaf.com"),
        make_cookie("GCLB", "lb", "www.overleaf.com"),
        make_cookie("unrelated", "x", ".overleaf.com"),
        make_cookie("overleaf_session2", "lookalike", "evil-overleaf.com"),
        make_cookie("SID", "google", ".google.com"),
    ]
    dashboard_ok(rsps)
    auth = tmp_path / ".olauth"
    result = invoke("--browser", "chrome", "--auth-file", str(auth))
    assert result.exit_code == 0, result.output
    assert "s3cret" not in result.output
    assert olauth.load_auth(auth) == {
        "cookies": {"overleaf_session2": "s3cret", "GCLB": "lb"},
        "csrf": "csrf-from-page",
        "server": "https://www.overleaf.com",
    }
    # Only Overleaf's cookies are asked for, never the whole cookie store
    assert browsers.calls == [("chrome", "overleaf.com")]
    assert "overleaf_session2=s3cret" in rsps.calls[0].request.headers["Cookie"]


def test_login_from_browser_on_a_self_hosted_server(no_pyside, browsers, rsps, tmp_path):
    browsers.stores["firefox"] = [
        make_cookie("overleaf_session2", "wrong-server", ".overleaf.com"),
        make_cookie("overleaf.sid", "ce-session", "overleaf.example.com"),
    ]
    dashboard_ok(rsps, SELF_HOSTED + "/project")
    auth = tmp_path / ".olauth"
    result = invoke("--browser", "firefox", "--server", SELF_HOSTED, "--auth-file", str(auth))
    assert result.exit_code == 0, result.output
    assert olauth.load_auth(auth)["cookies"] == {"overleaf.sid": "ce-session"}
    assert olauth.load_auth(auth)["server"] == SELF_HOSTED
    assert browsers.calls == [("firefox", "overleaf.example.com")]


def test_expired_browser_cookies_are_ignored(no_pyside, browsers, tmp_path):
    browsers.stores["chrome"] = [
        make_cookie("overleaf_session2", "old", ".overleaf.com", expires=int(time.time()) - 60)
    ]
    auth = tmp_path / ".olauth"
    result = invoke("--browser", "chrome", "--auth-file", str(auth))
    assert result.exit_code != 0
    assert "No Overleaf session found in chrome" in result.output
    assert not auth.exists()


def test_without_a_browser_name_the_first_browser_with_a_valid_session_is_used(no_pyside, browsers, rsps, tmp_path):
    from olsync import browsercookies

    first, second, third = browsercookies.BROWSERS[:3]
    browsers.stores[first] = RuntimeError("cookie database is locked")
    browsers.stores[second] = [make_cookie("overleaf_session2", "logged-out", ".overleaf.com")]
    browsers.stores[third] = [make_cookie("overleaf_session2", "valid", ".overleaf.com")]
    rsps.add(responses.GET, PROJECT_URL, status=302, headers={"Location": "/login"})
    dashboard_ok(rsps)
    auth = tmp_path / ".olauth"
    result = invoke("--browser", "--auth-file", str(auth))
    assert result.exit_code == 0, result.output
    assert olauth.load_auth(auth)["cookies"] == {"overleaf_session2": "valid"}
    assert third in result.output
    # Stops at the first valid session
    assert [name for name, _ in browsers.calls] == [first, second, third]


def test_no_session_in_any_browser_fails_with_hints(no_pyside, browsers, tmp_path):
    browsers.stores["chrome"] = RuntimeError("Unable to get key for cookie decryption")
    auth = tmp_path / ".olauth"
    result = invoke("--browser", "--auth-file", str(auth))
    assert result.exit_code != 0
    assert "No Overleaf session found in any supported browser" in result.output
    assert "ols login --browser chrome" in result.output
    assert "ols login --cookie" in result.output
    # Most browsers aren't installed at all, so read errors are only listed with -v
    assert "Unable to get key for cookie decryption" not in result.output
    assert not auth.exists()

    verbose = invoke("--browser", "-v", "--auth-file", str(auth))
    assert "chrome could not be read: Unable to get key for cookie decryption" in verbose.output


def test_unreadable_browser_explains_the_problem(no_pyside, browsers, tmp_path):
    browsers.stores["chrome"] = RuntimeError("Unable to get key for cookie decryption")
    auth = tmp_path / ".olauth"
    result = invoke("--browser", "chrome", "--auth-file", str(auth))
    assert result.exit_code != 0
    assert "could not be read" in result.output
    assert "Unable to get key for cookie decryption" in result.output
    assert "ols login --cookie" in result.output
    assert not auth.exists()


def test_logged_out_browser_session_fails_and_writes_nothing(no_pyside, browsers, rsps, tmp_path):
    browsers.stores["chrome"] = [make_cookie("overleaf_session2", "logged-out", ".overleaf.com")]
    rsps.add(responses.GET, PROJECT_URL, status=302, headers={"Location": "/login"})
    auth = tmp_path / ".olauth"
    result = invoke("--browser", "chrome", "--auth-file", str(auth))
    assert result.exit_code != 0
    assert "not logged in" in result.output
    assert not auth.exists()


def test_unknown_browser_is_a_usage_error(no_pyside, browsers, tmp_path):
    result = invoke("--browser", "netscape", "--auth-file", str(tmp_path / ".olauth"))
    assert result.exit_code == 2
    assert "netscape" in result.output


def test_browser_and_cookie_options_are_exclusive(no_pyside, browsers, tmp_path):
    result = invoke("--browser", "chrome", "--cookie", "--auth-file", str(tmp_path / ".olauth"))
    assert result.exit_code == 2
    assert "--browser" in result.output and "--cookie" in result.output


def test_missing_browser_cookie3_explains_how_to_install_it(no_pyside, monkeypatch, tmp_path):
    monkeypatch.setitem(sys.modules, "browser_cookie3", None)
    result = invoke("--browser", "chrome", "--auth-file", str(tmp_path / ".olauth"))
    assert result.exit_code != 0
    assert 'pip install "overleaf-sync[browser]"' in result.output
    assert "ols login --cookie" in result.output


def firefox_cookie_db(path, cookies):
    """A cookies.sqlite in the schema Firefox uses (moz_cookies), with (host, name, value, expiry) rows"""
    with sqlite3.connect(path) as db:
        db.execute(
            "CREATE TABLE moz_cookies (id INTEGER PRIMARY KEY, originAttributes TEXT NOT NULL DEFAULT '', name TEXT, "
            "value TEXT, host TEXT, path TEXT, expiry INTEGER, lastAccessed INTEGER, creationTime INTEGER, "
            "isSecure INTEGER, isHttpOnly INTEGER, inBrowserElement INTEGER DEFAULT 0, sameSite INTEGER DEFAULT 0, "
            "rawSameSite INTEGER DEFAULT 0, schemeMap INTEGER DEFAULT 0)"
        )
        db.executemany(
            "INSERT INTO moz_cookies (host, name, value, path, expiry, isSecure, isHttpOnly) "
            "VALUES (?, ?, ?, '/', ?, 1, 1)",
            cookies,
        )
    db.close()


def test_reads_a_real_firefox_cookie_database(tmp_path, monkeypatch):
    """The real browser_cookie3 parsing a Firefox cookie file, not a fake (skipped without the `browser` extra)"""
    browser_cookie3 = pytest.importorskip("browser_cookie3")
    from olsync import browsercookies

    db = tmp_path / "cookies.sqlite"
    in_a_year = int(time.time()) + 365 * 24 * 3600
    firefox_cookie_db(
        db,
        [
            (".overleaf.com", "overleaf_session2", "s3cret", in_a_year),
            ("www.overleaf.com", "GCLB", "lb", in_a_year),
            ("www.overleaf.com", "overleaf_session2", "expired", int(time.time()) - 60),
            ("evil-overleaf.com", "overleaf_session2", "lookalike", in_a_year),
            (".google.com", "SID", "google", in_a_year),
        ],
    )
    real_firefox = browser_cookie3.firefox
    monkeypatch.setattr(browser_cookie3, "firefox", lambda **kw: real_firefox(cookie_file=str(db), **kw))
    cookies = browsercookies.read_session_cookies("firefox", "https://www.overleaf.com", ["overleaf_session2", "GCLB"])
    assert cookies == {"overleaf_session2": "s3cret", "GCLB": "lb"}
