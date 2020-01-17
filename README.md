# Overleaf-Sync 1.0.3

### Easy Overleaf Two-Way Synchronization

![Made In Austria](https://img.shields.io/badge/Made%20in-Austria-%23ED2939.svg) ![PyPI - License](https://img.shields.io/pypi/l/overleaf-sync.svg) ![PyPI](https://img.shields.io/pypi/v/overleaf-sync.svg) ![PyPI - Python Version](https://img.shields.io/pypi/pyversions/overleaf-sync.svg)

This tool provides an easy way to synchronize Overleaf projects from and to your local computer. No paid account necessary.

----

## Features
- Sync your locally modified `.tex` (and other) files to your Overleaf projects
- Sync your remotely modified `.tex` (and other) files to computer
- Works with free Overleaf account
- No Git or Dropbox required
- Does not steal or store your login credentials (works with a persisted cookie, [check yourself](https://github.com/moritzgloeckl/overleaf-sync/blob/master/olsync/olclient.py#L34))

## How To Use
### Install
The package is available via PyPI. Just run:

```
moritz@github:~/test$ pip install overleaf-sync
```

That's it!

### Prerequisites
- Create your project on overleaf.com, for example `test`. The tool is not able to create projects (yet).
- Create a folder with the same name as the project (`test`) on your computer
- Execute the script from that folder (`test`)

### Usage
#### Login
```
moritz@github:~/test$ ols login [-u/--username -p/--pasword --path]
Username: <overleaf username>
Password: <overleaf password>
Login successful. Cookie persisted as `.olauth`. You may now sync your project.
```

You can either specify your username and/or password on the command line or you will be prompted to enter them. The `login` command logs you into Overleaf and stores your *cookie* (**not** your login credentials) in a hidden file called `.olauth` in the same folder you run the command from. It is possible to store the cookie elsewhere using the `--path` option. The cookie file will not be synced to or from Overleaf.

### Syncing
```
moritz@github:~/test$ ols [-l/--local-only -r/--remote-only --store-path -p/--path -i/--olignore]
```

Just calling `ols` will two-way sync your project. When there are changes both locally and remotely you will be asked which file to keep. Using the `-l` or `-r` option you can specify to either sync local project files to Overleaf only or Overleaf files to local ones only respectively. The option `--store-path` specifies the path of the cookie file created by the `login` command. If you did not change its path you do not need to specify this argument. The `-p/--path` option allows you to specify a different sync folder than the one you're calling `ols` from. The `-i/--olignore` option allows you to specify the path of `.olignore` file which works exactly like `.gitignore`.

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
- When syncing from local to remote, files (including the ones in sub-directories) will all be synced to the root directory under Overleaf project (i.e., if local files under different folder share a same name, only the last synced file will be on Overleaf).

## Disclaimer
THE AUTHOR OF THIS SOFTWARE AND THIS SOFTWARE IS NOT ENDORSED BY, DIRECTLY AFFILIATED WITH, MAINTAINED, AUTHORIZED, OR SPONSORED BY OVERLEAF OR WRITELATEX LIMITED. ALL PRODUCT AND COMPANY NAMES ARE THE REGISTERED TRADEMARKS OF THEIR ORIGINAL OWNERS. THE USE OF ANY TRADE NAME OR TRADEMARK IS FOR IDENTIFICATION AND REFERENCE PURPOSES ONLY AND DOES NOT IMPLY ANY ASSOCIATION WITH THE TRADEMARK HOLDER OF THEIR PRODUCT BRAND.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

THIS SOFTWARE WAS DESIGNED TO BE USED ONLY FOR RESEARCH PURPOSES. THIS SOFTWARE COMES WITH NO WARRANTIES OF ANY KIND WHATSOEVER. USE IT AT YOUR OWN RISK! IF THESE TERMS ARE NOT ACCEPTABLE, YOU AREN'T ALLOWED TO USE THE CODE.

