"""One-way sync must not report or record an upload that Overleaf rejected."""

from click.testing import CliRunner

from olsync import olsync as cli
from test_one_way_sync import FakeOverleaf, edit_locally, ols, project  # noqa: F401


def test_local_only_reports_a_rejected_upload_instead_of_success(project, monkeypatch):  # noqa: F811
    FakeOverleaf.files = {"main.tex": b"v1"}
    ols()
    edit_locally(project / "main.tex", b"v2 local")
    # upload_file signals a rejected upload (e.g. HTTP 422) by returning False
    monkeypatch.setattr(FakeOverleaf, "upload_file", lambda self, *args: False)
    result = CliRunner().invoke(cli.main, ["-l"], catch_exceptions=False)
    assert result.exit_code != 0
    assert "Synced files from [local] to [remote]" not in result.output
    assert FakeOverleaf.files["main.tex"] == b"v1"


def test_rejected_upload_is_not_recorded_as_synced(project, monkeypatch):  # noqa: F811
    FakeOverleaf.files = {"main.tex": b"v1"}
    ols()
    edit_locally(project / "main.tex", b"v2 local")
    real_upload = FakeOverleaf.upload_file
    monkeypatch.setattr(FakeOverleaf, "upload_file", lambda self, *args: False)
    CliRunner().invoke(cli.main, ["-l"], catch_exceptions=False)
    monkeypatch.setattr(FakeOverleaf, "upload_file", real_upload)
    # the local edit is still pending, so the next two-way sync uploads it without a conflict
    output = ols()
    assert FakeOverleaf.files["main.tex"] == b"v2 local"
    assert "Conflict" not in output
