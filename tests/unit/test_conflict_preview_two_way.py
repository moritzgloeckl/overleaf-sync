"""Two-way sync previews conflicts only when requested, then asks again."""

import pytest

from test_two_way_sync import FakeOverleaf, project, sync  # noqa: F401


def test_text_conflict_shows_a_diff_on_request_and_repeats_the_choice(project):  # noqa: F811
    FakeOverleaf.files = {"main.tex": b"heading\nremote edit\n"}
    (project / "main.tex").write_bytes(b"heading\nlocal edit\n")
    output, _ = sync(input="d\nd\ns\n")
    assert "--- local/main.tex" in output
    assert "+++ remote/main.tex" in output
    assert "-local edit" in output and "+remote edit" in output
    assert output.count("Conflict preview for") == 2
    assert output.index("Keep the [l]ocal version") < output.index("+remote edit")
    assert output.index("+remote edit") < output.rindex("Keep the [l]ocal version")
    assert (project / "main.tex").read_bytes() == b"heading\nlocal edit\n"
    assert FakeOverleaf.files["main.tex"] == b"heading\nremote edit\n"


@pytest.mark.parametrize("remote", [b"\x00PNG remote", b"\xff\xfe remote"])
def test_binary_conflict_explains_why_no_text_preview_is_available(project, remote):  # noqa: F811
    FakeOverleaf.files = {"image.png": remote}
    (project / "image.png").write_bytes(b"local image")
    output, _ = sync(input="d\ns\n")
    assert "Binary or non-UTF-8" in output
    assert "Keep the [l]ocal version" in output
    assert FakeOverleaf.files["image.png"] == remote


@pytest.mark.parametrize("answer", ["s\n", "\n"])
def test_conflict_has_no_preview_by_default(project, answer):  # noqa: F811
    FakeOverleaf.files = {"main.tex": b"remote\n"}
    (project / "main.tex").write_bytes(b"local\n")
    output, _ = sync(input=answer)
    assert "Conflict preview for" not in output


@pytest.mark.parametrize("choice", ["l", "r"])
def test_diff_then_resolve_preserves_original_line_endings(project, choice):  # noqa: F811
    FakeOverleaf.files = {"main.tex": b"same\n"}
    (project / "main.tex").write_bytes(b"same\r\n")
    output, _ = sync(input=f"d\n{choice}\n")
    expected = b"same\r\n" if choice == "l" else b"same\n"
    assert "Only the line endings differ" in output
    assert FakeOverleaf.files["main.tex"] == expected
    assert (project / "main.tex").read_bytes() == expected
