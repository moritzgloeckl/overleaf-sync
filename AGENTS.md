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

Lint with `ruff check .` (no formatter is enforced yet, so keep diffs minimal and in the surrounding style). `.gitignore` also ignores `setup.py`, `.olauth*`, `.olignore`, `.olsync-state.json` and `.env`.

## How it works

- **Login** (`olbrowserlogin.py`): opens a Qt WebEngine window on the Overleaf login page. Once the URL becomes `https://www.overleaf.com/project`, it grabs the `overleaf_session2` and `GCLB` cookies plus the CSRF token from the `ol-csrfToken` meta tag. `olsync.login_handler` pickles `{"cookie": ..., "csrf": ...}` to `.olauth` (path configurable). Credentials are never handled by this tool. `.olauth` is read back with `pickle.load`, so never load an untrusted one. `OverleafClient.login(username, password)` is dead code (broken by captchas); don't revive it.
- **Client** (`olclient.py`):
  - Projects are read by scraping the `ol-prefetchedProjectsBlob` meta tag on the dashboard (`{totalSize, projects}`; the old `ol-projects` tag is a fallback); archived/trashed projects are filtered out. Projects are matched by exact name.
  - The project file tree (folder/doc IDs) comes from Overleaf's real-time service (`get_project_infos`), using `socketIO-client==0.5.7.2` (Socket.IO 0.9 protocol at `/socket.io/1/`; keep the pin). The handshake must carry `?projectId=...`; the server then pushes a `joinProjectResponse` event. A preliminary handshake request captures the fresh `GCLB` load-balancer cookie, and a module-level shim restores `websocket.SSLError` for newer `websocket-client` versions.
  - Download = project zip; upload = multipart POST per file (creating missing folders first, case-insensitive folder match; the `name` field must be the bare file name, Overleaf rejects `/`); PDF = trigger compile, then fetch the first `pdf` output file.
  - Delete only searches the `docs` lists of the tree and calls the `/doc/{id}` URL. Binary files (images, PDFs) are most likely listed elsewhere in Overleaf's tree (`fileRefs`), so they probably can't be deleted remotely, and the CLI still lists them under `[DELETE]` without reporting the failure.
  - All Overleaf URLs are module-level constants at the top of `olclient.py`.
- **Sync** (`olsync.py`): `main` does `os.chdir(sync_path)` (all paths after that are relative to the CWD), downloads the project zip once and calls the generic `sync_func` once or twice (remote→local, then local→remote) with lambdas for create/delete/compare.
  - Change detection compares file bytes. The "newer" check compares the local mtime against the **project-wide** `lastUpdated` timestamp, not per file.
  - The user is only prompted when the source side looks *older*. If the source looks newer, differing files are overwritten without asking. In two-way mode, any remote edit after a local edit makes every differing file "newer" on remote, so local changes can be overwritten without a prompt. Don't treat the confirm prompt as real conflict protection.
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
- CLI flag names are inconsistent: the cookie file is `--path` on `login` but `--store-path` on sync/`list`/`download`, where `-p/--path` means the sync directory. Check the existing commands before you add or rename options.
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
