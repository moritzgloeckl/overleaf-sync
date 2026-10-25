"""Read-only checks of every Overleaf endpoint the sync depends on."""

import io
import zipfile

import pytest

pytestmark = pytest.mark.smoke


def test_project_list_contains_smoke_project(smoke_project):
    assert smoke_project["lastUpdated"]


def test_get_project_by_name(smoke_client, smoke_project):
    assert smoke_client.get_project(smoke_project["name"])["id"] == smoke_project["id"]


def test_project_infos_have_a_root_folder(smoke_client, smoke_project):
    infos = smoke_client.get_project_infos(smoke_project["id"])
    assert infos is not None, "No joinProject response from the real-time service"
    assert infos["rootFolder"][0]["_id"]


def test_project_zip_download(smoke_client, smoke_project):
    names = zipfile.ZipFile(io.BytesIO(smoke_client.download_project(smoke_project["id"]))).namelist()
    assert "main.tex" in names


def test_compile_and_download_pdf(smoke_client, smoke_project):
    # The only compile per smoke run (Overleaf rate-limits compiles)
    file_name, content = smoke_client.download_pdf(smoke_project["id"])
    assert file_name.endswith(".pdf")
    assert content.startswith(b"%PDF-")
