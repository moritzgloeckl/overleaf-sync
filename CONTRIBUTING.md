# Contributing to overleaf-sync

Thanks for helping! Bug reports, fixes and features are all welcome. This page explains how to set up the project, how the tests work, and what a pull request should contain.

## Reporting bugs

Please [open an issue](https://github.com/moritzgloeckl/overleaf-sync/issues) with:

- `ols --version`, your operating system and Python version
- whether you use overleaf.com or a self-hosted server (and its version)
- the full output of the failing command, run with `-v`

overleaf-sync talks to Overleaf's website like a browser does, so a change on Overleaf's side can break it overnight. If many things suddenly fail at once, that's the most likely reason, and a report helps everyone.

## Development setup

You need Python 3.11 or newer.

```bash
git clone https://github.com/moritzgloeckl/overleaf-sync.git
cd overleaf-sync
python3 -m venv venv && source venv/bin/activate
pip install -e ".[dev,gui]"     # leave out gui if you don't work on the login window
```

`ols` (and `overleaf-sync`) now run your working copy.

## Tests

The tests are written with pytest and come in three kinds:

| Kind | Command | Needs | Runs in CI |
|---|---|---|---|
| Unit tests (`tests/unit/`) | `pytest` | nothing | every PR, Python 3.11–3.14 on Linux, macOS and Windows |
| Integration tests (`tests/integration/`) | `pytest -m integration` | Docker | every PR |
| Smoke tests (`tests/smoke/`) | `pytest -m smoke` | an overleaf.com session | never (local only) |

**Unit tests** fake Overleaf with [`responses`](https://github.com/getsentry/responses) or small fake clients and run in under a second.

**Integration tests** run against a real Overleaf Community Edition in Docker (`tests/integration/compose.yml`). The tests start it automatically when nothing answers on `http://127.0.0.1:8080`, create a test user and projects, and stop it again afterwards (pass `--keep-ce` to keep it running between runs). The image is amd64-only: on Apple Silicon, enable Rosetta in Docker Desktop. The first start can take several minutes. To start it yourself:

```bash
docker compose -f tests/integration/compose.yml up -d --wait
pytest -m integration --keep-ce
```

**Smoke tests** check the real overleaf.com, read-only, against a project you pin. Use a dedicated test account if you can. Copy `.env.example` to `.env` (it's git-ignored) and fill in:

- `OLSYNC_SMOKE_COOKIE`: the `overleaf_session2` cookie of a browser that is logged in (no password; Overleaf's login has a captcha), or `OLSYNC_SMOKE_AUTH`: the path of a login file from `ols login --auth-file …`
- `OLSYNC_SMOKE_PROJECT_ID`: the id from the project's URL. The project's name must start with `olsync-smoke`, otherwise the tests refuse to run

Overleaf rate-limits requests (e.g. 30 dashboard loads and 10 zip downloads per minute), so don't run the smoke tests in a loop.

## Code style

- Lint and format with [ruff](https://docs.astral.sh/ruff/): `ruff check .` and `ruff format .`. Both are enforced in CI.
- Match the surrounding code: plain functions, docstrings with `Params:` / `Returns:` in `olclient.py`, `click.echo` for output.
- Keep paths sent to Overleaf POSIX-style (`/`), also on Windows.

## Pull requests

- **Write a test first.** For a bug, add a test that fails without your fix, and mention that in the PR. For behaviour that only real servers show, add an integration test if you can.
- Keep a PR to one topic, and describe what you verified (unit, integration, smoke, by hand).
- Add a line to `CHANGELOG.md` under `[Unreleased]` for anything users notice.
- Don't commit `.olauth`, `.env` or real project content.

How releases are made is described in [RELEASING.md](RELEASING.md).
