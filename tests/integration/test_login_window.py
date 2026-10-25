"""The real Qt login window (offscreen) against a self-hosted server. Skipped without the `gui` extra."""
import importlib.util
import json
import subprocess
import sys
import time
from pathlib import Path

import pytest
import requests

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(importlib.util.find_spec("PySide6") is None, reason="needs PySide6 (the gui extra)"),
]

DRIVER = Path(__file__).parent / "qt_login_driver.py"


def wait_until_dashboard_is_not_rate_limited(ce_login, ce_server):
    """The window loads the dashboard, which Overleaf limits to 30 loads per minute; earlier tests may have used them"""
    cookies, _ = ce_login
    deadline = time.time() + 75
    while requests.get(f"{ce_server}/project", cookies=cookies, timeout=30).status_code == 429:
        assert time.time() < deadline, "dashboard still rate limited"
        time.sleep(5)


def test_login_window_logs_in_to_a_self_hosted_server(ce_credentials, ce_login, ce_server):
    email, password = ce_credentials
    wait_until_dashboard_is_not_rate_limited(ce_login, ce_server)
    result = subprocess.run([sys.executable, str(DRIVER), ce_server, email, password],
                            capture_output=True, text=True, timeout=180)
    assert result.returncode == 0, result.stderr[-2000:]
    outcome = json.loads(result.stdout.strip().splitlines()[-1])
    assert outcome == {"cookie_names": ["overleaf.sid"], "csrf": True}
