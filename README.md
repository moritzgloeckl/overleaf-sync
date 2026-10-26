# Overleaf-Sync
### Easy Overleaf Two-Way Synchronization

![Made In Austria](https://img.shields.io/badge/Made%20in-Austria-%23ED2939.svg) ![PyPI - License](https://img.shields.io/pypi/l/overleaf-sync.svg) ![PyPI](https://img.shields.io/pypi/v/overleaf-sync.svg) ![PyPI - Python Version](https://img.shields.io/pypi/pyversions/overleaf-sync.svg)

This tool provides an easy way to synchronize Overleaf projects from and to your local computer. No paid account necessary.

----

## Features
- Sync your locally modified `.tex` (and other) files to your Overleaf projects
- Sync your remotely modified `.tex` (and other) files to computer
- Works with free Overleaf account
- No Git or Dropbox required
- Does not steal or store your login credentials (works with a persisted cookie, logging in is done on the original Overleaf website)

## How To Use
### Install
The package is available via [PyPI](https://pypi.org/project/overleaf-sync/) and needs Python 3.11 or newer. Install it including the login window (`gui` extra):

```
moritz@github:~/test$ pip3 install "overleaf-sync[gui]"
```

Depending on your local Python installation, you might need to use `pip` instead of `pip3`. [pipx](https://pipx.pypa.io/) works too: `pipx install "overleaf-sync[gui]"`.

> **2.0 pre-release:** Overleaf changed its website in a way that broke version 1.2.0. The fixes are available as a pre-release: `pip3 install --pre "overleaf-sync[gui]"`. Please report any problems in the [issues](https://github.com/moritzgloeckl/overleaf-sync/issues).

### Prerequisites
- Create your project on [Overleaf](https://www.overleaf.com/project), for example a project named `test`. Overleaf-sync is not able to create projects (yet).
- Create a folder, preferably with the same name as the project (`test`) on your computer.
- Execute the script from that folder (`test`).
- If you do not specify the project name, overleaf-sync uses the current folder's name as the project name.

### Usage
#### Login
```
moritz@github:~/test$ ols login [--auth-file PATH]
Login successful. Cookie persisted as `.olauth`. You may now sync your project.
```

Logging in will be handled by a mini web browser opening on your device (using Qt via PySide6, from the `gui` extra). You can then enter your username and password securely on the official Overleaf website. You might get asked to solve a CAPTCHA in the process. Your credentials are sent to Overleaf over HTTPS.

It then stores your session *cookie* (**not** your login credentials) in a hidden file called `.olauth` in the same folder you run the command from, readable only by you. It is possible to store it elsewhere using the `--auth-file` option. The file will not be synced to or from Overleaf.

Keep the `.olauth` file safe, as it can be used to log in to your account. Logins created by 2.0.0a4 or earlier use an older format; overleaf-sync asks you to run `ols login` again.

#### Login without the login window
On a server without a display, or if the login window doesn't work for your account (e.g. single sign-on via ORCID or your institution), log in with a session cookie instead:

1. Log in to Overleaf in your normal browser.
2. Open the developer tools → Application (Firefox: Storage) → Cookies → `https://www.overleaf.com` and copy the value of `overleaf_session2` (on a self-hosted server: the cookie `overleaf.sid` of your server).
3. Run `ols login --cookie` and paste the value at the (hidden) prompt, or provide it via the `OLSYNC_COOKIE` environment variable.

This works without installing the `gui` extra.

### Self-hosted Overleaf servers
overleaf-sync also works with self-hosted Overleaf servers. It is tested against Overleaf Community Edition; Server Pro shares its code and should work too, but is untested. Pass the server's URL when logging in:

```
moritz@github:~/test$ ols login --server https://overleaf.example.com
```

The server is stored together with the login, so all other commands (`ols`, `ols list`, `ols download`) use it automatically. You can also set it with `--server` on any command or with the `OLSYNC_SERVER` environment variable. `ols login --cookie --server ...` works too; self-hosted servers name the session cookie `overleaf.sid` (`sharelatex.sid` before version 5).

### Listing all projects
```
moritz@github:~/test$ ols list [--auth-file PATH -v/--verbose]
10/31/2021, 01:23:45 - Project A
09/21/2020, 01:23:45 - Project B
08/11/2019, 01:23:45 - Project C
07/01/2018, 01:23:45 - Project D
```

Use `ols list` to conveniently list all projects in your account available for syncing. 

### Downloading project's PDF
```
moritz@github:~/test$ ols download [--name --download-path --auth-file PATH -v/--verbose]
```

Use `ols download` to compile and download your project's PDF. Specify a download path if you do not want to store the PDF file in the current folder. Currently only downloads the first PDF file it finds.

### Syncing
```
moritz@github:~/test$ ols [-l/--local-only -r/--remote-only --auth-file PATH -p/--path -i/--olignore]
```

Just calling `ols` will two-way sync your project. overleaf-sync remembers what each file looked like after the last sync (in a local `.olsync-state.json` file, which is never uploaded), so it knows on which side a file changed: files changed locally are uploaded, files changed on Overleaf are downloaded. If a file was changed on both sides, or differs on the first sync, you are asked which version to keep (or to skip it). Nothing is overwritten silently.

Using the `-l` or `-r` option you can specify to either sync local project files to Overleaf only or Overleaf files to local ones only respectively. They use the same sync history: a file that was changed on the target side since the last sync (or has no history yet) is only overwritten after asking. When using these options you can also sync deleted files. If a file has been deleted it can either be deleted on the target (remote when `-l`, local when `-r`) as well, restored on the source (local when `-l`, remote when `-r`) or ignored.

The option `--auth-file` specifies the path of the login file created by the `login` command (`--store-path` still works but is deprecated). If you did not change its path, you do not need to specify this argument. The `-p/--path` option allows you to specify a different sync folder than the one you're calling `ols` from. The `-i/--olignore` option allows you to specify the path of an `.olignore` file. It uses `fnmatch` internally, so it may have some similarity to `.gitignore` but doesn't work exactly the same. For example, if you wish to exclude a specific folder named `out`, you need to specify it as `out/*`. See [here](https://docs.python.org/3/library/fnmatch.html) for more information.

Sample Output:

```
Project queried successfully.
✅  Querying project
Project downloaded successfully.
✅  Downloading project

Syncing files from remote to local
====================

[SYNCING] report.tex
report.tex does not exist on local. Creating file.

[SYNCING] other-report.tex
other-report.tex does not exist on local. Creating file.


✅  Syncing files from remote to local
```

## Known Bugs
- When modifying a file on Overleaf and immediately syncing afterwards, the tool might not detect the changes. Please allow 1-2 minutes after modifying a file on Overleaf before syncing it to your local computer.

## Contributing

All pull requests and change/feature requests are welcome.

## Disclaimer
THE AUTHOR OF THIS SOFTWARE AND THIS SOFTWARE IS NOT ENDORSED BY, DIRECTLY AFFILIATED WITH, MAINTAINED, AUTHORIZED, OR SPONSORED BY OVERLEAF OR WRITELATEX LIMITED. ALL PRODUCT AND COMPANY NAMES ARE THE REGISTERED TRADEMARKS OF THEIR ORIGINAL OWNERS. THE USE OF ANY TRADE NAME OR TRADEMARK IS FOR IDENTIFICATION AND REFERENCE PURPOSES ONLY AND DOES NOT IMPLY ANY ASSOCIATION WITH THE TRADEMARK HOLDER OF THEIR PRODUCT BRAND.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

THIS SOFTWARE WAS DESIGNED TO BE USED ONLY FOR RESEARCH PURPOSES. THIS SOFTWARE COMES WITH NO WARRANTIES OF ANY KIND WHATSOEVER. USE IT AT YOUR OWN RISK! IF THESE TERMS ARE NOT ACCEPTABLE, YOU AREN'T ALLOWED TO USE THE CODE.

