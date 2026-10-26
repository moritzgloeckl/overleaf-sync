"""An expired or invalid session gives a clear "log in again" message instead of "Project could not be queried"."""

import pytest
import responses
from click.testing import CliRunner

from olsync import auth as olauth
from olsync import olclient
from olsync import olsync as cli
from olsync.olclient import OverleafClient, SessionExpiredError

BASE = "https://www.overleaf.com"


@pytest.fixture
def expired(monkeypatch):
    monkeypatch.setattr(olclient, "RATE_LIMIT_WAITS", ())
    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        # Overleaf redirects to the login page when the session is no longer valid
        rsps.add(responses.GET, f"{BASE}/project", status=302, headers={"Location": f"{BASE}/login"})
        rsps.add(responses.GET, f"{BASE}/login", body="<html><title>Log in</title></html>", content_type="text/html")
        yield rsps


@pytest.mark.parametrize("call", [lambda c: c.all_projects(), lambda c: c.get_project("Thesis")])
def test_client_raises_session_expired(expired, call):
    with pytest.raises(SessionExpiredError, match="ols login"):
        call(OverleafClient({"overleaf_session2": "old"}, "c"))


@pytest.mark.parametrize("args", [["list"], ["-r"], ["download"]], ids=["list", "sync", "download"])
def test_cli_explains_an_expired_session(expired, tmp_path, monkeypatch, args):
    project_dir = tmp_path / "Thesis"
    project_dir.mkdir()
    olauth.save_auth(project_dir / ".olauth", {"overleaf_session2": "old"}, "c", BASE)
    monkeypatch.chdir(project_dir)
    result = CliRunner().invoke(cli.main, args)
    assert result.exit_code != 0
    assert "session has expired" in result.output and "ols login" in result.output
