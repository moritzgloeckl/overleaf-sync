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
    # splitlines(): print() writes "\r\n" on Windows
    assert stdout.buffer.getvalue().decode("utf-8").splitlines() == ["✅ done"]


def test_no_color_warning_when_output_is_not_a_terminal(monkeypatch):
    # yaspin warns "color, on_color and attrs are not supported when output stream is not a TTY", e.g. when the
    # output of `ols` is piped into a file or another program
    import warnings

    monkeypatch.setattr(sys, "stdout", io.TextIOWrapper(io.BytesIO(), encoding="utf-8"))
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        cli.execute_action(lambda: True, "Working", "Done.", "Failed.")
    assert not [w for w in caught if "not supported when output stream is not a TTY" in str(w.message)]
