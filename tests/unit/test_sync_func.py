"""Characterization tests for olsync.sync_func, the generic one-direction sync routine."""
import click
import pytest

from olsync import olsync


class FakeSide:
    """In-memory stand-in for one side (local or remote) of a sync."""

    def __init__(self, files=None):
        self.files = dict(files or {})


class Prompts:
    """Scripted answers for click.confirm / click.prompt, recording every question asked."""

    def __init__(self, monkeypatch, confirms=(), choices=()):
        self.confirms = list(confirms)
        self.choices = list(choices)
        self.asked = []
        monkeypatch.setattr(click, "confirm", self._confirm)
        monkeypatch.setattr(click, "prompt", self._prompt)

    def _confirm(self, text, *args, **kwargs):
        self.asked.append(text)
        return self.confirms.pop(0)

    def _prompt(self, text, *args, **kwargs):
        self.asked.append(text)
        return self.choices.pop(0)


def run_sync(src, dst, newer=(), deleted=()):
    """Sync src -> dst. `newer` lists the names where src counts as newer than dst."""
    olsync.sync_func(
        files_from=list(src.files),
        deleted_files=list(deleted),
        create_file_at_to=lambda name: dst.files.__setitem__(name, src.files[name]),
        delete_file_at_to=lambda name: dst.files.pop(name),
        create_file_at_from=lambda name: src.files.__setitem__(name, dst.files[name]),
        from_exists_in_to=lambda name: name in dst.files,
        from_equal_to_to=lambda name: src.files[name] == dst.files[name],
        from_newer_than_to=lambda name: name in newer,
        from_name="remote",
        to_name="local",
    )


def test_new_file_is_created_on_target(monkeypatch):
    prompts = Prompts(monkeypatch)
    src, dst = FakeSide({"main.tex": b"a"}), FakeSide()
    run_sync(src, dst)
    assert dst.files == {"main.tex": b"a"}
    assert prompts.asked == []


def test_unchanged_file_is_left_alone(monkeypatch):
    prompts = Prompts(monkeypatch)
    src, dst = FakeSide({"main.tex": b"a"}), FakeSide({"main.tex": b"a"})
    run_sync(src, dst)
    assert dst.files == {"main.tex": b"a"}
    assert prompts.asked == []


def test_differing_older_file_asks_and_overwrites_on_yes(monkeypatch):
    prompts = Prompts(monkeypatch, confirms=[True])
    src, dst = FakeSide({"main.tex": b"old"}), FakeSide({"main.tex": b"new"})
    run_sync(src, dst)
    assert dst.files == {"main.tex": b"old"}
    assert len(prompts.asked) == 1


def test_differing_older_file_asks_and_keeps_target_on_no(monkeypatch):
    Prompts(monkeypatch, confirms=[False])
    src, dst = FakeSide({"main.tex": b"old"}), FakeSide({"main.tex": b"new"})
    run_sync(src, dst)
    assert dst.files == {"main.tex": b"new"}


def test_differing_newer_file_is_overwritten(monkeypatch):
    Prompts(monkeypatch)
    src, dst = FakeSide({"main.tex": b"new"}), FakeSide({"main.tex": b"old"})
    run_sync(src, dst, newer={"main.tex"})
    assert dst.files == {"main.tex": b"new"}


@pytest.mark.xfail(reason="Silent overwrite: 'newer' is decided by the project-wide lastUpdated timestamp, so a "
                          "file changed on both sides is overwritten without asking (data loss)")
def test_differing_newer_file_is_not_overwritten_without_asking(monkeypatch):
    prompts = Prompts(monkeypatch, confirms=[False])
    src, dst = FakeSide({"main.tex": b"remote edit"}), FakeSide({"main.tex": b"local edit"})
    run_sync(src, dst, newer={"main.tex"})
    assert dst.files == {"main.tex": b"local edit"}
    assert len(prompts.asked) == 1


@pytest.mark.parametrize("choice, expected_src, expected_dst", [
    ("d", {}, {}),
    ("r", {"gone.tex": b"x"}, {"gone.tex": b"x"}),
    ("i", {}, {"gone.tex": b"x"}),
])
def test_deleted_file_choices(monkeypatch, choice, expected_src, expected_dst):
    Prompts(monkeypatch, choices=[choice])
    src, dst = FakeSide(), FakeSide({"gone.tex": b"x"})
    run_sync(src, dst, deleted=["gone.tex"])
    assert src.files == expected_src
    assert dst.files == expected_dst


def test_failure_while_creating_raises_click_exception(monkeypatch):
    Prompts(monkeypatch)

    def boom(name):
        raise OSError("disk full")

    with pytest.raises(click.ClickException):
        olsync.sync_func(
            files_from=["main.tex"], deleted_files=[],
            create_file_at_to=boom, delete_file_at_to=None, create_file_at_from=None,
            from_exists_in_to=lambda name: False, from_equal_to_to=None, from_newer_than_to=None,
            from_name="remote", to_name="local")
