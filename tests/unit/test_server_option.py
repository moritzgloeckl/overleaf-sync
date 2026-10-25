"""Choosing the Overleaf server: --server / OLSYNC_SERVER, the server stored at login, or overleaf.com (#65)."""
import pickle
from pathlib import Path

import pytest
import responses
from click.testing import CliRunner

from olsync import olsync as cli

FIXTURES = Path(__file__).parent.parent / "fixtures"
OVERLEAF = "https://www.overleaf.com"
CE = "http://overleaf.example.test"


class RecordingClient:
    """Fake OverleafClient that records which server it was created for."""

    created = []

    def __init__(self, cookie=None, csrf=None, base_url=OVERLEAF):
        self.cookie, self.csrf, self.base_url = cookie, csrf, base_url
        RecordingClient.created.append(self)

    def all_projects(self):
        return [{"id": "p1", "name": "Thesis", "lastUpdated": "2026-01-02T10:00:00.000Z"}]

    def get_project(self, name):
        return self.all_projects()[0]

    def get_project_infos(self, project_id):
        return {"rootFolder": [{"_id": "root", "docs": [], "fileRefs": [], "folders": []}]}

    def download_project(self, project_id):
        import io
        import zipfile
        buf = io.BytesIO()
        zipfile.ZipFile(buf, "w").close()
        return buf.getvalue()

    def download_pdf(self, project_id):
        return "output.pdf", b"%PDF-1.5"


@pytest.fixture
def workdir(tmp_path, monkeypatch):
    project_dir = tmp_path / "Thesis"
    project_dir.mkdir()
    monkeypatch.chdir(project_dir)
    monkeypatch.delenv("OLSYNC_SERVER", raising=False)
    monkeypatch.setattr(cli, "OverleafClient", RecordingClient)
    RecordingClient.created = []
    return project_dir


def write_auth(path, **extra):
    path.write_bytes(pickle.dumps({"cookie": {"overleaf.sid": "s"}, "csrf": "c", **extra}))


def server_used():
    return RecordingClient.created[-1].base_url


@pytest.mark.parametrize("args", [["list"], ["-r"], ["download"]], ids=["list", "sync", "download"])
def test_server_stored_at_login_is_used(workdir, args):
    write_auth(workdir / ".olauth", server=CE)
    result = CliRunner().invoke(cli.main, args)
    assert result.exit_code == 0, result.output
    assert server_used() == CE


def test_old_auth_files_without_server_use_overleaf_com(workdir):
    write_auth(workdir / ".olauth")
    assert CliRunner().invoke(cli.main, ["list"]).exit_code == 0
    assert server_used() == OVERLEAF


@pytest.mark.parametrize("args", [["--server", CE, "list"], ["list", "--server", CE], ["--server", CE, "-r"],
                                  ["download", "--server", CE]],
                         ids=["group-option", "command-option", "sync", "download"])
def test_server_option_overrides_the_auth_file(workdir, args):
    write_auth(workdir / ".olauth", server="http://other.example.test")
    result = CliRunner().invoke(cli.main, args)
    assert result.exit_code == 0, result.output
    assert server_used() == CE


def test_server_from_environment(workdir, monkeypatch):
    write_auth(workdir / ".olauth")
    monkeypatch.setenv("OLSYNC_SERVER", CE)
    assert CliRunner().invoke(cli.main, ["list"]).exit_code == 0
    assert server_used() == CE


def test_trailing_slash_in_server_is_ignored(workdir):
    write_auth(workdir / ".olauth")
    assert CliRunner().invoke(cli.main, ["list", "--server", CE + "/"]).exit_code == 0
    assert server_used().rstrip("/") == CE


# --- login ------------------------------------------------------------------------------------------------------

class FakeBrowserLogin:
    calls = []

    @staticmethod
    def login(base_url=OVERLEAF):
        FakeBrowserLogin.calls.append(base_url)
        return {"cookie": {"overleaf.sid": "from-window"}, "csrf": "c"}


@pytest.mark.parametrize("args", [["--server", CE, "login"], ["login", "--server", CE]],
                         ids=["group-option", "command-option"])
def test_login_window_opens_the_server_and_stores_it(tmp_path, monkeypatch, args):
    monkeypatch.setattr(cli, "load_browser_login", lambda: FakeBrowserLogin)
    FakeBrowserLogin.calls = []
    auth = tmp_path / ".olauth"
    result = CliRunner().invoke(cli.main, [*args, "--path", str(auth)])
    assert result.exit_code == 0, result.output
    assert FakeBrowserLogin.calls == [CE]
    assert pickle.loads(auth.read_bytes())["server"] == CE


def test_login_window_defaults_to_overleaf_com(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "load_browser_login", lambda: FakeBrowserLogin)
    monkeypatch.delenv("OLSYNC_SERVER", raising=False)
    FakeBrowserLogin.calls = []
    auth = tmp_path / ".olauth"
    assert CliRunner().invoke(cli.main, ["login", "--path", str(auth)]).exit_code == 0
    assert FakeBrowserLogin.calls == [OVERLEAF]
    assert pickle.loads(auth.read_bytes())["server"] == OVERLEAF


@pytest.fixture
def rsps():
    with responses.RequestsMock(assert_all_requests_are_fired=False) as mock:
        yield mock


def dashboard(rsps, server, accept_cookie):
    """The dashboard answers with the page only for the given session cookie name, otherwise redirects to /login."""
    def callback(request):
        if accept_cookie + "=" in request.headers.get("Cookie", ""):
            return 200, {"Content-Type": "text/html"}, (FIXTURES / "dashboard_2026.html").read_text()
        return 302, {"Location": "/login"}, ""
    rsps.add_callback(responses.GET, f"{server}/project", callback=callback)


@pytest.mark.parametrize("cookie_name", ["overleaf.sid", "sharelatex.sid"])
def test_cookie_login_on_a_self_hosted_server(rsps, tmp_path, cookie_name):
    # Community Edition uses overleaf.sid (sharelatex.sid before version 5) instead of overleaf_session2
    dashboard(rsps, CE, accept_cookie=cookie_name)
    auth = tmp_path / ".olauth"
    result = CliRunner().invoke(cli.main, ["login", "--cookie", "--server", CE, "--path", str(auth)], input="v\n")
    assert result.exit_code == 0, result.output
    assert pickle.loads(auth.read_bytes()) == {"cookie": {cookie_name: "v"}, "csrf": "csrf-from-page", "server": CE}


def test_cookie_login_on_overleaf_com_stores_the_server(rsps, tmp_path, monkeypatch):
    monkeypatch.delenv("OLSYNC_SERVER", raising=False)
    dashboard(rsps, OVERLEAF, accept_cookie="overleaf_session2")
    auth = tmp_path / ".olauth"
    result = CliRunner().invoke(cli.main, ["login", "--cookie", "--path", str(auth)], input="v\n")
    assert result.exit_code == 0, result.output
    assert pickle.loads(auth.read_bytes()) == {"cookie": {"overleaf_session2": "v"}, "csrf": "csrf-from-page",
                                               "server": OVERLEAF}
