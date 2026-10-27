"""A failed download must leave the previous local file intact."""

import os
import stat

import pytest

from olsync import olsync as cli


@pytest.mark.parametrize("error", [OSError, KeyboardInterrupt])
def test_failed_write_preserves_original_and_removes_temporary_file(tmp_path, monkeypatch, error):
    path = tmp_path / "main.tex"
    path.write_bytes(b"original document")
    real_fdopen = os.fdopen
    real_open = open

    class InterruptedWrite:
        def __init__(self, file):
            self.file = file

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.file.close()

        def write(self, content):
            self.file.write(content[:4])
            raise error("interrupted download")

    monkeypatch.setattr(cli.os, "fdopen", lambda *args, **kwargs: InterruptedWrite(real_fdopen(*args, **kwargs)))
    monkeypatch.setattr("builtins.open", lambda *args, **kwargs: InterruptedWrite(real_open(*args, **kwargs)))
    with pytest.raises(error):
        cli.write_file(str(path), b"replacement document")
    assert path.read_bytes() == b"original document"
    assert list(tmp_path.iterdir()) == [path]


def test_failed_replacement_preserves_original_and_removes_temporary_file(tmp_path, monkeypatch):
    path = tmp_path / "main.tex"
    path.write_bytes(b"original document")

    def fail_replace(*args):
        raise OSError("replacement denied")

    monkeypatch.setattr(cli.os, "replace", fail_replace)
    with pytest.raises(OSError, match="replacement denied"):
        cli.write_file(str(path), b"replacement document")
    assert path.read_bytes() == b"original document"
    assert list(tmp_path.iterdir()) == [path]


@pytest.mark.skipif(os.name == "nt", reason="POSIX file permissions")
def test_replacement_preserves_existing_permissions(tmp_path):
    path = tmp_path / "main.tex"
    path.write_bytes(b"original")
    path.chmod(0o640)
    cli.write_file(str(path), b"replacement")
    assert path.read_bytes() == b"replacement"
    assert stat.S_IMODE(path.stat().st_mode) == 0o640


@pytest.mark.skipif(os.name == "nt", reason="Creating symlinks can require elevated privileges")
def test_replacement_preserves_symlink_and_updates_its_target(tmp_path):
    target = tmp_path / "actual.tex"
    target.write_bytes(b"original")
    link = tmp_path / "main.tex"
    link.symlink_to(target)
    cli.write_file(str(link), b"replacement")
    assert link.is_symlink()
    assert target.read_bytes() == b"replacement"
