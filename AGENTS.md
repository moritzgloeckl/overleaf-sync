# AGENTS.md

Guidance for AI coding agents working in this repository.

## Project overview

`overleaf-sync` (PyPI: `overleaf-sync`, CLI: `ols`) is a small Python CLI for two-way syncing of Overleaf projects with a local folder. It works with free Overleaf accounts and talks to Overleaf's **unofficial, undocumented** web endpoints (HTML scraping, REST calls, and Socket.IO), so it can break whenever Overleaf changes its frontend.

## Layout

```
olsync/
  __init__.py         # package docstring + __version__ (flit reads the version from here)
  olsync.py           # click CLI: default sync command + `login`, `list`, `download` subcommands; sync logic
  olclient.py         # OverleafClient: HTTP/Socket.IO wrapper around overleaf.com
  olbrowserlogin.py   # PySide6 (Qt WebEngine) mini browser used by `ols login`
pyproject.toml        # flit build config, dependencies, `ols` entry point
requirements.txt      # same dependencies, for dev installs
```

There is no test suite, CI, linter, or formatter config, so keep diffs minimal and in the surrounding style. `.gitignore` ignores anything matching `test*` (plus `setup.py`, `.olauth`, `.olignore`), so a new `tests/` folder or `test_*.py` file is silently untracked: use `git add -f` or adjust `.gitignore`. The existing local `tests/` only holds stale `.pyc` files.

## How it works

- **Login** (`olbrowserlogin.py`): opens a Qt WebEngine window on the Overleaf login page. Once the URL becomes `https://www.overleaf.com/project`, it grabs the `overleaf_session2` and `GCLB` cookies plus the CSRF token from the `ol-csrfToken` meta tag. `olsync.login_handler` pickles `{"cookie": ..., "csrf": ...}` to `.olauth` (path configurable). Credentials are never handled by this tool. `.olauth` is read back with `pickle.load`, so never load an untrusted one. `OverleafClient.login(username, password)` is dead code (broken by captchas); don't revive it.
- **Client** (`olclient.py`):
  - Projects are read by scraping the `ol-projects` meta tag on the dashboard; archived/trashed projects are filtered out. Projects are matched by exact name.
  - The project file tree (folder/doc IDs) comes from a Socket.IO `joinProject` event (`get_project_infos`), using `socketIO-client==0.5.7.2`. The pin is marked "Do not upgrade!" in `requirements.txt` (presumably because newer clients speak a protocol Overleaf rejects); leave it alone. `get_project_infos` needs both `GCLB` and `overleaf_session2` in the stored cookie and fails with a `KeyError` (only visible with `-v`) if either is missing.
  - Download = project zip; upload = multipart POST per file (creating missing folders first, case-insensitive folder match); PDF = trigger compile, then fetch the first `pdf` output file.
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
pip install -r requirements.txt
pip install "flit<4" "flit_core<4" && flit install --symlink   # installs the `ols` command in dev mode
```

`pyproject.toml` uses the legacy `[tool.flit.metadata]` table and an unpinned `flit` build requirement. flit/flit_core 4.x reject it ("The [tool.flit.metadata] table is no longer supported"), so a plain `pip install flit`, `pip install .` or `flit build` fails. Use the pins above, or migrate to a `[project]` table with the `flit_core.buildapi` backend.

PySide6 is imported eagerly (`olsync.py` imports `olbrowserlogin` at module top), so it is required for every command, even `--help`. `python olsync/olsync.py --help` works from source once dependencies are installed, but `--version` reads installed package metadata (`package_name='overleaf-sync'`) and needs an installed package.

Almost everything else needs a real Overleaf account and network access: run `ols login` first (opens a GUI window), then test against a throwaway Overleaf project. Never commit `.olauth` (it's gitignored, but it is a live session cookie) or real project content.

## Releasing

Version bumps touch four files; keep them in sync (each module has an MIT header block with a `Version:` line):
- `olsync/__init__.py` (`__version__`)
- the `Version:` header in `olsync/olsync.py`, `olsync/olclient.py`, `olsync/olbrowserlogin.py`

If dependencies change, update both `pyproject.toml` and `requirements.txt`.

Build and publish with flit (`flit build`, `flit publish`, using the `flit<4` / `flit_core<4` pins above); artifacts land in `dist/`.

## Known gotchas

- `olclient.py` compares `r.status_code == str(200)` / `str(400)` / `str(204)`. `status_code` is an `int`, so these checks are always `False`:
  - `upload_file` and `delete_file` always return `False` (callers currently ignore it);
  - `create_folder` raises `HTTPError` on "folder already exists" (400) instead of returning `None`. Even if it returned `None`, `upload_file` would crash on `new_folder['_id']`.
- `olsync.py` calls `olignore_keep_list()` inside the `-l` deletion list comprehension, i.e. once per zip entry, re-globbing the tree and re-printing the `.olignore` notice each time. Hoist it if you touch that code.
- Overleaf may take 1–2 minutes before remote edits show up in the downloaded zip / `lastUpdated` (see README "Known Bugs").
