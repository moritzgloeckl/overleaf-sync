import pytest


@pytest.fixture(autouse=True)
def isolate_from_user_environment(monkeypatch):
    """Unit tests must not pick up the developer's own server or session settings."""
    for name in ("OLSYNC_SERVER", "OLSYNC_COOKIE"):
        monkeypatch.delenv(name, raising=False)
