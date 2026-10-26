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
    result = CliRunner().invoke(cli.main, ["login", "--auth-file", str(tmp_path / ".olauth")])
    assert result.exit_code != 0
    assert "overleaf-sync[gui]" in result.output


def test_version_is_defined():
    assert olsync.__version__


def test_every_command_and_option_is_described_in_the_help():
    main_help = CliRunner().invoke(cli.main, ["--help"]).output
    for command in ("download", "list", "login"):
        line = next(line for line in main_help.splitlines() if line.strip().startswith(command))
        assert line.strip() != command, f"`{command}` has no description in `ols --help`"
    assert "--download-path PATH  " in CliRunner().invoke(cli.main, ["download", "--help"]).output


def test_olignore_help_does_not_claim_it_is_ignored_for_remote_syncs():
    # .olignore selects the local files in two-way mode and filters the local deletion candidates with -r (#72)
    help_text = " ".join(CliRunner().invoke(cli.main, ["--help"]).output.split())
    assert "ignored if syncing from remote" not in help_text
