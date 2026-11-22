"""Browser session reuse"""

##################################################
# MIT License
##################################################
# File: browsercookies.py
# Description: Reads the Overleaf session cookies from a browser that is logged in (`ols login --browser`)
# Author: Moritz Glöckl
# License: MIT
##################################################

from urllib.parse import urlsplit

# Browsers that can be read, in the order `ols login --browser` (without a name) tries them; the names are the
# functions of browser_cookie3
BROWSERS = [
    "chrome",
    "firefox",
    "edge",
    "brave",
    "chromium",
    "vivaldi",
    "opera",
    "opera_gx",
    "arc",
    "librewolf",
    "safari",
]

MISSING_LIBRARY_MESSAGE = (
    'Logging in with a browser\'s session needs browser-cookie3. Install it with: pip install "overleaf-sync[browser]"'
    "\nAlternatively, copy the session cookie yourself: ols login --cookie"
)


class MissingLibraryError(Exception):
    """browser-cookie3 (the `browser` extra) is not installed"""


class BrowserReadError(Exception):
    """The browser's cookie store could not be read (not installed, locked, or its cookies can't be decrypted)"""


def domain_matches(cookie_domain, host):
    """True if a cookie set for `cookie_domain` (e.g. `.overleaf.com`) is sent to `host` (e.g. `www.overleaf.com`)"""
    domain = cookie_domain.lstrip(".").lower()
    return host == domain or host.endswith("." + domain)


def read_session_cookies(browser, server, cookie_names):
    """
    Read the session cookies of an Overleaf server from a browser's cookie store. Only cookies of the server's domain
    are requested from the browser, and only the given, unexpired ones are returned.
    Params: browser (a name from BROWSERS), server (base URL), cookie_names (names of the cookies to return)
    Returns: dict of cookie name to value, empty if the browser has no session for the server
    """
    try:
        import browser_cookie3
    except ImportError as e:
        if e.name != "browser_cookie3":
            raise
        raise MissingLibraryError(MISSING_LIBRARY_MESSAGE) from None

    host = urlsplit(server).hostname.lower()
    # browser_cookie3 filters by substring: "overleaf.com" also finds cookies for ".overleaf.com" when the server is
    # www.overleaf.com. Cookies of lookalike domains are dropped by domain_matches below.
    domain_filter = host.removeprefix("www.")
    try:
        jar = getattr(browser_cookie3, browser)(domain_name=domain_filter)
        cookies = list(jar)
    except Exception as e:  # BrowserCookieError, but also e.g. sqlite3, OS keyring or decryption errors
        raise BrowserReadError(str(e) or type(e).__name__) from e
    return {
        cookie.name: cookie.value
        for cookie in cookies
        if cookie.name in cookie_names and domain_matches(cookie.domain, host) and not cookie.is_expired()
    }
