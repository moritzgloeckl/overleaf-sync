import sys

from click.testing import CliRunner

import olsync
from olsync import olsync as cli


def test_help_works_without_pyside6(monkeypatch):
    monkeypatch.setitem(sys.modules, "PySide6", None)
    result = CliRunner().invoke(cli.main, ["--help"])
    assert result.exit_code == 0, result.output
    assert "login" in result.output


def test_login_without_pyside6_explains_how_to_install(monkeypatch, tmp_path):
    monkeypatch.setitem(sys.modules, "PySide6", None)
    monkeypatch.delitem(sys.modules, "olsync.olbrowserlogin", raising=False)
    result = CliRunner().invoke(cli.main, ["login", "--path", str(tmp_path / ".olauth")])
    assert result.exit_code != 0
    assert 'overleaf-sync[gui]' in result.output


def test_version_is_defined():
    assert olsync.__version__
