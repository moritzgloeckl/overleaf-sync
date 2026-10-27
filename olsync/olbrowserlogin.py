"""Ol Browser Login Utility"""
##################################################
# MIT License
##################################################
# File: olbrowserlogin.py
# Description: Overleaf Browser Login Utility
# Author: Moritz Glöckl
# License: MIT
##################################################

from PySide6.QtCore import *
from PySide6.QtWidgets import *
from PySide6.QtWebEngineWidgets import *
from PySide6.QtWebEngineCore import QWebEngineProfile, QWebEngineSettings, QWebEnginePage

BASE_URL = "https://www.overleaf.com"  # The default Overleaf server
LOGIN_PATH = "/login"  # Where the user logs in
PROJECT_PATH = "/project"  # The dashboard, reached after a successful login
# JS snippet to extract the csrfToken
JAVASCRIPT_CSRF_EXTRACTOR = "document.getElementsByName('ol-csrfToken')[0].content"
# Name of the cookies we want to extract: overleaf.com's session and load balancer cookies, and the session cookie of
# self-hosted servers (Community Edition; "sharelatex.sid" before version 5)
COOKIE_NAMES = ["overleaf_session2", "GCLB", "overleaf.sid", "sharelatex.sid"]


def is_dashboard_url(url, base_url):
    """True if `url` is the project dashboard of `base_url`, ignoring a query string or a trailing slash"""
    return url.split("?", 1)[0].rstrip("/") == base_url.rstrip("/") + PROJECT_PATH


class OlBrowserLoginWindow(QMainWindow):
    """
    Overleaf Browser Login Utility
    Opens a browser window to securely login the user and returns relevant login data.
    """

    def __init__(self, base_url=BASE_URL, *args, **kwargs):
        super(OlBrowserLoginWindow, self).__init__(*args, **kwargs)

        self._base_url = base_url.rstrip("/")

        self.webview = QWebEngineView()

        self._cookies = {}
        self._csrf = ""
        self._login_success = False

        self.profile = QWebEngineProfile(self.webview)
        self.cookie_store = self.profile.cookieStore()
        self.cookie_store.cookieAdded.connect(self.handle_cookie_added)
        self.profile.setPersistentCookiesPolicy(QWebEngineProfile.NoPersistentCookies)

        self.profile.settings().setAttribute(QWebEngineSettings.JavascriptEnabled, True)

        webpage = QWebEnginePage(self.profile, self)
        self.webview.setPage(webpage)
        self.webview.load(QUrl.fromUserInput(self._base_url + LOGIN_PATH))
        self.webview.loadFinished.connect(self.handle_load_finished)

        self.setCentralWidget(self.webview)
        self.resize(600, 700)

    def handle_load_finished(self):
        def callback(result):
            self._csrf = result
            self._login_success = True
            QCoreApplication.quit()

        if is_dashboard_url(self.webview.url().toString(), self._base_url):
            self.webview.page().runJavaScript(JAVASCRIPT_CSRF_EXTRACTOR, 0, callback)

    def handle_cookie_added(self, cookie):
        cookie_name = cookie.name().data().decode("utf-8")
        if cookie_name in COOKIE_NAMES:
            self._cookies[cookie_name] = cookie.value().data().decode("utf-8")

    @property
    def cookies(self):
        return self._cookies

    @property
    def csrf(self):
        return self._csrf

    @property
    def login_success(self):
        return self._login_success


def login(base_url=BASE_URL):
    from PySide6.QtCore import QLoggingCategory

    QLoggingCategory.setFilterRules("""\
    qt.webenginecontext.info=false
    """)

    app = QApplication([])
    ol_browser_login_window = OlBrowserLoginWindow(base_url)
    ol_browser_login_window.show()
    app.exec()

    if not ol_browser_login_window.login_success:
        return None

    return {"cookie": ol_browser_login_window.cookies, "csrf": ol_browser_login_window.csrf}
