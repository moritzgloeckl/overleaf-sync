"""Characterization tests for olsync.olignore_keep_list (local file selection)."""

import pytest

from olsync import olsync


@pytest.fixture
def project(tmp_path, monkeypatch):
    for path in [
        "main.tex",
        "chapters/intro.tex",
        "chapters/deep/a.tex",
        "out/main.pdf",
        ".hidden",
        ".git/config",
        "figs/plot.png",
    ]:
        file = tmp_path / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text("x")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_without_olignore_keeps_all_visible_files(project):
    assert sorted(olsync.olignore_keep_list(".olignore")) == [
        "chapters/deep/a.tex",
        "chapters/intro.tex",
        "figs/plot.png",
        "main.tex",
        "out/main.pdf",
    ]


def test_dotfiles_and_hidden_dirs_are_skipped(project):
    keep = olsync.olignore_keep_list(".olignore")
    assert ".hidden" not in keep
    assert not any(f.startswith(".git") for f in keep)


def test_folder_pattern_needs_trailing_star(project):
    (project / ".olignore").write_text("out/*\nfigs/\n")
    keep = olsync.olignore_keep_list(".olignore")
    assert "out/main.pdf" not in keep
    # `figs/` alone does not match files inside the folder (fnmatch semantics)
    assert "figs/plot.png" in keep


def test_glob_patterns_match_across_folders(project):
    (project / ".olignore").write_text("*.png\nchapters/deep/*\n")
    keep = olsync.olignore_keep_list(".olignore")
    assert "figs/plot.png" not in keep
    assert "chapters/deep/a.tex" not in keep
    assert "chapters/intro.tex" in keep


def test_paths_use_forward_slashes(project):
    assert all("\\" not in f for f in olsync.olignore_keep_list(".olignore"))


def test_dot_slash_prefix_in_olignore_is_normalised(project):
    # #72: './main.tex' and 'main.tex' must mean the same file
    (project / ".olignore").write_text("./main.tex\n./chapters/deep/*\n")
    keep = olsync.olignore_keep_list(".olignore")
    assert "main.tex" not in keep
    assert "chapters/deep/a.tex" not in keep
    assert "chapters/intro.tex" in keep


def test_negated_pattern_keeps_a_file_an_earlier_pattern_ignores(project):
    # #72: sync a single file without listing every other file
    (project / ".olignore").write_text("*\n!main.tex\n")
    assert olsync.olignore_keep_list(".olignore") == ["main.tex"]


def test_last_matching_pattern_wins(project):
    (project / ".olignore").write_text("chapters/*\n!chapters/*.tex\nchapters/deep/*\n")
    keep = olsync.olignore_keep_list(".olignore")
    assert "chapters/intro.tex" in keep
    assert "chapters/deep/a.tex" not in keep


def test_negation_before_the_ignoring_pattern_has_no_effect(project):
    (project / ".olignore").write_text("!main.tex\n*.tex\n")
    assert "main.tex" not in olsync.olignore_keep_list(".olignore")


def test_negated_pattern_accepts_dot_slash_prefix(project):
    (project / ".olignore").write_text("*\n!./chapters/intro.tex\n")
    assert olsync.olignore_keep_list(".olignore") == ["chapters/intro.tex"]


def test_escaped_exclamation_mark_matches_a_literal_file_name(project):
    (project / "!draft.tex").write_text("x")
    (project / ".olignore").write_text("\\!draft.tex\n")
    keep = olsync.olignore_keep_list(".olignore")
    assert "!draft.tex" not in keep
    assert "main.tex" in keep
