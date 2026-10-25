"""The real Qt login window (offscreen) against a self-hosted server. Skipped without the `gui` extra."""
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(importlib.util.find_spec("PySide6") is None, reason="needs PySide6 (the gui extra)"),
]

DRIVER = Path(__file__).parent / "qt_login_driver.py"


def test_login_window_logs_in_to_a_self_hosted_server(ce_credentials, ce_server):
    email, password = ce_credentials
    result = subprocess.run([sys.executable, str(DRIVER), ce_server, email, password],
                            capture_output=True, text=True, timeout=180)
    assert result.returncode == 0, result.stderr[-2000:]
    outcome = json.loads(result.stdout.strip().splitlines()[-1])
    assert outcome == {"cookie_names": ["overleaf.sid"], "csrf": True}
