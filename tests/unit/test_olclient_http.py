"""Request shape and return values of OverleafClient's HTTP calls (mocked with `responses`)."""
import json
from urllib.parse import parse_qs, urlparse

import pytest
import requests
import responses

from olsync.olclient import OverleafClient

BASE = "https://www.overleaf.com"


@pytest.fixture
def rsps():
    with responses.RequestsMock(assert_all_requests_are_fired=False) as mock:
        yield mock


@pytest.fixture
def client():
    return OverleafClient({"overleaf_session2": "s", "GCLB": "g"}, "csrf-token")


def project_infos(root_docs=(), root_files=(), folders=()):
    return {"rootFolder": [{"_id": "root", "name": "rootFolder", "docs": list(root_docs),
                            "fileRefs": list(root_files), "folders": list(folders)}]}


def folder(_id, name, docs=(), files=(), folders=()):
    return {"_id": _id, "name": name, "docs": list(docs), "fileRefs": list(files), "folders": list(folders)}


def upload_ok(rsps):
    rsps.add(responses.POST, f"{BASE}/project/p1/upload", json={"success": True}, status=200)


def query(call):
    return {k: v[0] for k, v in parse_qs(urlparse(call.request.url).query).items()}


# --- upload_file -----------------------------------------------------------------------------------------------

def test_upload_to_root_folder(rsps, client):
    upload_ok(rsps)
    client.upload_file("p1", project_infos(), "main.tex", 3, b"abc")
    params = query(rsps.calls[0])
    assert params["folder_id"] == "root"
    assert params["qqfilename"] == "main.tex"
    assert params["_csrf"] == "csrf-token"
    assert b'name="qqfile"' in rsps.calls[0].request.body


def test_upload_into_existing_folder_matches_case_insensitively(rsps, client):
    upload_ok(rsps)
    client.upload_file("p1", project_infos(folders=[folder("f1", "Figures")]), "figures/a.png", 3, b"abc")
    assert len(rsps.calls) == 1
    assert query(rsps.calls[0])["folder_id"] == "f1"


def test_upload_into_missing_folder_creates_it_first(rsps, client):
    rsps.add(responses.POST, f"{BASE}/project/p1/folder", json=folder("f9", "figures"), status=200)
    upload_ok(rsps)
    client.upload_file("p1", project_infos(), "figures/a.png", 3, b"abc")
    assert json.loads(rsps.calls[0].request.body) == {"parent_folder_id": "root", "name": "figures"}
    assert rsps.calls[0].request.headers["X-Csrf-Token"] == "csrf-token"
    assert query(rsps.calls[1])["folder_id"] == "f9"


@pytest.mark.xfail(reason="#49/#77: Overleaf now requires a multipart `name` field, and rejects '/' in it "
                          "(fixed by #85 plus basename fix-up)")
def test_upload_sends_basename_as_name_field(rsps, client):
    upload_ok(rsps)
    client.upload_file("p1", project_infos(folders=[folder("f1", "figures")]), "figures/a.png", 3, b"abc")
    assert b'name="name"\r\n\r\na.png\r\n' in rsps.calls[0].request.body


@pytest.mark.xfail(reason="status_code is compared to str(200), so success is never reported (fixed by #85)")
def test_upload_returns_true_on_success(rsps, client):
    upload_ok(rsps)
    assert client.upload_file("p1", project_infos(), "main.tex", 3, b"abc") is True


def test_upload_returns_false_on_failure(rsps, client):
    rsps.add(responses.POST, f"{BASE}/project/p1/upload", json={"success": False, "error": "invalid_filename"},
             status=422)
    assert not client.upload_file("p1", project_infos(), "main.tex", 3, b"abc")


# --- create_folder ---------------------------------------------------------------------------------------------

def test_create_folder_returns_new_folder(rsps, client):
    rsps.add(responses.POST, f"{BASE}/project/p1/folder", json=folder("f1", "figs"), status=200)
    assert client.create_folder("p1", "root", "figs")["_id"] == "f1"


@pytest.mark.xfail(reason="status_code is compared to str(400), so 'folder exists' raises (fixed by #85)")
def test_create_folder_returns_none_if_folder_exists(rsps, client):
    rsps.add(responses.POST, f"{BASE}/project/p1/folder", status=400)
    assert client.create_folder("p1", "root", "figs") is None


def test_create_folder_raises_on_server_error(rsps, client):
    rsps.add(responses.POST, f"{BASE}/project/p1/folder", status=500)
    with pytest.raises(requests.HTTPError):
        client.create_folder("p1", "root", "figs")


# --- delete_file -----------------------------------------------------------------------------------------------

def test_delete_doc_in_root(rsps, client):
    rsps.add(responses.DELETE, f"{BASE}/project/p1/doc/d1", status=204)
    client.delete_file("p1", project_infos(root_docs=[{"_id": "d1", "name": "main.tex"}]), "main.tex")
    assert rsps.calls[0].request.headers["X-Csrf-Token"] == "csrf-token"


def test_delete_doc_in_subfolder(rsps, client):
    rsps.add(responses.DELETE, f"{BASE}/project/p1/doc/d2", status=204)
    infos = project_infos(folders=[folder("f1", "chapters", docs=[{"_id": "d2", "name": "intro.tex"}])])
    client.delete_file("p1", infos, "chapters/intro.tex")
    assert len(rsps.calls) == 1


def test_delete_unknown_file_returns_false_without_request(rsps, client):
    assert client.delete_file("p1", project_infos(), "missing.tex") is False


@pytest.mark.xfail(reason="status_code is compared to str(204), so success is never reported (fixed by #85)")
def test_delete_returns_true_on_success(rsps, client):
    rsps.add(responses.DELETE, f"{BASE}/project/p1/doc/d1", status=204)
    assert client.delete_file("p1", project_infos(root_docs=[{"_id": "d1", "name": "main.tex"}]), "main.tex")


@pytest.mark.xfail(reason="#77: binary files live in fileRefs and need the /file/{id} endpoint")
def test_delete_binary_file(rsps, client):
    rsps.add(responses.DELETE, f"{BASE}/project/p1/file/b1", status=204)
    client.delete_file("p1", project_infos(root_files=[{"_id": "b1", "name": "plot.png"}]), "plot.png")
    assert len(rsps.calls) == 1


# --- download_pdf ----------------------------------------------------------------------------------------------

def test_download_pdf_compiles_then_fetches_output(rsps, client):
    rsps.add(responses.POST, f"{BASE}/project/p1/compile", json={
        "status": "success",
        "outputFiles": [{"type": "log", "path": "output.log", "url": "/project/p1/build/1/output/output.log"},
                        {"type": "pdf", "path": "output.pdf", "url": "/project/p1/build/1/output/output.pdf"}],
    })
    rsps.add(responses.GET, f"{BASE}/project/p1/build/1/output/output.pdf", body=b"%PDF-1.5")
    assert client.download_pdf("p1") == ("output.pdf", b"%PDF-1.5")


def test_download_pdf_raises_if_compile_fails(rsps, client):
    rsps.add(responses.POST, f"{BASE}/project/p1/compile", json={"status": "failure", "outputFiles": []})
    with pytest.raises(requests.HTTPError):
        client.download_pdf("p1")
