# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/).

## [2.0.0a1] - unreleased

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

[2.0.0a1]: https://github.com/moritzgloeckl/overleaf-sync/compare/aa62165...v2.0.0a1
[1.2.0]: https://pypi.org/project/overleaf-sync/1.2.0/
