"""Explicit project IDs bypass name lookup, including for shared duplicate names."""

import json

import pytest

from test_cli import FakeClient, run, workdir  # noqa: F401


def forbid_name_lookup(*args):
    raise AssertionError("Project ID selection must not query the project dashboard")


@pytest.mark.parametrize("mode", [[], ["-l"], ["-r"]])
@pytest.mark.parametrize("name_args", [[], ["--name", "Duplicate name"]])
def test_sync_by_id_bypasses_names_and_targets_requested_project(workdir, monkeypatch, mode, name_args):  # noqa: F811
    monkeypatch.setattr(FakeClient, "get_project", forbid_name_lookup)
    monkeypatch.setattr(FakeClient, "all_projects", forbid_name_lookup)
    requested = []
    original_infos = FakeClient.get_project_infos
    original_zip = FakeClient.download_project
    original_upload = FakeClient.upload_file

    def infos(self, project_id):
        requested.append(project_id)
        return original_infos(self, project_id)

    def archive(self, project_id):
        requested.append(project_id)
        return original_zip(self, project_id)

    def upload(self, project_id, *args):
        requested.append(project_id)
        return original_upload(self, project_id, *args)

    monkeypatch.setattr(FakeClient, "get_project_infos", infos)
    monkeypatch.setattr(FakeClient, "download_project", archive)
    monkeypatch.setattr(FakeClient, "upload_file", upload)
    FakeClient.remote = {"main.tex": b"remote"}
    if mode == ["-l"]:
        FakeClient.remote = {}
        (workdir / "main.tex").write_bytes(b"local")
    result = run(*mode, *name_args, "--project-id", "shared-project")
    assert result.exit_code == 0, result.output
    assert len(requested) >= 2 and set(requested) == {"shared-project"}
    expected = b"local" if mode == ["-l"] else b"remote"
    assert (workdir / "main.tex").read_bytes() == expected
    if mode == ["-l"]:
        assert FakeClient.instances[0].uploaded == [("main.tex", b"local")]
    state = json.loads((workdir / ".olsync-state.json").read_text())
    assert state["project_id"] == "shared-project"


def test_unavailable_id_fails_without_falling_back_to_a_name(workdir, monkeypatch):  # noqa: F811
    monkeypatch.setattr(FakeClient, "get_project", forbid_name_lookup)
    monkeypatch.setattr(FakeClient, "get_project_infos", lambda self, project_id: None)
    result = run("--project-id", "unavailable")
    assert result.exit_code != 0
    assert "Project details could not be queried" in result.output
    assert not (workdir / ".olsync-state.json").exists()


@pytest.mark.parametrize(
    "args",
    [
        ["download", "--project-id", "shared-project"],
        ["download", "--name", "Duplicate name", "--project-id", "shared-project"],
        ["--project-id", "shared-project", "download"],
        ["--project-id", "other-project", "download", "--project-id", "shared-project"],
    ],
)
def test_pdf_by_id_bypasses_names(workdir, monkeypatch, tmp_path, args):  # noqa: F811
    monkeypatch.setattr(FakeClient, "get_project", forbid_name_lookup)
    monkeypatch.setattr(FakeClient, "all_projects", forbid_name_lookup)
    requested = []

    def pdf(self, project_id):
        requested.append(project_id)
        return "output.pdf", b"%PDF-1.5"

    monkeypatch.setattr(FakeClient, "download_pdf", pdf)
    result = run(*args, "--download-path", str(tmp_path))
    assert result.exit_code == 0, result.output
    assert requested == ["shared-project"]
    assert (tmp_path / "output.pdf").read_bytes() == b"%PDF-1.5"


def test_list_shows_ids_for_duplicate_names_in_date_order(workdir, monkeypatch):  # noqa: F811
    original = FakeClient.all_projects

    def duplicates(self):
        return [dict(project, name="Thesis") for project in original(self)]

    monkeypatch.setattr(FakeClient, "all_projects", duplicates)
    result = run("list")
    assert result.exit_code == 0, result.output
    assert "Thesis [p1]" in result.output and "Thesis [p2]" in result.output
    assert result.output.index("[p2]") < result.output.index("[p1]")
