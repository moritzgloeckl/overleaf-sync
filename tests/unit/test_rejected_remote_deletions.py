"""One-way sync must not report success when Overleaf rejects a deletion."""

from click.testing import CliRunner

from olsync import olsync as cli
from test_one_way_sync import FakeOverleaf, ols, project  # noqa: F401


def test_rejected_remote_deletion_fails_without_reporting_success(project, monkeypatch):  # noqa: F811
    FakeOverleaf.files = {"main.tex": b"v1"}
    ols()
    (project / "main.tex").unlink()
    monkeypatch.setattr(FakeOverleaf, "delete_file", lambda self, *args: False)
    result = CliRunner().invoke(cli.main, ["-l"], input="d\n", catch_exceptions=False)
    assert result.exit_code != 0
    assert "deleting" in result.output
    assert "Synced files from [local] to [remote]" not in result.output
    assert FakeOverleaf.files["main.tex"] == b"v1"
