"""Full `ols` sync runs against a real Overleaf Community Edition server."""
import functools
import pickle

import pytest
from click.testing import CliRunner

from olsync import olsync as cli
from olsync.olclient import OverleafClient

pytestmark = pytest.mark.integration


@pytest.fixture
def ce_project(ce_project_per_test):
    """One project per test: every sync downloads the project zip, and Overleaf allows only 10 per minute per project"""
    return ce_project_per_test


@pytest.fixture
def ols(ce_server, ce_login, ce_project, tmp_path, monkeypatch):
    """Runs `ols` for the test's project in a local sync folder. Returns (run, sync_dir)."""
    cookies, csrf = ce_login
    auth = tmp_path / "olauth"
    auth.write_bytes(pickle.dumps({"cookie": cookies, "csrf": csrf}))
    sync_dir = tmp_path / "project"
    sync_dir.mkdir()
    # Until the CLI has a --server option, point its client at the CE server
    monkeypatch.setattr(cli, "OverleafClient", functools.partial(OverleafClient, base_url=ce_server))
    monkeypatch.chdir(tmp_path)

    def run(*args, input=None):
        result = CliRunner().invoke(cli.main, [*args, "-n", ce_project["name"], "--store-path", str(auth),
                                               "-p", str(sync_dir)], input=input, catch_exceptions=False)
        assert result.exit_code == 0, result.output
        return result
    return run, sync_dir


def test_remote_only_downloads_the_project(ols):
    run, sync_dir = ols
    run("-r")
    assert (sync_dir / "main.tex").read_bytes().startswith(b"\\documentclass")


def test_local_only_uploads_new_files(ols, ce_tree, ce_content):
    run, sync_dir = ols
    run("-r")
    (sync_dir / "cli").mkdir()
    (sync_dir / "cli" / "new.tex").write_bytes(b"% from the CLI\n")
    run("-l")
    assert ce_content(ce_tree()["cli/new.tex"]) == b"% from the CLI\n"


def test_local_only_deletes_remote_files_after_confirmation(ols, ce_tree):
    run, sync_dir = ols
    run("-r")
    (sync_dir / "delete-me.tex").write_bytes(b"x")
    run("-l")
    assert "delete-me.tex" in ce_tree()
    (sync_dir / "delete-me.tex").unlink()
    run("-l", input="d\n" * 10)
    assert "delete-me.tex" not in ce_tree()


def test_olignore_keeps_local_files_off_overleaf(ols, ce_tree):
    run, sync_dir = ols
    run("-r")
    (sync_dir / ".olignore").write_text("*.log\nbuild/*\n")
    (sync_dir / "kept.tex").write_bytes(b"x")
    (sync_dir / "ignored.log").write_bytes(b"x")
    (sync_dir / "build").mkdir()
    (sync_dir / "build" / "out.pdf").write_bytes(b"x")
    run("-l")
    tree = ce_tree()
    assert "kept.tex" in tree
    assert "ignored.log" not in tree
    assert "build/out.pdf" not in tree


def test_two_way_sync_uploads_local_and_keeps_remote_files(ols, ce_tree):
    run, sync_dir = ols
    run("-r")
    (sync_dir / "two-way.tex").write_bytes(b"x")
    run()
    assert "two-way.tex" in ce_tree()
    assert (sync_dir / "main.tex").exists()


def test_download_pdf(ols, ce_project, tmp_path):  # ols writes the auth file
    out = tmp_path / "out"
    out.mkdir()
    # `download` has no -p option, it takes --download-path instead
    result = CliRunner().invoke(cli.main, ["download", "-n", ce_project["name"], "--store-path",
                                           str(tmp_path / "olauth"), "--download-path", str(out)],
                                catch_exceptions=False)
    assert result.exit_code == 0, result.output
    assert next(out.glob("*.pdf")).read_bytes().startswith(b"%PDF-")
