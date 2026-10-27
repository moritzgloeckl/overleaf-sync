"""Per-file sync state for two-way sync: decide per file instead of by the project-wide timestamp."""

import json

import pytest

from olsync import syncstate

H = {"a": "hash-a", "b": "hash-b", "c": "hash-c"}


def plan(local, remote, state):
    return syncstate.plan_two_way(local, remote, state)


@pytest.mark.parametrize(
    "local, remote, state, expected",
    [
        # unchanged on both sides
        ({"f": "a"}, {"f": "a"}, {"f": {"local": "a", "remote": "a"}}, "in_sync"),
        # same content without history (e.g. first run)
        ({"f": "a"}, {"f": "a"}, {}, "in_sync"),
        # changed locally only -> upload
        ({"f": "b"}, {"f": "a"}, {"f": {"local": "a", "remote": "a"}}, "upload"),
        # changed on Overleaf only -> download
        ({"f": "a"}, {"f": "b"}, {"f": {"local": "a", "remote": "a"}}, "download"),
        # changed on both sides to different content -> conflict
        ({"f": "b"}, {"f": "c"}, {"f": {"local": "a", "remote": "a"}}, "conflict"),
        # changed on both sides to the same content -> nothing to do
        ({"f": "b"}, {"f": "b"}, {"f": {"local": "a", "remote": "a"}}, "in_sync"),
        # differs, no history -> conflict (never guess on the first run)
        ({"f": "a"}, {"f": "b"}, {}, "conflict"),
        # differs, but neither side changed since the last sync (e.g. Overleaf normalised line endings)
        ({"f": "a"}, {"f": "n"}, {"f": {"local": "a", "remote": "n"}}, "in_sync"),
        # only local -> upload, only remote -> download (as before 2.0)
        ({"f": "a"}, {}, {}, "upload"),
        ({}, {"f": "a"}, {}, "download"),
    ],
)
def test_plan_two_way(local, remote, state, expected):
    result = plan(local, remote, state)
    assert {action for action, paths in result.items() if "f" in paths} == {expected}


def test_plan_covers_every_file_exactly_once():
    result = plan({"l": "a", "both": "a", "x": "b"}, {"r": "a", "both": "a", "x": "c"}, {})
    assert sorted(p for paths in result.values() for p in paths) == ["both", "l", "r", "x"]


def test_file_hash_is_stable_and_content_based():
    assert syncstate.file_hash(b"x") == syncstate.file_hash(b"x")
    assert syncstate.file_hash(b"x") != syncstate.file_hash(b"y")


def test_state_round_trip(tmp_path):
    files = {"main.tex": {"local": "a", "remote": "b"}}
    syncstate.save_state(tmp_path, "https://www.overleaf.com", "p1", files)
    assert syncstate.load_state(tmp_path, "https://www.overleaf.com", "p1") == files
    assert json.loads((tmp_path / ".olsync-state.json").read_text())["project_id"] == "p1"


@pytest.mark.parametrize("server, project_id", [("https://www.overleaf.com", "other"), ("http://ce.test", "p1")])
def test_state_of_another_project_or_server_is_ignored(tmp_path, server, project_id):
    syncstate.save_state(tmp_path, "https://www.overleaf.com", "p1", {"f": {"local": "a", "remote": "a"}})
    assert syncstate.load_state(tmp_path, server, project_id) == {}


def test_missing_or_corrupt_state_is_empty(tmp_path):
    assert syncstate.load_state(tmp_path, "s", "p") == {}
    (tmp_path / ".olsync-state.json").write_text("{not json")
    assert syncstate.load_state(tmp_path, "s", "p") == {}


def test_save_state_leaves_no_temporary_files(tmp_path):
    syncstate.save_state(tmp_path, "s", "p", {})
    assert [p.name for p in tmp_path.iterdir()] == [".olsync-state.json"]


@pytest.mark.parametrize(
    "files",
    [
        None,
        [],
        "invalid",
        42,
        {"main.tex": []},
        {"main.tex": {"local": 1, "remote": "b"}},
        {"main.tex": {"local": "a"}},
        {"main.tex": {"local": "", "remote": "b"}},
    ],
)
def test_malformed_history_warns_and_requires_conflict_confirmation(tmp_path, capsys, files):
    path = tmp_path / syncstate.STATE_FILE
    path.write_text(json.dumps({"version": syncstate.STATE_VERSION, "server": "s", "project_id": "p", "files": files}))
    state = syncstate.load_state(tmp_path, "s", "p")
    assert "ignoring invalid sync history" in capsys.readouterr().err
    assert state == {}
    assert syncstate.plan_two_way({"main.tex": "local"}, {"main.tex": "remote"}, state)["conflict"] == ["main.tex"]
