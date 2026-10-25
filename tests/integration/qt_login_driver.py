"""
Helper for test_login_window.py: runs the real Qt login window offscreen against a server, fills in and submits the
login form, and prints the result as JSON. Runs in its own process because Qt allows one application per process.
Usage: python qt_login_driver.py SERVER EMAIL PASSWORD
"""
import json
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-gpu --no-sandbox")

from PySide6.QtCore import QCoreApplication, QTimer  # noqa: E402

from olsync import olbrowserlogin  # noqa: E402

server, email, password = sys.argv[1:4]
FILL_AND_SUBMIT = """
(function () {
  const set = (el, value) => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(el, value);
    el.dispatchEvent(new Event('input', {bubbles: true}));
  };
  set(document.querySelector('input[name=email]'), %s);
  set(document.querySelector('input[name=password]'), %s);
  document.querySelector('form button[type=submit]').click();
})()
""" % (json.dumps(email), json.dumps(password))

original_handler = olbrowserlogin.OlBrowserLoginWindow.handle_load_finished


def handle_load_finished(self):
    if self.webview.url().toString().rstrip("/").endswith("/login"):
        self.webview.page().runJavaScript(FILL_AND_SUBMIT)
    original_handler(self)


olbrowserlogin.OlBrowserLoginWindow.handle_load_finished = handle_load_finished
QTimer.singleShot(120000, QCoreApplication.quit)  # never hang if the login doesn't complete
store = olbrowserlogin.login(server)
print(json.dumps({"cookie_names": sorted(store["cookie"]) if store else None, "csrf": bool(store and store["csrf"])}))
