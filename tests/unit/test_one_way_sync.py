"""-r and -l only overwrite a file without asking if the target side did not change it since the last sync."""

import io
import os
import time
import zipfile

import pytest
from click.testing import CliRunner

from olsync import auth as olauth
from olsync import olsync as cli


class FakeOverleaf:
    """In-memory Overleaf project that keeps its files across several `ols` runs."""

    files = {}
    uploads = []

    def __init__(self, cookie=None, csrf=None, base_url="https://www.overleaf.com"):
        self.base_url = base_url

    def get_project(self, name):
        # lastUpdated always "newer" than local files, the case where -r used to overwrite local edits silently
        return {"id": "p1", "name": name, "lastUpdated": "2030-01-01T00:00:00.000Z"}

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

    def delete_file(self, project_id, project_infos, name):
        FakeOverleaf.files.pop(name, None)
        return True


@pytest.fixture
def project(tmp_path, monkeypatch):
    project_dir = tmp_path / "Thesis"
    project_dir.mkdir()
    olauth.save_auth(project_dir / ".olauth", {"overleaf_session2": "s"}, "c", "https://www.overleaf.com")
    monkeypatch.chdir(project_dir)
    monkeypatch.setattr(cli, "OverleafClient", FakeOverleaf)
    FakeOverleaf.files = {}
    FakeOverleaf.uploads = []
    return project_dir


def ols(*args, input=None):
    result = CliRunner().invoke(cli.main, list(args), input=input, catch_exceptions=False)
    assert result.exit_code == 0, result.output
    return result.output


def edit_locally(path, content):
    path.write_bytes(content)
    old = time.time() - 3600  # older than the project's lastUpdated
    os.utime(path, (old, old))


# --- -r: remote -> local ----------------------------------------------------------------------------------------


def test_remote_only_overwrites_files_changed_only_on_overleaf(project):
    FakeOverleaf.files = {"main.tex": b"v1"}
    ols()
    FakeOverleaf.files["main.tex"] = b"v2 from Overleaf"
    output = ols("-r")
    assert (project / "main.tex").read_bytes() == b"v2 from Overleaf"
    assert "Warning" not in output


def test_remote_only_asks_before_overwriting_a_local_edit(project):
    FakeOverleaf.files = {"main.tex": b"v1"}
    ols()
    edit_locally(project / "main.tex", b"local edit")
    FakeOverleaf.files["main.tex"] = b"remote edit"
    output = ols("-r", input="n\n")
    assert "main.tex" in output and "changed" in output
    assert (project / "main.tex").read_bytes() == b"local edit"


def test_remote_only_overwrites_a_local_edit_when_confirmed(project):
    FakeOverleaf.files = {"main.tex": b"v1"}
    ols()
    edit_locally(project / "main.tex", b"local edit")
    ols("-r", input="y\n")
    assert (project / "main.tex").read_bytes() == b"v1"


def test_remote_only_asks_without_sync_history(project):
    FakeOverleaf.files = {"main.tex": b"remote"}
    edit_locally(project / "main.tex", b"local")
    ols("-r", input="n\n")
    assert (project / "main.tex").read_bytes() == b"local"


# --- -l: local -> remote ----------------------------------------------------------------------------------------


def test_local_only_uploads_files_changed_only_locally(project):
    FakeOverleaf.files = {"main.tex": b"v1"}
    ols()
    edit_locally(project / "main.tex", b"v2 local")
    output = ols("-l")
    assert FakeOverleaf.files["main.tex"] == b"v2 local"
    assert "Warning" not in output


def test_local_only_asks_before_overwriting_an_edit_on_overleaf(project):
    FakeOverleaf.files = {"main.tex": b"v1"}
    ols()
    (project / "main.tex").write_bytes(b"local edit")  # local file is *newer*, -l used to upload without asking
    FakeOverleaf.files["main.tex"] = b"remote edit"
    output = ols("-l", input="n\n")
    assert "main.tex" in output and "changed" in output
    assert FakeOverleaf.files["main.tex"] == b"remote edit"


def test_local_only_asks_without_sync_history(project):
    FakeOverleaf.files = {"main.tex": b"remote"}
    (project / "main.tex").write_bytes(b"local")
    ols("-l", input="n\n")
    assert FakeOverleaf.files["main.tex"] == b"remote"


# --- state ------------------------------------------------------------------------------------------------------


def test_one_way_syncs_record_the_state_for_later_syncs(project):
    FakeOverleaf.files = {"main.tex": b"v1"}
    ols("-r")
    # after -r the files are known to be in sync, so a later local edit is uploaded by a two-way sync without asking
    edit_locally(project / "main.tex", b"v2 local")
    output = ols()
    assert FakeOverleaf.files["main.tex"] == b"v2 local"
    assert "Conflict" not in output


def test_skipped_file_stays_unsynced(project):
    FakeOverleaf.files = {"main.tex": b"v1"}
    ols()
    edit_locally(project / "main.tex", b"local edit")
    FakeOverleaf.files["main.tex"] = b"remote edit"
    ols("-r", input="n\n")
    output = ols("-r", input="n\n")
    assert "main.tex" in output and "changed" in output
