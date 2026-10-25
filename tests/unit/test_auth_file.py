"""The auth file (.olauth) is JSON, private to the user, and old pickle files are never unpickled."""

import json
import os
import pickle
import sys

import pytest

from olsync import auth

SERVER = "https://www.overleaf.com"


def test_round_trip(tmp_path):
    path = tmp_path / ".olauth"
    auth.save_auth(path, {"overleaf_session2": "s"}, "csrf", SERVER)
    assert auth.load_auth(path) == {"cookies": {"overleaf_session2": "s"}, "csrf": "csrf", "server": SERVER}


def test_file_format_is_versioned_json(tmp_path):
    path = tmp_path / ".olauth"
    auth.save_auth(path, {"overleaf.sid": "s"}, "csrf", "http://ce.example.test")
    assert json.loads(path.read_text()) == {
        "version": 2,
        "server": "http://ce.example.test",
        "cookies": {"overleaf.sid": "s"},
        "csrf": "csrf",
    }


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX file permissions")
def test_file_is_only_readable_by_the_user(tmp_path):
    path = tmp_path / ".olauth"
    auth.save_auth(path, {"overleaf_session2": "s"}, "csrf", SERVER)
    assert oct(path.stat().st_mode & 0o777) == oct(0o600)


def test_save_overwrites_atomically_without_leftovers(tmp_path):
    path = tmp_path / ".olauth"
    auth.save_auth(path, {"a": "1"}, "c", SERVER)
    auth.save_auth(path, {"b": "2"}, "c", SERVER)
    assert auth.load_auth(path)["cookies"] == {"b": "2"}
    assert [p.name for p in tmp_path.iterdir()] == [".olauth"]


def test_missing_file_explains_how_to_log_in(tmp_path):
    with pytest.raises(auth.AuthFileError, match="ols login"):
        auth.load_auth(tmp_path / ".olauth")


class _Marker:
    """Unpickling this would create a marker file; loading the auth file must never do that"""

    def __init__(self, path):
        self.path = path

    def __reduce__(self):
        return (open, (self.path, "w"))


def test_old_pickle_file_is_never_unpickled(tmp_path):
    marker = tmp_path / "unpickled"
    path = tmp_path / ".olauth"
    path.write_bytes(pickle.dumps({"cookie": _Marker(str(marker)), "csrf": "c"}))
    with pytest.raises(auth.AuthFileError, match="older version.*ols login"):
        auth.load_auth(path)
    assert not marker.exists()


@pytest.mark.parametrize("content", [b"{not json", b'{"version": 1}', b'["a"]', b'{"version": 2, "cookies": {}}'])
def test_invalid_file_explains_how_to_log_in(tmp_path, content):
    path = tmp_path / ".olauth"
    path.write_bytes(content)
    with pytest.raises(auth.AuthFileError, match="ols login"):
        auth.load_auth(path)


def test_relative_path_in_another_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    os.mkdir("sub")
    auth.save_auth("sub/.olauth", {"a": "1"}, "c", SERVER)
    assert auth.load_auth("sub/.olauth")["csrf"] == "c"
