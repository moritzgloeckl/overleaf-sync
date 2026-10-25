"""Auth file handling"""

##################################################
# MIT License
##################################################
# File: auth.py
# Description: The persisted login (.olauth): session cookies, CSRF token and server, stored as JSON
# Author: Moritz Glöckl
# License: MIT
##################################################

import json
import os
import tempfile
from pathlib import Path

AUTH_VERSION = 2  # Version 1 was the pickle format of overleaf-sync <= 2.0.0a4


class AuthFileError(Exception):
    """The auth file is missing, from an older version, or invalid"""


def save_auth(path, cookies, csrf, server):
    """
    Persist the login atomically, readable only by the current user (it grants access to the Overleaf account)
    Params: path, cookies (dict of session cookies), csrf (CSRF token), server (base URL)
    """
    path = Path(path)
    data = {"version": AUTH_VERSION, "server": server, "cookies": cookies, "csrf": csrf}
    directory = path.parent if str(path.parent) else Path(".")
    fd, tmp_path = tempfile.mkstemp(dir=directory, prefix=path.name + ".", suffix=".tmp")
    try:
        os.chmod(tmp_path, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=1)
        os.replace(tmp_path, path)
    except BaseException:
        os.unlink(tmp_path)
        raise


def load_auth(path):
    """
    Load the persisted login. Old pickle files are recognised but never unpickled, since unpickling can run code.
    Params: path
    Returns: {"cookies": dict, "csrf": str, "server": str}
    """
    try:
        content = Path(path).read_bytes()
    except FileNotFoundError:
        raise AuthFileError(
            f"Persisted Overleaf login `{path}` not found. Log in with `ols login`, or check the --auth-file path."
        ) from None
    if content[:1] == b"\x80":  # pickle protocol 2+, written by overleaf-sync 2.0.0a4 and earlier
        raise AuthFileError(
            f"`{path}` was created by an older version of overleaf-sync, which used a format that is no longer "
            "supported. Please log in again with `ols login`."
        )
    try:
        data = json.loads(content)
        if data["version"] != AUTH_VERSION or not isinstance(data["cookies"], dict) or not data["cookies"]:
            raise ValueError("unsupported auth file")
        return {"cookies": data["cookies"], "csrf": data["csrf"], "server": data["server"]}
    except (ValueError, KeyError, TypeError):
        raise AuthFileError(f"`{path}` is not a valid overleaf-sync login. Please log in again with `ols login`.")
