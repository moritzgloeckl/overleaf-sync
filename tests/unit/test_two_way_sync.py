"""Two-way sync (`ols` without -l/-r) never overwrites changes silently: it decides per file using the sync state."""

import io
import os
import pickle
import time
import zipfile

import pytest
from click.testing import CliRunner

from olsync import olsync as cli


class FakeOverleaf:
    """In-memory Overleaf project that keeps its files across several `ols` runs."""

    files = {}
    uploads = []
    last_updated = "2030-01-01T00:00:00.000Z"  # always "newer" than local files, like a project edited online

    def __init__(self, cookie=None, csrf=None, base_url="https://www.overleaf.com"):
        self.base_url = base_url

    def get_project(self, name):
        return {"id": "p1", "name": name, "lastUpdated": FakeOverleaf.last_updated}

    def get_project_infos(self, project_id):
        return {"rootFolder": [{"_id": "root", "docs": [], "fileRefs": [], "folders": []}]}

    def download_project(self, project_id):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            for name, content in FakeOverleaf.files.items():
                zf.writestr(name, content)
        return buf.getvalue()

    def upload_file(self, project_id, project_infos, name, size, file):
        FakeOverleaf.files[name] = file.read()
        FakeOverleaf.uploads.append(name)
        return True


@pytest.fixture
def project(tmp_path, monkeypatch):
    project_dir = tmp_path / "Thesis"
    project_dir.mkdir()
    (project_dir / ".olauth").write_bytes(pickle.dumps({"cookie": {"overleaf_session2": "s"}, "csrf": "c"}))
    monkeypatch.chdir(project_dir)
    monkeypatch.setattr(cli, "OverleafClient", FakeOverleaf)
    FakeOverleaf.files = {}
    FakeOverleaf.uploads = []
    return project_dir


def sync(input=None):
    result = CliRunner().invoke(cli.main, [], input=input, catch_exceptions=False)
    assert result.exit_code == 0, result.output
    FakeOverleaf.uploads, uploads = [], FakeOverleaf.uploads
    return result.output, uploads


def edit_locally(path, content):
    path.write_bytes(content)
    # make sure the local file is *older* than the project's lastUpdated, the case that used to lose data
    old = time.time() - 3600
    os.utime(path, (old, old))


def test_first_sync_downloads_and_uploads_new_files(project):
    FakeOverleaf.files = {"remote.tex": b"r"}
    (project / "local.tex").write_bytes(b"l")
    _, uploads = sync()
    assert (project / "remote.tex").read_bytes() == b"r"
    assert uploads == ["local.tex"]


def test_local_edit_is_uploaded_not_overwritten(project):
    # The data loss before 2.0.0a4: the project's lastUpdated was newer than the local file, so the local edit was
    # silently replaced by the Overleaf version
    FakeOverleaf.files = {"main.tex": b"v1"}
    sync()
    edit_locally(project / "main.tex", b"v2 local edit")
    output, uploads = sync()
    assert (project / "main.tex").read_bytes() == b"v2 local edit"
    assert FakeOverleaf.files["main.tex"] == b"v2 local edit"
    assert uploads == ["main.tex"]
    assert "Conflict" not in output


def test_remote_edit_is_downloaded_without_asking(project):
    FakeOverleaf.files = {"main.tex": b"v1"}
    sync()
    FakeOverleaf.files["main.tex"] = b"v2 edited on Overleaf"
    output, uploads = sync()
    assert (project / "main.tex").read_bytes() == b"v2 edited on Overleaf"
    assert uploads == []
    assert "Conflict" not in output


def test_unchanged_files_are_left_alone(project):
    FakeOverleaf.files = {"main.tex": b"v1"}
    sync()
    output, uploads = sync()
    assert uploads == []
    assert "Conflict" not in output


@pytest.mark.parametrize(
    "answer, expected_local, expected_remote",
    [
        ("l", b"local edit", b"local edit"),
        ("r", b"remote edit", b"remote edit"),
        ("s", b"local edit", b"remote edit"),
    ],
)
def test_edits_on_both_sides_ask_which_version_to_keep(project, answer, expected_local, expected_remote):
    FakeOverleaf.files = {"main.tex": b"v1"}
    sync()
    edit_locally(project / "main.tex", b"local edit")
    FakeOverleaf.files["main.tex"] = b"remote edit"
    output, _ = sync(input=f"{answer}\n")
    assert "Conflict" in output and "main.tex" in output
    assert (project / "main.tex").read_bytes() == expected_local
    assert FakeOverleaf.files["main.tex"] == expected_remote


def test_skipped_conflict_is_offered_again(project):
    FakeOverleaf.files = {"main.tex": b"v1"}
    sync()
    edit_locally(project / "main.tex", b"local edit")
    FakeOverleaf.files["main.tex"] = b"remote edit"
    sync(input="s\n")
    output, _ = sync(input="s\n")
    assert "Conflict" in output


def test_first_sync_asks_about_differing_files(project):
    # No sync history yet: never guess which version is newer
    FakeOverleaf.files = {"main.tex": b"remote version"}
    edit_locally(project / "main.tex", b"local version")
    output, uploads = sync(input="s\n")
    assert "Conflict" in output
    assert (project / "main.tex").read_bytes() == b"local version"
    assert FakeOverleaf.files["main.tex"] == b"remote version"


def test_state_file_stays_local(project):
    FakeOverleaf.files = {"main.tex": b"v1"}
    sync()
    assert (project / ".olsync-state.json").is_file()
    _, uploads = sync()
    assert ".olsync-state.json" not in FakeOverleaf.files
    assert uploads == []
