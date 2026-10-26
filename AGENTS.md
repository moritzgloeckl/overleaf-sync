# AGENTS.md

Guidance for AI coding agents working in this repository. Human contributors: see [CONTRIBUTING.md](CONTRIBUTING.md).

## Project overview

`overleaf-sync` (PyPI: `overleaf-sync`, CLI: `ols`, alias `overleaf-sync`) is a Python CLI that syncs Overleaf projects with a local folder, in both directions. It works with free overleaf.com accounts and self-hosted Overleaf (Community Edition) and talks to Overleaf's **unofficial, undocumented** web endpoints (HTML scraping, REST calls, the real-time service), so it can break whenever Overleaf changes its frontend.

## Layout

```
olsync/
  __init__.py         # package docstring + __version__ (single source of the version; flit reads it)
  olsync.py           # click CLI: default sync command + `login`, `list`, `download`; sync logic
  olclient.py         # OverleafClient: HTTP calls to overleaf.com or another server (base_url)
  realtime.py         # project file tree from Overleaf's real-time service (Socket.IO 0.9 over xhr-polling)
  syncstate.py        # per-file sync state (.olsync-state.json) and the two-way decision table
  auth.py             # the persisted login (.olauth, JSON)
  olbrowserlogin.py   # PySide6 (Qt WebEngine) login window used by `ols login` (optional `gui` extra)
tests/
  unit/               # default `pytest` run, no network
  integration/        # `pytest -m integration`: local Overleaf CE in Docker (compose.yml)
  smoke/              # `pytest -m smoke`: overleaf.com with a real session, local only
pyproject.toml        # [project] metadata (flit_core backend), dependencies + extras, pytest/ruff config
.github/workflows/    # ci.yml (lint, unit matrix, build, integration), release.yml (PyPI via Trusted Publishing)
```

## Tests

`pytest` runs unit tests only; `-m integration` and `-m smoke` are opt-in markers (see `pyproject.toml`). Work test-first: a bug fix starts with a test that fails without the fix.

- **Integration tests** run against a local Overleaf Community Edition from `tests/integration/compose.yml` (`sharelatex/sharelatex`, pinned; amd64-only, so on Apple Silicon Docker Desktop needs Rosetta). The fixtures start the stack if nothing answers on `http://127.0.0.1:8080` (`OLSYNC_CE_URL`) and stop it afterwards unless `--keep-ce` is passed. They create the first admin via `/launchpad/register_admin`, log in once per run, and read CSRF tokens from the pages' `ol-csrfToken` meta tag (`/dev/csrf` is disabled in the image). Use `127.0.0.1`, not `localhost`: Python's cookie jar never sends cookies back to `localhost`. Overleaf rate-limits zip downloads (10/min per project), the dashboard (30/min), project creation (20/min) and logins; hence one project per test module, or per test for CLI round trips. `test_login_window.py` drives the real Qt login window offscreen (skipped without PySide6; CI installs the system libraries).
- **Smoke tests** hit overleaf.com with a session from the git-ignored `.env` (see `.env.example`). **Never run them unless asked**, and only against the pinned `olsync-smoke*` project.

Lint and format with `ruff check .` and `ruff format .` (both enforced in CI; line length 120). `.git-blame-ignore-revs` lists the mechanical formatting commit.

## How it works

