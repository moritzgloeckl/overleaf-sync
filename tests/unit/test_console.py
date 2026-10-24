import io
import sys

from olsync import olsync as cli


def test_console_is_switched_to_utf8_on_legacy_codepages(monkeypatch):
    stdout = io.TextIOWrapper(io.BytesIO(), encoding="cp1252")
    monkeypatch.setattr(sys, "stdout", stdout)
    monkeypatch.setattr(sys, "stderr", io.TextIOWrapper(io.BytesIO(), encoding="cp1252"))
    cli.configure_console()
    print("✅ done")
    stdout.flush()
    assert stdout.buffer.getvalue().decode("utf-8") == "✅ done\n"

