"""Readable conflict diffs must remain bounded and safe for terminal output."""

import click
from click.testing import CliRunner

from olsync import olsync as cli


def preview(local, remote, color=False):
    @click.command()
    def command():
        cli.show_conflict_preview("main.tex", local, remote)

    result = CliRunner().invoke(command, color=color, catch_exceptions=False)
    assert result.exit_code == 0
    return result.output


def test_diff_colors_removed_lines_red_and_added_lines_green():
    output = preview(b"local edit\n", b"remote edit\n", color=True)
    assert "\x1b[31m-local edit" in output
    assert "\x1b[32m+remote edit" in output


def test_large_preview_is_truncated_explicitly():
    local = "".join(f"local {i}\n" for i in range(300)).encode()
    remote = "".join(f"remote {i}\n" for i in range(300)).encode()
    output = preview(local, remote)
    assert "Preview truncated" in output
    assert "+remote 299" not in output


def test_terminal_control_sequences_are_escaped():
    output = preview(b"local\n", b"remote\x1b[2J\n")
    assert "\\x1b[2J" in output
    assert "\x1b[2J" not in output


def test_diff_marks_a_missing_final_newline():
    output = preview(b"local", b"remote\n")
    assert "\\ No newline at end of file" in output


def test_utf8_text_is_readable():
    output = preview("café\n".encode(), "café corrigé\n".encode())
    assert "-café" in output
    assert "+café corrigé" in output
