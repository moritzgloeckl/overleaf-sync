"""--auth-file on every command; the old option names still work, with a deprecation warning."""

import json
import pickle
from pathlib import Path

import pytest
import responses
from click.testing import CliRunner

from olsync import auth
from olsync import olsync as cli

FIXTURES = Path(__file__).parent.parent / "fixtures"
OVERLEAF = "https://www.overleaf.com"


class FakeClient:
    created = []

    def __init__(self, cookie=None, csrf=None, base_url=OVERLEAF):
        self.cookie, self.csrf, self.base_url = cookie, csrf, base_url
        FakeClient.created.append(self)

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
    monkeypatch.setattr(cli, "OverleafClient", FakeClient)
    FakeClient.created = []
    return project_dir


def run(*args, input=None):
    return CliRunner().invoke(cli.main, list(args), input=input)


@pytest.mark.parametrize(
    "args",
    [["list", "--auth-file", "{}"], ["download", "--auth-file", "{}"], ["--auth-file", "{}", "-r"]],
    ids=["list", "download", "sync"],
)
def test_auth_file_option(workdir, tmp_path, args):
    path = tmp_path / "login.json"
    auth.save_auth(path, {"overleaf_session2": "s"}, "c", OVERLEAF)
    result = run(*[a.format(path) for a in args])
    assert result.exit_code == 0, result.output
    assert FakeClient.created[-1].cookie == {"overleaf_session2": "s"}
    assert "deprecated" not in result.output


@pytest.mark.parametrize("args", [["list", "--store-path", "{}"], ["--store-path", "{}", "-r"]], ids=["list", "sync"])
def test_store_path_still_works_but_is_deprecated(workdir, tmp_path, args):
    path = tmp_path / "login.json"
    auth.save_auth(path, {"overleaf_session2": "s"}, "c", OVERLEAF)
    result = run(*[a.format(path) for a in args])
    assert result.exit_code == 0, result.output
    assert "--store-path is deprecated" in result.output
    assert FakeClient.created[-1].cookie == {"overleaf_session2": "s"}


def test_deprecated_options_are_hidden_from_help(workdir):
    assert "--store-path" not in run("list", "--help").output
    assert "--auth-file" in run("list", "--help").output
    assert "--path " not in run("login", "--help").output


def test_old_pickle_auth_file_asks_to_log_in_again(workdir):
    (workdir / ".olauth").write_bytes(pickle.dumps({"cookie": {"overleaf_session2": "s"}, "csrf": "c"}))
    result = run("list")
    assert result.exit_code != 0
    assert "older version" in result.output and "ols login" in result.output


def test_missing_auth_file_asks_to_log_in(workdir):
    result = run("list")
    assert result.exit_code != 0
    assert "ols login" in result.output


@pytest.fixture
def rsps():
    with responses.RequestsMock(assert_all_requests_are_fired=False) as mock:
        mock.add(
            responses.GET,
            f"{OVERLEAF}/project",
            body=(FIXTURES / "dashboard_2026.html").read_text(),
            content_type="text/html",
        )
        yield mock


@pytest.mark.parametrize("option", ["--auth-file", "--path"])
def test_login_writes_a_json_auth_file(rsps, tmp_path, option):
    path = tmp_path / "login.json"
    result = run("login", "--cookie", option, str(path), input="v\n")
    assert result.exit_code == 0, result.output
    assert json.loads(path.read_text())["cookies"] == {"overleaf_session2": "v"}
    assert ("--path is deprecated" in result.output) == (option == "--path")


def test_login_window_result_is_saved_as_json(tmp_path, monkeypatch):
    class FakeWindow:
        @staticmethod
        def login(base_url):
            return {"cookie": {"overleaf_session2": "w"}, "csrf": "c"}

    monkeypatch.setattr(cli, "load_browser_login", lambda: FakeWindow)
    path = tmp_path / "login.json"
    assert run("login", "--auth-file", str(path)).exit_code == 0
    assert auth.load_auth(path) == {"cookies": {"overleaf_session2": "w"}, "csrf": "c", "server": OVERLEAF}
