"""End-to-end CLI behaviour with a fake OverleafClient (no network)."""
import io
import pickle
import zipfile

import pytest
from click.testing import CliRunner

from olsync import olsync as cli


def make_zip(files):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buf.getvalue()


class FakeClient:
    """Records calls; `remote` maps file names to bytes and is served as the project zip."""

    instances = []

    def __init__(self, cookie, csrf, base_url="https://www.overleaf.com"):
        self.cookie, self.csrf, self.base_url = cookie, csrf, base_url
        self.remote = dict(FakeClient.remote)
        self.uploaded, self.deleted = [], []
        FakeClient.instances.append(self)

    def all_projects(self):
        return [{"id": "p1", "name": "Thesis", "lastUpdated": "2026-01-02T10:00:00.000Z"},
                {"id": "p2", "name": "Paper", "lastUpdated": "2026-03-04T10:00:00.000Z"}]

    def get_project(self, name):
        return next((p for p in self.all_projects() if p["name"] == name), None)

    def get_project_infos(self, project_id):
        return {"rootFolder": [{"_id": "root", "docs": [], "fileRefs": [], "folders": []}]}

    def download_project(self, project_id):
        return make_zip(self.remote)

    def upload_file(self, project_id, project_infos, name, size, file):
        self.uploaded.append((name, file.read()))
        return True

    def delete_file(self, project_id, project_infos, name):
        self.deleted.append(name)
        return True

    def download_pdf(self, project_id):
        return "output.pdf", b"%PDF-1.5"


@pytest.fixture
def workdir(tmp_path, monkeypatch):
    """A sync folder named like the project, with a valid auth file, and a fake client."""
    project_dir = tmp_path / "Thesis"
    project_dir.mkdir()
    with open(project_dir / ".olauth", "wb") as f:
        pickle.dump({"cookie": {"overleaf_session2": "s"}, "csrf": "c"}, f)
    monkeypatch.chdir(project_dir)
    monkeypatch.setattr(cli, "OverleafClient", FakeClient)
    FakeClient.instances = []
    FakeClient.remote = {}
    return project_dir


def run(*args, input=None):
    return CliRunner().invoke(cli.main, list(args), input=input, catch_exceptions=False)


def test_missing_auth_file_is_reported(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(cli.main, [])
    assert result.exit_code != 0
    assert "Persisted Overleaf cookie not found" in result.output


def test_auth_file_is_passed_to_client(workdir):
    run("-r")
    assert FakeClient.instances[0].cookie == {"overleaf_session2": "s"}
    assert FakeClient.instances[0].csrf == "c"


def test_list_prints_projects_newest_first(workdir):
    result = run("list")
    assert result.output.index("Paper") < result.output.index("Thesis")


def test_remote_only_creates_missing_local_files(workdir):
    FakeClient.remote = {"main.tex": b"remote", "chapters/intro.tex": b"intro"}
    run("-r")
    assert (workdir / "main.tex").read_bytes() == b"remote"
    assert (workdir / "chapters" / "intro.tex").read_bytes() == b"intro"


def test_local_only_uploads_new_local_files(workdir):
    (workdir / "main.tex").write_bytes(b"local")
    run("-l")
    assert FakeClient.instances[0].uploaded == [("main.tex", b"local")]


def test_local_only_offers_to_delete_remote_files_missing_locally(workdir):
    FakeClient.remote = {"gone.tex": b"x"}
    run("-l", input="d\n")
    assert FakeClient.instances[0].deleted == ["gone.tex"]


def test_two_way_sync_never_offers_deletions(workdir):
    FakeClient.remote = {"remote_only.tex": b"r"}
    (workdir / "local_only.tex").write_bytes(b"l")
    run()
    assert (workdir / "remote_only.tex").read_bytes() == b"r"
    assert FakeClient.instances[0].uploaded == [("local_only.tex", b"l")]
    assert FakeClient.instances[0].deleted == []


def test_olignore_excludes_local_files_from_upload(workdir):
    (workdir / ".olignore").write_text("*.log\n")
    (workdir / "main.tex").write_bytes(b"x")
    (workdir / "main.log").write_bytes(b"x")
    run("-l")
    assert [name for name, _ in FakeClient.instances[0].uploaded] == ["main.tex"]


@pytest.mark.parametrize("mode", [["-l"], ["-r"], []], ids=["local-only", "remote-only", "two-way"])
def test_olignore_notice_is_printed_once(workdir, mode):
    # #60: olignore_keep_list ran (and printed its notice) once per remote file
    (workdir / ".olignore").write_text("*.log\n")
    FakeClient.remote = {f"f{i}.tex": b"x" for i in range(5)}
    for i in range(5):
        (workdir / f"f{i}.tex").write_bytes(b"x")
    result = run(*mode)
    assert result.output.count(".olignore: using") == 1


def test_project_name_option_overrides_folder_name(workdir):
    result = run("-r", "-n", "Paper")
    assert result.exit_code == 0


def test_unknown_project_fails_cleanly(workdir):
    result = CliRunner().invoke(cli.main, ["-r", "-n", "Nope"])
    assert result.exit_code != 0
    assert "Project could not be queried" in result.output


def test_download_writes_pdf_to_download_path(workdir, tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    run("download", "--download-path", str(out))
    assert (out / "output.pdf").read_bytes() == b"%PDF-1.5"
