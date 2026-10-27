"""One-way sync shows a diff before asking to overwrite a file the other side changed."""

import pytest

from test_one_way_sync import FakeOverleaf, ols, project  # noqa: F401


@pytest.mark.parametrize("args", [["-l"], ["-r"]])
def test_one_way_overwrite_shows_a_conflict_preview(project, args):  # noqa: F811
    FakeOverleaf.files = {"main.tex": b"remote edit\n"}
    (project / "main.tex").write_bytes(b"local edit\n")
    output = ols(*args, input="n\n")
    assert "--- local/main.tex" in output and "+++ remote/main.tex" in output
    assert output.index("+remote edit") < output.index("Overwrite it")
    assert FakeOverleaf.files["main.tex"] == b"remote edit\n"
    assert (project / "main.tex").read_bytes() == b"local edit\n"
