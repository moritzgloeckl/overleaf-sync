"""OverleafClient can talk to another Overleaf server (e.g. a self-hosted Community Edition, #65)."""

import json
from pathlib import Path

import pytest
import responses

from olsync.olclient import OverleafClient

CE = "http://overleaf.example.test:8080"
FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def rsps():
    with responses.RequestsMock() as mock:
        yield mock


@pytest.fixture
def client():
    return OverleafClient({"overleaf.sid": "s"}, "csrf-token", base_url=CE + "/")


def test_default_server_is_overleaf_com():
    assert OverleafClient({}, "csrf").base_url == "https://www.overleaf.com"


def test_trailing_slash_is_ignored(client):
    assert client.base_url == CE


def test_project_list_and_csrf_use_the_configured_server(rsps, client):
    rsps.add(
        responses.GET, f"{CE}/project", body=(FIXTURES / "dashboard_2026.html").read_text(), content_type="text/html"
    )
    assert sorted(p["name"] for p in client.all_projects()) == ["Paper", "Thesis"]
    assert client.get_project("Thesis")["id"] == "p1"
    assert client.fetch_csrf() == "csrf-from-page"


def test_file_operations_use_the_configured_server(rsps, client):
    infos = {
        "rootFolder": [{"_id": "root", "docs": [{"_id": "d1", "name": "main.tex"}], "fileRefs": [], "folders": []}]
    }
    rsps.add(responses.GET, f"{CE}/project/p1/download/zip", body=b"PK")
    rsps.add(
        responses.POST,
        f"{CE}/project/p1/folder",
        json={"_id": "f1", "name": "figs", "docs": [], "fileRefs": [], "folders": []},
    )
    rsps.add(responses.POST, f"{CE}/project/p1/upload", json={"success": True})
    rsps.add(responses.DELETE, f"{CE}/project/p1/doc/d1", status=204)
    assert client.download_project("p1") == b"PK"
    assert client.upload_file("p1", infos, "figs/a.png", 3, b"abc") is True
    assert client.delete_file("p1", infos, "main.tex") is True


def test_pdf_download_uses_the_configured_server(rsps, client):
    rsps.add(
        responses.POST,
        f"{CE}/project/p1/compile",
        json={
            "status": "success",
            "outputFiles": [{"type": "pdf", "path": "output.pdf", "url": "/project/p1/build/b1/output/output.pdf"}],
        },
    )
    rsps.add(responses.GET, f"{CE}/project/p1/build/b1/output/output.pdf", body=b"%PDF-1.5")
    assert client.download_pdf("p1") == ("output.pdf", b"%PDF-1.5")
    assert json.loads(rsps.calls[0].request.body)["check"] == "silent"
