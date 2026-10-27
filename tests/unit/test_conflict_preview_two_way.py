"""Two-way sync shows a diff, or explains why it cannot, before asking how to resolve a conflict."""

import pytest

from test_two_way_sync import FakeOverleaf, project, sync  # noqa: F401


def test_text_conflict_shows_a_diff_before_the_choice(project):  # noqa: F811
    FakeOverleaf.files = {"main.tex": b"heading\nremote edit\n"}
    (project / "main.tex").write_bytes(b"heading\nlocal edit\n")
    output, _ = sync(input="s\n")
    assert "--- local/main.tex" in output
    assert "+++ remote/main.tex" in output
    assert "-local edit" in output and "+remote edit" in output
    assert output.index("+remote edit") < output.index("Keep the [l]ocal version")
    assert (project / "main.tex").read_bytes() == b"heading\nlocal edit\n"
    assert FakeOverleaf.files["main.tex"] == b"heading\nremote edit\n"


@pytest.mark.parametrize("remote", [b"\x00PNG remote", b"\xff\xfe remote"])
def test_binary_conflict_explains_why_no_text_preview_is_available(project, remote):  # noqa: F811
    FakeOverleaf.files = {"image.png": remote}
    (project / "image.png").write_bytes(b"local image")
    output, _ = sync(input="s\n")
    assert "Binary or non-UTF-8" in output
    assert "Keep the [l]ocal version" in output
    assert FakeOverleaf.files["image.png"] == remote
