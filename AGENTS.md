# AGENTS.md

Guidance for AI coding agents working in this repository.

## Project overview

`overleaf-sync` (PyPI: `overleaf-sync`, CLI: `ols`) is a small Python CLI for two-way syncing of Overleaf projects with a local folder. It works with free Overleaf accounts and talks to Overleaf's **unofficial, undocumented** web endpoints (HTML scraping, REST calls, and Socket.IO), so it can break whenever Overleaf changes its frontend.

## Layout

```
olsync/
  __init__.py         # package docstring + __version__ (flit reads the version from here)
  olsync.py           # click CLI: default sync command + `login`, `list`, `download` subcommands; sync logic
  olclient.py         # OverleafClient: HTTP/Socket.IO wrapper around overleaf.com (or another server via base_url)
  olbrowserlogin.py   # PySide6 (Qt WebEngine) mini browser used by `ols login`
pyproject.toml        # [project] metadata (flit_core backend), dependencies + extras, pytest/ruff config
tests/                # unit/ (default), integration/ (CE container), smoke/ (overleaf.com, local only)
.github/workflows/    # ci.yml: ruff + unit tests on 3.11-3.14 x ubuntu/macos/windows
```

Tests use pytest. `pytest` runs unit tests only; `-m integration` and `-m smoke` are opt-in markers (see `pyproject.toml`).

- **Integration tests** (`tests/integration/`) run against a local Overleaf Community Edition from `tests/integration/compose.yml` (`sharelatex/sharelatex`, pinned; amd64-only, so on Apple Silicon it needs Docker Desktop with Rosetta). The fixtures start the stack if nothing answers on `http://127.0.0.1:8080` (`OLSYNC_CE_URL`) and stop it afterwards unless `--keep-ce` is passed; a first start from scratch can take 10+ minutes under Rosetta. They create the first admin via `/launchpad/register_admin`, log in once per run and read CSRF tokens from the pages' `ol-csrfToken` meta tag (`/dev/csrf` is disabled in the image). Use `127.0.0.1`, not `localhost`: Python's cookie jar never sends cookies back to `localhost`. Overleaf rate-limits zip downloads (10/min per project), project creation (20/min) and logins, hence one project per test module, or per test for CLI round trips. CI runs them in the `integration` job.
- **Smoke tests** (`tests/smoke/`) hit overleaf.com with a real session from the git-ignored `.env` (see `.env.example`). Never run them unless asked, and only against the pinned `olsync-smoke*` project.

Lint and format with `ruff check .` and `ruff format .` (both enforced in CI; line length 120). `.git-blame-ignore-revs` lists the mechanical formatting commit (`git config blame.ignoreRevsFile .git-blame-ignore-revs`). `.gitignore` also ignores `setup.py`, `.olauth*`, `.olignore`, `.olsync-state.json` and `.env`.

## How it works

