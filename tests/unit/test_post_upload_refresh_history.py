"""A failed refresh after an upload must not leave stale contents in the sync history."""

import pytest

from test_one_way_sync import FakeOverleaf, ols, project  # noqa: F401


@pytest.mark.parametrize("restore", [False, True])
def test_failed_post_upload_refresh_does_not_create_false_conflict(project, monkeypatch, restore):  # noqa: F811
    if restore:
        FakeOverleaf.files = {}
        (project / "main.tex").write_bytes(b"v2")
        args, answer = ["-r"], "r\n"
    else:
        FakeOverleaf.files = {"main.tex": b"v1"}
        ols()
        (project / "main.tex").write_bytes(b"v2")
        args, answer = ["-l"], None
    real_download = FakeOverleaf.download_project
    calls = 0

    def fail_refresh(self, project_id):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("temporary refresh failure")
        return real_download(self, project_id)

    with monkeypatch.context() as patch:
        patch.setattr(FakeOverleaf, "download_project", fail_refresh)
        output = ols(*args, input=answer)
    assert "Warning" in output and "refresh" in output
    assert FakeOverleaf.files["main.tex"] == b"v2"
    (project / "main.tex").write_bytes(b"v3")
    output = ols(input="s\n")
    assert "Conflict" not in output
    assert FakeOverleaf.files["main.tex"] == b"v3"
