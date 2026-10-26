# Releasing overleaf-sync

Releases are built and published by GitHub Actions (`.github/workflows/release.yml`) when a version tag is pushed. Publishing to PyPI uses [Trusted Publishing](https://docs.pypi.org/trusted-publishers/), so there is no API token anywhere, and every upload waits for the maintainer's approval.

## Versions

Versions follow [PEP 440](https://peps.python.org/pep-0440/) and live only in `olsync/__init__.py` (`__version__`). Tags are the version with a `v` in front:

| Kind | Version | Tag | Installed by |
|---|---|---|---|
| Pre-release | `2.1.0a1`, `2.1.0b1`, `2.1.0rc1` | `v2.1.0rc1` | `pip install --pre overleaf-sync` |
| Release | `2.1.0` | `v2.1.0` | `pip install overleaf-sync` |

## Step by step

1. **Everything is merged and green.** All PRs for the release are merged into `master` with *merge commits*, and the latest CI run on `master` passed, including the integration job.

2. **Run the smoke tests locally** against overleaf.com (see [CONTRIBUTING.md](CONTRIBUTING.md#tests)):
   ```bash
   pytest -m smoke -v
   ```
   They're the only tests that talk to the real overleaf.com. Don't release if they fail.

3. **Open a release PR** from a branch like `release-2.1.0`:
   - set `__version__` in `olsync/__init__.py`
   - in `CHANGELOG.md`, rename `## [Unreleased]` to `## [2.1.0] - YYYY-MM-DD`, add a one-line summary, and add the compare link at the bottom (`[2.1.0]: https://github.com/moritzgloeckl/overleaf-sync/compare/v2.0.0...v2.1.0`)
   - check the package locally:
     ```bash
     python -m build && twine check --strict dist/*
     ```
   Wait for CI, then merge it with a merge commit.

4. **Tag the merge commit and push the tag:**
   ```bash
   git checkout master && git pull
   git tag -a v2.1.0 -m "overleaf-sync 2.1.0"
   git push origin v2.1.0
   ```

5. **Approve the upload.** The *Release* workflow checks that the tag matches `__version__`, builds the package and runs `twine check`. Then it waits: open the run in the *Actions* tab → *Review deployments* → `pypi` → *Approve and deploy*. (The `pypi` environment only accepts `v*` tags and requires the maintainer's approval.)

6. **The workflow publishes** to PyPI and creates a GitHub Release with generated notes and the built files. `a`/`b`/`rc` versions are marked as pre-releases.

7. **Check the published package** in a fresh environment (PyPI's index can take a minute to update):
   ```bash
   python3 -m venv /tmp/check && /tmp/check/bin/pip install "overleaf-sync==2.1.0"   # add --pre for pre-releases
   /tmp/check/bin/ols --version
   ```

8. **Tell users:** comment on the issues the release fixes (with the install command), and update the pinned announcement issue if there is one.

## Trying the workflow without releasing (TestPyPI)

*Actions* → *Release* → *Run workflow* builds the current `master` and uploads it to [TestPyPI](https://test.pypi.org/project/overleaf-sync/) after approval in the `testpypi` environment. TestPyPI refuses versions it already has, so this only works for a version that wasn't uploaded there before (e.g. a `.devN` version).

To install from TestPyPI, take only overleaf-sync from there and its dependencies from PyPI:

```bash
pip install --no-deps --index-url https://test.pypi.org/simple/ overleaf-sync==2.1.0.dev1
pip install requests beautifulsoup4 yaspin click
```

Avoid `--extra-index-url https://test.pypi.org/simple/`: anyone can upload packages to TestPyPI, so dependencies could be resolved from there (dependency confusion).

## Fixing a broken release

PyPI never lets you upload the same version twice, so don't delete a release to fix it.

- **Yank it:** pypi.org → *overleaf-sync* → *Manage* → *Releases* → the version → *Options* → *Yank*. pip then no longer installs it unless asked for exactly that version.
- **Release a fix** as the next patch version (e.g. `2.1.1`), following the steps above. For an urgent fix on top of a release, branch from its tag (`git checkout -b hotfix-2.1.1 v2.1.0`), open the PR against `master`, and release from `master` as usual.

## One-time setup (already done)

For reference, in case it has to be redone:

- **PyPI** → *overleaf-sync* → *Publishing*: GitHub publisher for `moritzgloeckl/overleaf-sync`, workflow `release.yml`, environment `pypi`. The same on **TestPyPI** with environment `testpypi`.
- **GitHub** → *Settings* → *Environments*: `pypi` (required reviewer: the maintainer; deployment tags: `v*`) and `testpypi` (required reviewer).
