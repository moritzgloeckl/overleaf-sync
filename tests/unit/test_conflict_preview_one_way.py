"""One-way sync previews conflicts only when requested."""

import pytest

from test_one_way_sync import FakeOverleaf, ols, project  # noqa: F401


@pytest.mark.parametrize("args", [["-l"], ["-r"]])
@pytest.mark.parametrize("answer", ["n\n", "\n", "d\nd\nn\n"])
def test_one_way_overwrite_previews_only_on_request(project, args, answer):  # noqa: F811
    FakeOverleaf.files = {"main.tex": b"remote edit\n"}
    (project / "main.tex").write_bytes(b"local edit\n")
    output = ols(*args, input=answer)
    assert output.count("Conflict preview for") == answer.count("d")
    if "d" in answer:
        assert "--- local/main.tex" in output and "+++ remote/main.tex" in output
        assert output.index("Overwrite it") < output.index("+remote edit") < output.rindex("Overwrite it")
    assert FakeOverleaf.files["main.tex"] == b"remote edit\n"
    assert (project / "main.tex").read_bytes() == b"local edit\n"


@pytest.mark.parametrize("args", [["-l"], ["-r"]])
def test_one_way_diff_then_yes_preserves_original_bytes(project, args):  # noqa: F811
    FakeOverleaf.files = {"main.tex": b"remote edit\n"}
    (project / "main.tex").write_bytes(b"local edit\r\n")
    output = ols(*args, input="d\nyes\n")
    expected = b"local edit\r\n" if args == ["-l"] else b"remote edit\n"
    assert "Conflict preview for" in output
    assert FakeOverleaf.files["main.tex"] == expected
    assert (project / "main.tex").read_bytes() == expected
