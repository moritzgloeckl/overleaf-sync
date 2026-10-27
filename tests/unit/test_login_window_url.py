"""The login window detects the dashboard even when Overleaf adds a query string or a trailing slash."""

import sys
import types

import pytest


@pytest.fixture
def olbrowserlogin(monkeypatch):
    """Import olbrowserlogin with stub PySide6 modules, so the URL check is testable without Qt."""

    class QMainWindow:
        pass

    stubs = {
        "PySide6": types.ModuleType("PySide6"),
        "PySide6.QtCore": types.ModuleType("PySide6.QtCore"),
        "PySide6.QtWidgets": types.ModuleType("PySide6.QtWidgets"),
        "PySide6.QtWebEngineWidgets": types.ModuleType("PySide6.QtWebEngineWidgets"),
        "PySide6.QtWebEngineCore": types.ModuleType("PySide6.QtWebEngineCore"),
    }
    stubs["PySide6.QtWidgets"].QMainWindow = QMainWindow
    for name in ("QWebEngineProfile", "QWebEngineSettings", "QWebEnginePage"):
        setattr(stubs["PySide6.QtWebEngineCore"], name, object)
    for name, module in stubs.items():
        monkeypatch.setitem(sys.modules, name, module)
    monkeypatch.delitem(sys.modules, "olsync.olbrowserlogin", raising=False)
    from olsync import olbrowserlogin as module

    yield module
    monkeypatch.delitem(sys.modules, "olsync.olbrowserlogin", raising=False)


@pytest.mark.parametrize(
    "url",
    [
        "https://www.overleaf.com/project",
        "https://www.overleaf.com/project/",
        "https://www.overleaf.com/project?",
        "https://www.overleaf.com/project?ref=login",
        "https://www.overleaf.com/project/?ref=login",
    ],
)
def test_dashboard_url_is_detected(olbrowserlogin, url):
    assert olbrowserlogin.is_dashboard_url(url, "https://www.overleaf.com")


@pytest.mark.parametrize(
    "url",
    [
        "https://www.overleaf.com/login",
        "https://www.overleaf.com/login?redir=/project",
        "https://www.overleaf.com/project/64f0c0ffee",
        "https://overleaf.example.com/project",
    ],
)
def test_other_urls_are_not_the_dashboard(olbrowserlogin, url):
    assert not olbrowserlogin.is_dashboard_url(url, "https://www.overleaf.com")


def test_self_hosted_dashboard_is_detected(olbrowserlogin):
    assert olbrowserlogin.is_dashboard_url("https://overleaf.example.com/project?x=1", "https://overleaf.example.com/")