- **Login** (`olbrowserlogin.py`): opens a Qt WebEngine window on the Overleaf login page. Once the URL becomes `https://www.overleaf.com/project`, it grabs the `overleaf_session2` and `GCLB` cookies plus the CSRF token from the `ol-csrfToken` meta tag. `olsync.login_handler` saves the login with `olsync/auth.py`: JSON `{"version": 2, "server": ..., "cookies": {...}, "csrf": ...}` in `.olauth` (`--auth-file`), written atomically with mode 0600. Pickle files from 2.0.0a4 and earlier are detected by their first byte and **never unpickled**; the user is asked to log in again. The server is overleaf.com or a self-hosted server (`--server` / `OLSYNC_SERVER`); `load_client` resolves it as explicit option > stored server > overleaf.com (Session cookies are `overleaf_session2` (+ `GCLB`) on overleaf.com and `overleaf.sid` (`sharelatex.sid` before CE 5) on self-hosted servers; `ols login --cookie` tries them in that order. Credentials are never handled by this tool. `.olauth` is read back with `pickle.load`, so never load an untrusted one. `OverleafClient.login(username, password)` is dead code (broken by captchas); don't revive it.
- **Client** (`olclient.py`):
  - All requests go through `_request`, which waits and retries when Overleaf answers HTTP 429 (rate limits: e.g. 30 dashboard loads and 10 zip downloads per minute; no `Retry-After` header) and finally raises `RateLimitError`, which the CLI shows as a clear message.
  - Projects are read by scraping the `ol-prefetchedProjectsBlob` meta tag on the dashboard (`{totalSize, projects}`; the old `ol-projects` tag is a fallback); archived/trashed projects are filtered out. Projects are matched by exact name.
  - The project file tree (folder/doc IDs) comes from Overleaf's real-time service (`get_project_infos`), using `socketIO-client==0.5.7.2` (Socket.IO 0.9 protocol at `/socket.io/1/`; keep the pin). The handshake must carry `?projectId=...`; the server then pushes a `joinProjectResponse` event. A preliminary handshake request captures the fresh `GCLB` load-balancer cookie, and a module-level shim restores `websocket.SSLError` for newer `websocket-client` versions.
  - Download = project zip; upload = multipart POST per file (creating missing folders first, case-insensitive folder match; the `name` field must be the bare file name, Overleaf rejects `/`); PDF = trigger compile, then fetch the first `pdf` output file.
  - Delete only searches the `docs` lists of the tree and calls the `/doc/{id}` URL. Binary files (images, PDFs) are most likely listed elsewhere in Overleaf's tree (`fileRefs`), so they probably can't be deleted remotely, and the CLI still lists them under `[DELETE]` without reporting the failure.
  - All Overleaf URLs are module-level constants at the top of `olclient.py`.
- **Sync** (`olsync.py`): `main` does `os.chdir(sync_path)` (all paths after that are relative to the CWD) and downloads the project zip once.
  - **Two-way (default):** `two_way_sync` decides per file with the state of the last sync (`olsync/syncstate.py`, `.olsync-state.json` in the sync folder, keyed by server and project id, separate local and remote content hashes): changed on one side → sync, changed on both sides or differing without history → prompt `l`/`r`/`s`, skipped conflicts keep their old state. After uploads it downloads the zip again to record the remote hashes (Overleaf may normalise files). Measured: the zip reflects uploads immediately, on overleaf.com and CE.
  - **`-l` / `-r`:** the generic `sync_func` with lambdas for create/delete/compare. Its "newer" check still compares the local mtime with the **project-wide** `lastUpdated` timestamp and only prompts when the source looks *older* (known limitation, `xfail` in `test_sync_func.py`).
  - Deletions are only offered with `-l` or `-r` (never in default two-way mode) and are resolved with `click.prompt` (`d`/`r`/`i`).
  - `sync_func` has its own try/except → `ClickException`; it is not wrapped by `execute_action`.
- **`.olignore`**: `fnmatch` patterns applied to the local file list from `glob('**', recursive=True)`, which skips dotfiles and hidden dirs (so `.olauth`/`.olignore` are never uploaded). A folder needs `folder/*`, not `folder/`. Despite the CLI help text, it also matters outside local→remote:
  - with `-l`, remote deletion candidates are zip entries not in the local keep list, so remote files matching `.olignore` (and remote dotfiles) are offered for deletion on Overleaf;
  - with `-r`, it filters the local deletion candidates.
- `execute_action` wraps steps in a `yaspin` spinner; a falsy return value or an exception becomes a `click.ClickException`. `-v/--verbose` prints tracebacks.

## Conventions

- Keep paths POSIX-style (`/`) when talking to Overleaf, also on Windows (`PATH_SEP` in `olclient.py`, `Path(...).as_posix()` in `olsync.py`). Several past fixes were Windows path bugs.
- `olsync.py` imports with a try/except fallback so it runs both installed (`olsync.olclient`) and directly from inside `olsync/` (`olclient`). Keep both branches working when adding modules.
- Match the existing style: plain functions and lambdas, docstrings with `Params:` / `Returns:` sections in `olclient.py`, `click.echo` for user output.
- The auth file option is `--auth-file` on every command (`auth_file_options` / `resolve_auth_file` in `olsync.py`, which also honour `ols --auth-file X <command>`). The pre-2.0 names (`--store-path`, and `--path` on `login`) are hidden aliases that print a deprecation warning. `-p/--path` on sync means the sync directory.
- User-facing behavior and options are documented in `README.md`; update it when you add or change CLI options. Parts of it are already stale (it says "Qt5", and its sample output predates the current `sync_func` output).

## Development

```bash
python3 -m venv venv && source venv/bin/activate
pip install -e ".[dev]"        # add ,gui for the PySide6 login window
pytest && ruff check .
```

PySide6 is optional (the `gui` extra) and only imported by `ols login` (`load_browser_login` in `olsync.py`); keep it out of module-level imports. `python olsync/olsync.py --help` works from source, but `--version` reads installed package metadata (`package_name='overleaf-sync'`) and needs an installed package.

Almost everything else needs a real Overleaf account and network access: run `ols login` first (opens a GUI window), then test against a throwaway Overleaf project. Never commit `.olauth` (it's gitignored, but it is a live session cookie) or real project content.

## Releasing

The version lives only in `olsync/__init__.py` (`__version__`); flit reads it from there and `release.yml` checks that the tag matches it.

Dependencies live only in `pyproject.toml`.

Build locally with `python -m build` (backend `flit_core >=3.4,<4`). Releases are automated: pushing a tag `vX.Y.Z` runs `.github/workflows/release.yml`, which publishes to PyPI via Trusted Publishing after the maintainer approves the `pypi` environment (restricted to `v*` tags). A manual run of the workflow publishes to TestPyPI.

## Known gotchas

- `olsync.py` calls `olignore_keep_list()` inside the `-l` deletion list comprehension, i.e. once per zip entry, re-globbing the tree and re-printing the `.olignore` notice each time. Hoist it if you touch that code.
- Overleaf may take 1–2 minutes before remote edits show up in the downloaded zip / `lastUpdated` (see README "Known Bugs").
