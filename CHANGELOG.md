# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Fixed
- `ols -r` and `ols -l` no longer overwrite changes silently either: they use the same sync history as two-way sync
  and only overwrite a file without asking if the other side did not change it since the last sync. Previously they
  decided by comparing timestamps with the project's last update time.

### Changed
- **Breaking:** the login (`.olauth`) is now stored as JSON, readable only by you, instead of Python's pickle format
  (loading a pickle file can run arbitrary code). Logins created by 2.0.0a4 or earlier are recognised, but never
  loaded: overleaf-sync asks you to run `ols login` once more.
- The login file option is now `--auth-file` on every command. The old names (`--store-path`, and `--path` on
  `ols login`) still work but are deprecated.

### Changed (internal)
- The project's file tree is now fetched from Overleaf's real-time service with a small built-in client (HTTP
  long-polling) instead of the unmaintained `socketIO-client` package from 2016, which also drops `websocket-client`
  as a dependency. `python-dateutil` is no longer needed either.

### Removed
- The unused username/password login code, which stopped working when Overleaf introduced captchas.

## [2.0.0a4] - 2026-10-25

Fourth pre-release of 2.0: two-way sync never overwrites changes without asking.

### Fixed
- **Two-way sync no longer overwrites changes silently.** overleaf-sync now remembers what each file looked like
  after the last sync (`.olsync-state.json`, stays local) and decides per file: changes on one side are synced, and
  files changed on both sides, or differing on the first sync, are only overwritten after asking. Previously, a
  remote edit anywhere in the project could make a sync replace local edits without asking.
- Overleaf's rate limits (HTTP 429, e.g. when syncing often) no longer make commands fail with unrelated errors:
  overleaf-sync waits and retries, and explains the rate limit if it persists.

## [2.0.0a3] - 2026-10-25

Third pre-release of 2.0: self-hosted Overleaf servers.

### Added
- Self-hosted Overleaf servers (tested with Community Edition): `ols login --server URL` (or `OLSYNC_SERVER`). The
  server is stored with the login and used by all other commands; `--server` works on every command (#65, #15).
  Building on the earlier work by @hrvylein (#17) and @mone27 (#64).
- `--server` also works with `ols login --cookie`, and the login window opens the server's login page.
- Integration tests against a local Overleaf Community Edition in Docker (including the login window), run in CI
  for every change.

### Fixed
- `ols` could hang forever when the connection to Overleaf's real-time service dropped, and made an unnecessary
  extra connection when cleaning up.

## [2.0.0a2] - 2026-10-24

Second pre-release of 2.0, with the fixes found while re-testing all open issues against 2.0.0a1.

### Added
- `ols login --cookie`: log in with the `overleaf_session2` cookie from your browser instead of the login window
  (hidden prompt or `OLSYNC_COOKIE`). Works without PySide6, e.g. on servers without a display (#80), on systems
  where PySide6 can't be installed such as Ubuntu 18.04 (#74), and for single sign-on accounts such as ORCID (#83).

### Fixed
- `ols download`: Overleaf rejected the compile request and served the PDF only with additional parameters (#83).
- Deleting files on Overleaf with `ols -l`: binary files (images, PDFs) were reported as deleted but stayed on
  Overleaf, and a same-named file in a parent folder could be deleted instead of a file in a missing subfolder (#77).
- When the login window can't be loaded (e.g. Qt conflicts with Anaconda on Windows), the real error is shown with
  a hint, instead of a misleading `No module named 'olbrowserlogin'` (#59).
- The `.olignore` notice was printed once per file instead of once per sync (#60).
- `.olignore` patterns starting with `./` never matched (#72).

## [2.0.0a1] - 2026-10-24

First pre-release of 2.0. Overleaf changed its website in ways that broke 1.2.0 for everyone; this release makes
syncing work again and puts the project on a tested footing.

### Fixed
- Listing and finding projects: Overleaf renamed the project list on its dashboard
  (#84 by @warnes; also reported in #32, #61, #63, #75, #83).
- Querying project details: the real-time handshake now needs the project id, a fresh load-balancer cookie and a
  new response event (#85 by @warnes).
- Uploading files: Overleaf now requires the file name as a separate form field (#85 by @warnes, #49, #77).
- Status checks in upload, delete and folder creation always reported failure (#85 by @warnes).
- Crash on Windows consoles with a legacy codepage when printing status symbols (#86 by @semihvazgecen).

### Changed
- **Breaking:** requires Python 3.11 or newer.
- **Breaking:** the login window (PySide6) is now an optional extra. Install with
  `pip install "overleaf-sync[gui]"`; without it, `ols login` explains how to install it.
- New `overleaf-sync` command as an alias for `ols`, in case another program named `ols` is on your PATH (#68).
- Modern packaging (`flit_core`, standard `[project]` metadata) (#79 by @takluyver).

### Added
- Test suite (unit tests, plus local-only smoke tests against overleaf.com) and CI on Linux, macOS and Windows.
- Automated releases to PyPI via Trusted Publishing.

### Thanks
Thanks also to everyone whose earlier pull requests worked on these problems while the project was unmaintained:
@NiklasPrahl (#82), @JINNMnm (#87), @e-zz (#70), @matevosashot (#73) and @svennniiii (#66).

## [1.2.0] - 2022-11-06

Last release before the 2.0 rework.

[Unreleased]: https://github.com/moritzgloeckl/overleaf-sync/compare/v2.0.0a4...HEAD
[2.0.0a4]: https://github.com/moritzgloeckl/overleaf-sync/compare/v2.0.0a3...v2.0.0a4
[2.0.0a3]: https://github.com/moritzgloeckl/overleaf-sync/compare/v2.0.0a2...v2.0.0a3
[2.0.0a2]: https://github.com/moritzgloeckl/overleaf-sync/compare/v2.0.0a1...v2.0.0a2
[2.0.0a1]: https://github.com/moritzgloeckl/overleaf-sync/compare/aa62165...v2.0.0a1
[1.2.0]: https://pypi.org/project/overleaf-sync/1.2.0/
