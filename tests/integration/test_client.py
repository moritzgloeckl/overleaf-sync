"""OverleafClient against a real Overleaf Community Edition server."""
import io
import zipfile

import pytest

pytestmark = pytest.mark.integration

PNG = bytes.fromhex("89504e470d0a1a0a0000000d4948445200000001000000010806000000"
                    "1f15c4890000000d4944415478da63f8cfc0f00f0003860180" "5a347d6b0000000049454e44ae426082")


def upload(client, project, infos, path, content):
    return client.upload_file(project["id"], infos, path, len(content), io.BytesIO(content))


def test_project_list_contains_the_project(ce_client, ce_project):
    assert ce_project["id"] in [p["id"] for p in ce_client.all_projects()]
    assert ce_client.get_project(ce_project["name"])["id"] == ce_project["id"]


def test_project_infos_come_from_the_real_time_service(ce_client, ce_project):
    root = ce_client.get_project_infos(ce_project["id"])["rootFolder"][0]
    assert "main.tex" in [doc["name"] for doc in root["docs"]]


def test_zip_download_contains_main_tex(ce_client, ce_project):
    zf = zipfile.ZipFile(io.BytesIO(ce_client.download_project(ce_project["id"])))
    assert "main.tex" in zf.namelist()


def test_upload_text_file_to_root(ce_client, ce_project, ce_tree, ce_content):
    infos = ce_client.get_project_infos(ce_project["id"])
    assert upload(ce_client, ce_project, infos, "root.tex", b"% root\n") is True
    assert ce_content(ce_tree()["root.tex"]) == b"% root\n"


def test_upload_into_new_nested_folders(ce_client, ce_project, ce_tree, ce_content):
    infos = ce_client.get_project_infos(ce_project["id"])
    assert upload(ce_client, ce_project, infos, "chapters/part1/intro.tex", b"% intro\n") is True
    tree = ce_tree()
    assert tree["chapters/"][0] == "folder" and tree["chapters/part1/"][0] == "folder"
    assert ce_content(tree["chapters/part1/intro.tex"]) == b"% intro\n"


def test_upload_into_existing_folder_with_different_case(ce_client, ce_project, ce_tree):
    infos = ce_client.get_project_infos(ce_project["id"])
    upload(ce_client, ce_project, infos, "figs/a.tex", b"a")
    infos = ce_client.get_project_infos(ce_project["id"])
    assert upload(ce_client, ce_project, infos, "FIGS/b.tex", b"b") is True
    assert "figs/b.tex" in ce_tree()


def test_upload_binary_file(ce_client, ce_project, ce_tree, ce_content):
    infos = ce_client.get_project_infos(ce_project["id"])
    assert upload(ce_client, ce_project, infos, "images/pixel.png", PNG) is True
    entry = ce_tree()["images/pixel.png"]
    assert entry[0] == "file"
    assert ce_content(entry) == PNG


def test_upload_replaces_existing_file(ce_client, ce_project, ce_tree, ce_content):
    infos = ce_client.get_project_infos(ce_project["id"])
    upload(ce_client, ce_project, infos, "replace.tex", b"version 1\n")
    infos = ce_client.get_project_infos(ce_project["id"])
    assert upload(ce_client, ce_project, infos, "replace.tex", b"version 2\n") is True
    tree = ce_tree()
    assert [path for path in tree if path == "replace.tex"] == ["replace.tex"]
    assert ce_content(tree["replace.tex"]) == b"version 2\n"


def test_create_folder_that_already_exists(ce_client, ce_project):
    root_id = ce_client.get_project_infos(ce_project["id"])["rootFolder"][0]["_id"]
    assert ce_client.create_folder(ce_project["id"], root_id, "twice")["name"] == "twice"
    assert ce_client.create_folder(ce_project["id"], root_id, "twice") is None


def test_delete_text_file(ce_client, ce_project, ce_tree):
    infos = ce_client.get_project_infos(ce_project["id"])
    upload(ce_client, ce_project, infos, "gone/doc.tex", b"x")
    infos = ce_client.get_project_infos(ce_project["id"])
    assert ce_client.delete_file(ce_project["id"], infos, "gone/doc.tex") is True
    assert "gone/doc.tex" not in ce_tree()


def test_delete_binary_file(ce_client, ce_project, ce_tree):
    infos = ce_client.get_project_infos(ce_project["id"])
    upload(ce_client, ce_project, infos, "gone/pixel.png", PNG)
    infos = ce_client.get_project_infos(ce_project["id"])
    assert ce_client.delete_file(ce_project["id"], infos, "gone/pixel.png") is True
    assert "gone/pixel.png" not in ce_tree()


def test_compile_and_download_pdf(ce_client, ce_project):
    file_name, content = ce_client.download_pdf(ce_project["id"])
    assert file_name.endswith(".pdf")
    assert content.startswith(b"%PDF-")