- **Login** (`olbrowserlogin.py`, `olsync.login`): the Qt window opens `<server>/login`; once it reaches `<server>/project` it takes the session cookies (`overleaf_session2` + `GCLB` on overleaf.com, `overleaf.sid` / `sharelatex.sid` on self-hosted servers) and the CSRF token. `ols login --cookie` instead takes the cookie from a hidden prompt or `OLSYNC_COOKIE` (never a CLI argument) and fetches the CSRF token; on self-hosted servers it tries `overleaf.sid`, then `sharelatex.sid`. Passwords are never handled.
- **Auth file** (`auth.py`): JSON `{"version": 2, "server": ..., "cookies": {...}, "csrf": ...}` in `.olauth` (`--auth-file`), written atomically with mode 0600. Pickle files from 2.0.0a4 and earlier are recognised by their first byte and **never unpickled**; the user is asked to log in again.
- **Server**: `load_client` resolves it as `--server`/`OLSYNC_SERVER` > stored server > overleaf.com.
- **Client** (`olclient.py`):
  - All requests go through `_request`, which waits and retries on HTTP 429 (no `Retry-After` header; waits `RATE_LIMIT_WAITS`) and finally raises `RateLimitError`. A redirect of the dashboard to `/login` raises `SessionExpiredError`. The CLI shows both as clear messages.
  - Projects come from the `ol-prefetchedProjectsBlob` meta tag on the dashboard (`{totalSize, projects}`; the old `ol-projects` tag is a fallback); archived/trashed projects are filtered out, projects are matched by exact name.
  - The file tree (folder/doc/file IDs) comes from `realtime.join_project`: handshake `GET /socket.io/1/?projectId=...`, polls on `/socket.io/1/xhr-polling/<sid>` return `1::`, then the `joinProjectResponse` event; heartbeats (`2::`) are answered, rejections/errors/timeouts raise `RealtimeError`, and the session is always disconnected. The `requests.Session` keeps overleaf.com's `GCLB` cookie from the handshake.
  - Download = project zip (reflects uploads immediately, measured on overleaf.com and CE); upload = multipart POST per file (missing folders are created first, folders match case-insensitively; the `name` field must be the bare file name, Overleaf rejects `/`); delete = `DELETE /project/<id>/doc|file/<id>` (text files are `docs`, binary files `fileRefs` in the tree); PDF = compile (no `rootDoc_id`), then fetch the `pdf` output with `compileGroup`/`clsiserverid`.
  - Paths are relative to `base_url` (`*_PATH` constants at the top of `olclient.py`).
- **Sync** (`olsync.py`): `main` does `os.chdir(sync_path)` (paths after that are relative to the CWD) and downloads the project zip once.
  - **Two-way (default):** `two_way_sync` decides per file with the sync state (`syncstate.py`, `.olsync-state.json` in the sync folder, keyed by server and project id, separate local and remote content hashes): changed on one side → sync; changed on both sides, or differing without history → prompt `l`/`r`/`s`; skipped conflicts keep their old state. After uploads it reads the zip again to record the remote hashes (Overleaf may normalise files). Two-way sync never deletes.
  - **`-l` / `-r`:** the generic `sync_func` with lambdas for create/delete/compare. A differing file is overwritten without asking only if the target side is unchanged since the last sync (`to_unchanged_since_last_sync`); `record_state` then updates the sync state, so the modes can be mixed. Deletions are only offered here (`d`/`r`/`i`).
- **`.olignore`**: `fnmatch` patterns applied to the local file list from `glob('**', recursive=True)`, which skips dotfiles and hidden dirs (so `.olauth`, `.olsync-state.json` are never uploaded); a leading `./` in patterns is ignored. A folder needs `folder/*`, not `folder/`. With `-l`, remote files not in the local keep list are deletion candidates; with `-r`, it filters the local deletion candidates.
- `execute_action` wraps steps in a `yaspin` spinner; a falsy return value or an exception becomes a `ClickException` (already explained `ClickException`s, `RateLimitError` and `SessionExpiredError` keep their message). `-v/--verbose` prints tracebacks.

## Conventions

- Keep paths POSIX-style (`/`) when talking to Overleaf, also on Windows (`PATH_SEP`, `Path(...).as_posix()`). Several past fixes were Windows path bugs.
- Modules import each other with a try/except fallback, so they run both installed (`olsync.x`) and from inside `olsync/` (`x`). Keep both working when adding modules.
- PySide6 is optional and only imported by `ols login` (`load_browser_login`); keep it out of module-level imports.
- Match the existing style: plain functions and lambdas, docstrings with `Params:` / `Returns:` sections, `click.echo` for user output.
- The auth file option is `--auth-file` on every command (`auth_file_options` / `resolve_auth_file`, which also honour `ols --auth-file X <command>`). The pre-2.0 names (`--store-path`, and `--path` on `login`) are hidden aliases with a deprecation warning. `-p/--path` on sync means the sync directory. `--server` follows the same pattern (`server_option`).
- User-facing behaviour is documented in `README.md`, changes in `CHANGELOG.md` (`[Unreleased]`); update both when you change behaviour or options.
- Never commit `.olauth`, `.env` or real project content.

## Development

```bash
python3 -m venv venv && source venv/bin/activate
pip install -e ".[dev,gui]"
pytest && ruff check . && ruff format --check .
```

`--version` reads installed package metadata, so it needs an installed package.

## Releasing

See [RELEASING.md](RELEASING.md): release PR (version in `olsync/__init__.py`, changelog), merge, tag `vX.Y.Z`; `release.yml` publishes to PyPI via Trusted Publishing after the maintainer approves the `pypi` environment (restricted to `v*` tags). Dependencies live only in `pyproject.toml`.
