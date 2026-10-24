"""Project list parsing from the Overleaf dashboard page."""
from pathlib import Path

import pytest
import responses

from olsync.olclient import OverleafClient

FIXTURES = Path(__file__).parent.parent / "fixtures"
PROJECT_URL = "https://www.overleaf.com/project"


@pytest.fixture
def dashboard():
    with responses.RequestsMock() as rsps:
        yield lambda fixture: rsps.add(responses.GET, PROJECT_URL, body=(FIXTURES / fixture).read_text(),
                                       content_type="text/html")


def test_filter_projects_drops_archived_and_trashed():
    projects = [{"name": "a"}, {"name": "b", "archived": True}, {"name": "c", "trashed": True}]
    assert [p["name"] for p in OverleafClient.filter_projects(projects)] == ["a"]


def test_filter_projects_matches_extra_attributes():
    projects = [{"name": "a"}, {"name": "b"}]
    assert [p["name"] for p in OverleafClient.filter_projects(projects, {"name": "b"})] == ["b"]


def test_all_projects_old_dashboard(dashboard):
    dashboard("dashboard_old.html")
    assert sorted(p["name"] for p in OverleafClient({}, "csrf").all_projects()) == ["Paper", "Thesis"]


def test_get_project_old_dashboard(dashboard):
    dashboard("dashboard_old.html")
    assert OverleafClient({}, "csrf").get_project("Thesis")["id"] == "p1"


@pytest.mark.xfail(reason="#32/#63/#75: Overleaf renamed the meta tag to ol-prefetchedProjectsBlob (fixed by #84)")
def test_all_projects_2026_dashboard(dashboard):
    dashboard("dashboard_2026.html")
    assert sorted(p["name"] for p in OverleafClient({}, "csrf").all_projects()) == ["Paper", "Thesis"]


@pytest.mark.xfail(reason="#32/#63/#75: Overleaf renamed the meta tag to ol-prefetchedProjectsBlob (fixed by #84)")
def test_get_project_2026_dashboard(dashboard):
    dashboard("dashboard_2026.html")
    assert OverleafClient({}, "csrf").get_project("Thesis")["id"] == "p1"


def test_get_project_unknown_name_returns_none(dashboard):
    dashboard("dashboard_old.html")
    assert OverleafClient({}, "csrf").get_project("Nope") is None
