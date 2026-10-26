# Overleaf-Sync
### Easy Overleaf Two-Way Synchronization

![Made In Austria](https://img.shields.io/badge/Made%20in-Austria-%23ED2939.svg) ![PyPI - License](https://img.shields.io/pypi/l/overleaf-sync.svg) ![PyPI](https://img.shields.io/pypi/v/overleaf-sync.svg) ![PyPI - Python Version](https://img.shields.io/pypi/pyversions/overleaf-sync.svg)

Sync your Overleaf projects with a folder on your computer, in both directions. No paid Overleaf account, Git or Dropbox needed.

- Edit your `.tex` files (and figures, bibliographies, …) locally with any editor, then sync them to Overleaf
- Get the changes you or your co-authors made on Overleaf
- Changes on both sides are detected per file; **nothing is overwritten without asking**
- Works with free accounts on overleaf.com and with self-hosted Overleaf servers
- Never sees or stores your password: you log in on Overleaf's own login page, and only the session cookie is kept

----

## Installation

overleaf-sync needs Python 3.11 or newer and is available on [PyPI](https://pypi.org/project/overleaf-sync/):

```
pip install "overleaf-sync[gui]"
```

The `gui` extra installs the login window (Qt via PySide6). Without it, everything works except the login window; log in with [`ols login --cookie`](#login-without-the-login-window) instead. [pipx](https://pipx.pypa.io/) works too: `pipx install "overleaf-sync[gui]"`.

The command is called `ols`. If another program named `ols` is already on your `PATH`, use `overleaf-sync` instead; it is the same command.

## Quick start

1. Create the project on [Overleaf](https://www.overleaf.com/project), e.g. `thesis` (overleaf-sync can't create projects).
2. Create a folder with the same name and go there:
   ```
   mkdir thesis && cd thesis
   ```
3. Log in once (opens Overleaf's login page in a small window):
   ```
   ols login
   ```
4. Sync:
   ```
   ols
   ```

Run `ols` again whenever you want to sync. If the folder name differs from the project name, pass the project name with `-n "My Project"`.

## Logging in

```
ols login [--auth-file PATH] [--server URL] [--cookie]
```

`ols login` opens Overleaf's real login page in a small window. You log in there, as in a browser (including captchas), and your password goes directly to Overleaf. overleaf-sync then stores only the session cookie and the CSRF token in `.olauth` in the current folder. The file is readable only by you and is never synced to Overleaf. Use `--auth-file` to keep it somewhere else; all commands accept the same option.

Keep `.olauth` private: anyone with this file can access your Overleaf account until the session ends. To end it, use *Clear sessions* in your Overleaf account settings (if you logged in with `--cookie`, logging out in that browser works too).

### Login without the login window

On a server without a display, if PySide6 can't be installed (e.g. on older Linux distributions), or if the login window doesn't work for your account (e.g. single sign-on via ORCID or your institution), log in with the session cookie of your normal browser:

1. Log in to Overleaf in your browser.
2. Open the developer tools → *Application* (Firefox: *Storage*) → *Cookies* → `https://www.overleaf.com`, and copy the value of `overleaf_session2` (on a self-hosted server: `overleaf.sid`).
3. Run `ols login --cookie` and paste the value at the hidden prompt, or provide it in the `OLSYNC_COOKIE` environment variable.

This doesn't need the `gui` extra.

## Syncing

```
ols [-l | -r] [-n NAME] [-p PATH] [-i OLIGNORE] [--auth-file PATH] [--server URL] [-v]
```

| Option | Meaning |
|---|---|
| *(none)* | Two-way sync (see below) |
| `-l`, `--local-only` | Only sync local files to Overleaf |
| `-r`, `--remote-only` | Only sync files from Overleaf to the local folder |
| `-n`, `--name` | Project name, if it differs from the folder name |
| `-p`, `--path` | Sync folder, if it isn't the current folder |
| `-i`, `--olignore` | Path of the [`.olignore`](#excluding-files-olignore) file (default: `.olignore` in the sync folder) |
| `--auth-file` | Login file (default: `.olauth` in the current folder) |
| `--server` | [Self-hosted Overleaf server](#self-hosted-overleaf-servers) |
| `-v`, `--verbose` | Show details when something goes wrong |

**Two-way sync.** overleaf-sync remembers what every file looked like after the last sync, in `.olsync-state.json` in the sync folder (it stays local). That way it knows on which side a file changed:

- changed locally → uploaded to Overleaf
- changed on Overleaf → downloaded
- changed on both sides → you're asked whether to keep the local version, keep the Overleaf version, or skip the file (skipped files come up again next time)
- new files on either side are copied to the other side

On the very first sync there's no history yet, so you're asked about every file that differs between your folder and Overleaf.

**One-way sync (`-l`, `-r`).** These use the same history: a file is only overwritten without asking if the other side didn't change it since the last sync. They also handle files deleted on one side: you can delete them on the other side as well, restore them, or ignore them. (Two-way sync never deletes files.)

Example output of a two-way sync:

```
Syncing files between [local] and [remote]
========================================

[DOWNLOAD] Following file(s) downloaded from [remote]
	chapters/intro.tex

[UPLOAD] Following file(s) uploaded to [remote]
	chapters/results.tex
	main.tex

[SYNC] Following file(s) are up to date
	figures/plot.png

✅  Synced files between [local] and [remote]
```

### Excluding files (`.olignore`)

Put [`fnmatch`](https://docs.python.org/3/library/fnmatch.html) patterns, one per line, into a file called `.olignore` in the sync folder to keep local files off Overleaf, e.g. build output:

```
*.aux
*.log
out/*
```

To exclude a folder, use `folder/*` (not `folder/`). Patterns starting with `./` work too. Files and folders starting with a dot (like `.olauth`, `.olsync-state.json` or `.git`) are never uploaded.

## Other commands

**`ols list`** lists your projects, most recently changed first:

```
$ ols list
10/24/2026, 13:45:12 - thesis
09/21/2026, 01:23:45 - Paper draft
```

**`ols download`** compiles the project on Overleaf and saves the PDF (`--download-path` to choose the folder, `-n` for the project name).

## Self-hosted Overleaf servers

overleaf-sync works with self-hosted Overleaf servers too. It is tested against Overleaf Community Edition; Server Pro shares its code and should work as well, but is untested. Log in with the server's URL:

```
ols login --server https://overleaf.example.com
```

The server is stored with the login, so `ols`, `ols list` and `ols download` use it automatically. `--server` works on every command, and the `OLSYNC_SERVER` environment variable sets it too. For `ols login --cookie --server …`, copy the cookie `overleaf.sid` (`sharelatex.sid` on versions before 5).

## Troubleshooting

- **"Your Overleaf session has expired"**: sessions end after a while, or when they're cleared in your Overleaf account settings. Run `ols login` again.
- **"… was created by an older version of overleaf-sync"**: the login format changed in 2.0. Run `ols login` again.
- **"Overleaf's rate limit was reached"**: Overleaf limits how many requests you can make per minute (e.g. project downloads). overleaf-sync already waits and retries; if it still fails, wait a minute.
- **"Project could not be queried"**: check the project name (`ols list`), or pass it with `-n`.
- **The login window doesn't open or crashes**: Qt can conflict with other Qt installations (e.g. Anaconda's). Install overleaf-sync in a fresh virtual environment based on a non-conda Python, or use [`ols login --cookie`](#login-without-the-login-window).
- **`ols: no description file specified`** or other unexpected output: another program called `ols` is on your `PATH`. Use `overleaf-sync` instead.
- **A change you just made in Overleaf's web editor isn't picked up**: give Overleaf a moment to save it, then sync again.
- **Something else**: run the command with `-v` and [open an issue](https://github.com/moritzgloeckl/overleaf-sync/issues) with the output. overleaf-sync uses Overleaf's website like a browser does, not an official API, so changes on Overleaf's side can break it.

## Migrating from 1.x

- Python 3.11 or newer is required.
- Install with `pip install "overleaf-sync[gui]"`; the login window is now an optional extra.
- Run `ols login` once more: the login file is now stored in a safer format.
- `--store-path` is now called `--auth-file` (the old name still works for now, and `ols login --path` too).
- The first two-way sync asks about every file that differs between your folder and Overleaf, because there's no sync history yet. After that, only real conflicts are asked about.

## Contributing

Pull requests and issues are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for the development setup and the tests, and [CHANGELOG.md](CHANGELOG.md) for what changed.

## Disclaimer
THE AUTHOR OF THIS SOFTWARE AND THIS SOFTWARE IS NOT ENDORSED BY, DIRECTLY AFFILIATED WITH, MAINTAINED, AUTHORIZED, OR SPONSORED BY OVERLEAF OR WRITELATEX LIMITED. ALL PRODUCT AND COMPANY NAMES ARE THE REGISTERED TRADEMARKS OF THEIR ORIGINAL OWNERS. THE USE OF ANY TRADE NAME OR TRADEMARK IS FOR IDENTIFICATION AND REFERENCE PURPOSES ONLY AND DOES NOT IMPLY ANY ASSOCIATION WITH THE TRADEMARK HOLDER OF THEIR PRODUCT BRAND.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

THIS SOFTWARE WAS DESIGNED TO BE USED ONLY FOR RESEARCH PURPOSES. THIS SOFTWARE COMES WITH NO WARRANTIES OF ANY KIND WHATSOEVER. USE IT AT YOUR OWN RISK! IF THESE TERMS ARE NOT ACCEPTABLE, YOU AREN'T ALLOWED TO USE THE CODE.
