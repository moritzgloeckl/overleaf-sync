"""Full `ols` sync runs against a real Overleaf Community Edition server."""
import pickle

import pytest
from click.testing import CliRunner

from olsync import olsync as cli

pytestmark = pytest.mark.integration


@pytest.fixture
def ce_project(ce_project_per_test):
    """One project per test: every sync downloads the project zip, and Overleaf allows only 10 per minute per project"""
    return ce_project_per_test


@pytest.fixture
def ols(ce_server, ce_login, ce_project, tmp_path, monkeypatch):
    """
    Logs in to the CE server with `ols login --cookie --server` (as a user of a self-hosted server would), then runs
    `ols` for the test's project in a local sync folder, without --server: the server comes from the auth file.
    Returns (run, sync_dir).
    """
    cookies, _ = ce_login
    auth = tmp_path / "olauth"
    monkeypatch.setenv("OLSYNC_COOKIE", cookies["overleaf.sid"])
    monkeypatch.delenv("OLSYNC_SERVER", raising=False)
    login = CliRunner().invoke(cli.main, ["login", "--cookie", "--server", ce_server, "--path", str(auth)],
                               catch_exceptions=False)
    assert login.exit_code == 0, login.output
    sync_dir = tmp_path / "project"
    sync_dir.mkdir()
    monkeypatch.chdir(tmp_path)

    def run(*args, input=None):
        result = CliRunner().invoke(cli.main, [*args, "-n", ce_project["name"], "--store-path", str(auth),
                                               "-p", str(sync_dir)], input=input, catch_exceptions=False)
        assert result.exit_code == 0, result.output
        return result
    return run, sync_dir


def test_login_stores_the_self_hosted_server(ols, tmp_path, ce_server):
    store = pickle.loads((tmp_path / "olauth").read_bytes())
    assert store["server"] == ce_server
    assert set(store["cookie"]) == {"overleaf.sid"}


def test_list_uses_the_server_from_the_auth_file(ols, ce_project, tmp_path):
    result = CliRunner().invoke(cli.main, ["list", "--store-path", str(tmp_path / "olauth")], catch_exceptions=False)
    assert result.exit_code == 0, result.output
    assert ce_project["name"] in result.output


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


def remote_edit(ce_client, ce_project, path, content):
    """Change a file on Overleaf, as if edited online"""
    import io
    infos = ce_client.get_project_infos(ce_project["id"])
    assert ce_client.upload_file(ce_project["id"], infos, path, len(content), io.BytesIO(content))


def test_two_way_sync_keeps_local_and_remote_edits(ols, ce_client, ce_project, ce_tree, ce_content):
    run, sync_dir = ols
    run()  # first sync: downloads main.tex and records the sync state
    (sync_dir / "local.tex").write_bytes(b"v1")
    remote_edit(ce_client, ce_project, "remote.tex", b"v1")
    run()
    assert (sync_dir / "remote.tex").read_bytes() == b"v1"

    (sync_dir / "local.tex").write_bytes(b"v2, edited locally")
    remote_edit(ce_client, ce_project, "remote.tex", b"v2, edited on Overleaf")
    result = run()
    assert "Conflict" not in result.output
    assert ce_content(ce_tree()["local.tex"]) == b"v2, edited locally"
    assert (sync_dir / "remote.tex").read_bytes() == b"v2, edited on Overleaf"
    assert (sync_dir / "local.tex").read_bytes() == b"v2, edited locally"


def test_two_way_sync_asks_when_both_sides_changed(ols, ce_client, ce_project, ce_tree, ce_content):
    run, sync_dir = ols
    run()
    (sync_dir / "both.tex").write_bytes(b"v1")
    run()
    (sync_dir / "both.tex").write_bytes(b"local edit")
    remote_edit(ce_client, ce_project, "both.tex", b"remote edit")
    result = run(input="l\n")
    assert "Conflict" in result.output and "both.tex" in result.output
    assert ce_content(ce_tree()["both.tex"]) == b"local edit"
    assert (sync_dir / "both.tex").read_bytes() == b"local edit"
