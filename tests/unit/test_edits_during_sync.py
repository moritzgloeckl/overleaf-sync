"""Edits made while a sync is running must stay pending for the next run."""

import pytest

from olsync import olsync as cli
from test_one_way_sync import FakeOverleaf, ols, project  # noqa: F401


@pytest.mark.parametrize("mode", ["two-way", "local-only", "restore"])
def test_edit_during_upload_is_synced_on_the_next_run(project, monkeypatch, mode):  # noqa: F811
    if mode == "restore":
        FakeOverleaf.files = {}
        (project / "main.tex").write_bytes(b"v2")
        args, answer = ["-r"], "r\n"
    else:
        FakeOverleaf.files = {"main.tex": b"v1"}
        ols()
        (project / "main.tex").write_bytes(b"v2")
        args, answer = (["-l"] if mode == "local-only" else []), None
    real_upload = FakeOverleaf.upload_file

    def upload_then_edit(self, *args):
        result = real_upload(self, *args)
        (project / "main.tex").write_bytes(b"v3 saved during sync")
        return result

    with monkeypatch.context() as patch:
        patch.setattr(FakeOverleaf, "upload_file", upload_then_edit)
        ols(*args, input=answer)
    assert FakeOverleaf.files["main.tex"] == b"v2"
    output = ols(input="s\n")
    assert "Conflict" not in output
    assert FakeOverleaf.files["main.tex"] == b"v3 saved during sync"


@pytest.mark.parametrize("args", [[], ["-r"]])
def test_edit_after_download_is_synced_on_the_next_run(project, monkeypatch, args):  # noqa: F811
    FakeOverleaf.files = {"main.tex": b"v1"}
    ols()
    FakeOverleaf.files["main.tex"] = b"v2 remote"
    real_write = cli.write_file

    def write_then_edit(name, content):
        real_write(name, content)
        (project / name).write_bytes(b"v3 saved during sync")

    with monkeypatch.context() as patch:
        patch.setattr(cli, "write_file", write_then_edit)
        ols(*args)
    output = ols(input="s\n")
    assert "Conflict" not in output
    assert FakeOverleaf.files["main.tex"] == b"v3 saved during sync"


@pytest.mark.parametrize("edited_side", ["local", "remote"])
def test_edit_to_an_unrelated_file_during_upload_remains_pending(project, monkeypatch, edited_side):  # noqa: F811
    FakeOverleaf.files = {"main.tex": b"v1"}
    ols()
    (project / "note.txt").write_bytes(b"new file")
    real_upload = FakeOverleaf.upload_file

    def upload_then_edit(self, *args):
        result = real_upload(self, *args)
        if edited_side == "local":
            (project / "main.tex").write_bytes(b"v2 edited during sync")
        else:
            FakeOverleaf.files["main.tex"] = b"v2 edited during sync"
        return result

    with monkeypatch.context() as patch:
        patch.setattr(FakeOverleaf, "upload_file", upload_then_edit)
        ols()
    output = ols(input="s\n")
    assert "Conflict" not in output
    assert FakeOverleaf.files["main.tex"] == b"v2 edited during sync"
    assert (project / "main.tex").read_bytes() == b"v2 edited during sync"


def test_edit_mid_transfer_does_not_change_the_uploaded_snapshot(project, monkeypatch):  # noqa: F811
    original = b"a" * 131072
    edited = b"b" * 131072
    (project / "main.tex").write_bytes(original)

    def edit_mid_upload(self, project_id, infos, name, size, file):
        first_chunk = file.read(16384)
        (project / name).write_bytes(edited)
        FakeOverleaf.files[name] = first_chunk + file.read()
        assert size == len(FakeOverleaf.files[name])
        return True

    with monkeypatch.context() as patch:
        patch.setattr(FakeOverleaf, "upload_file", edit_mid_upload)
        ols()
    assert FakeOverleaf.files["main.tex"] == original
    output = ols(input="s\n")
    assert "Conflict" not in output
    assert FakeOverleaf.files["main.tex"] == edited
