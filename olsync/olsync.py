"""Overleaf Two-Way Sync Tool"""
##################################################
# MIT License
##################################################
# File: olsync.py
# Description: Overleaf Two-Way Sync
# Author: Moritz Glöckl
# License: MIT
##################################################

import click
from datetime import datetime
import os
import sys
from yaspin import yaspin
import zipfile
import io
import glob
import fnmatch
import traceback
from pathlib import Path

try:
    # Import for pip installation / wheel
    from olsync.olclient import BASE_URL, OverleafClient, RateLimitError, SessionExpiredError
    from olsync import auth, syncstate
except ImportError:
    # Import for development
    from olclient import BASE_URL, OverleafClient, RateLimitError, SessionExpiredError
    import auth
    import syncstate

# Session cookie names: overleaf.com, and self-hosted servers (Community Edition, "sharelatex.sid" before version 5)
OVERLEAF_COM_SESSION_COOKIES = ["overleaf_session2"]
SELF_HOSTED_SESSION_COOKIES = ["overleaf.sid", "sharelatex.sid"]

server_option = click.option(
    "--server",
    "server",
    default=None,
    envvar="OLSYNC_SERVER",
    metavar="URL",
    help="URL of a self-hosted Overleaf server (default: the server used at login, or https://www.overleaf.com). "
    "Can also be set with OLSYNC_SERVER.",
)

DEFAULT_AUTH_FILE = ".olauth"


def auth_file_options(legacy_name):
    """
    --auth-file, plus the option name used before 2.0 (--store-path, or --path for login) as a hidden, deprecated alias
    """

    def decorator(f):
        f = click.option(legacy_name, "legacy_auth_file", default=None, hidden=True, type=click.Path(exists=False))(f)
        return click.option(
            "--auth-file",
            "auth_file",
            default=None,
            type=click.Path(exists=False),
            metavar="PATH",
            help=f"Path of the persisted Overleaf login (default: {DEFAULT_AUTH_FILE} in the current directory).",
        )(f)

    return decorator


def resolve_auth_file(ctx, auth_file, legacy_auth_file, legacy_name):
    """--auth-file of the command, else of the group (`ols --auth-file X list`), else the default"""
    root = ctx.find_root()
    candidates = [(auth_file, legacy_auth_file, legacy_name)]
    if root is not ctx:
        candidates.append((root.params.get("auth_file"), root.params.get("legacy_auth_file"), "--store-path"))
    for new, legacy, name in candidates:
        if legacy:
            click.echo(f"Warning: {name} is deprecated, use --auth-file instead.", err=True)
        if new or legacy:
            return new or legacy
    return DEFAULT_AUTH_FILE


def configure_console():
    """
    Windows consoles often default to a legacy codepage (e.g. cp1252) that can't
    encode the emoji/braille characters used for status output and the spinner,
    which crashes stdout.write() with UnicodeEncodeError. Force UTF-8 output.
    Done when the CLI starts rather than on import, so importing olsync has no side effects.
    """
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


@click.group(invoke_without_command=True)
@click.option("-l", "--local-only", "local", is_flag=True, help="Sync local project files to Overleaf only.")
@click.option(
    "-r",
    "--remote-only",
    "remote",
    is_flag=True,
    help="Sync remote project files from Overleaf to local file system only.",
)
@click.option(
    "-n",
    "--name",
    "project_name",
    default="",
    help="Specify the Overleaf project name instead of the default name of the sync directory.",
)
@auth_file_options("--store-path")
@click.option(
    "-p", "--path", "sync_path", default=".", type=click.Path(exists=True), help="Path of the project to sync."
)
@click.option(
    "-i",
    "--olignore",
    "olignore_path",
    default=".olignore",
    type=click.Path(exists=False),
    help="Path to the .olignore file (relative to the sync path): fnmatch patterns of local files that are never "
    "uploaded, e.g. `*.log` or `out/*`.",
)
@server_option
@click.option("-v", "--verbose", "verbose", is_flag=True, help="Enable extended error logging.")
@click.version_option(package_name="overleaf-sync")
@click.pass_context
def main(ctx, local, remote, project_name, auth_file, legacy_auth_file, sync_path, olignore_path, server, verbose):
    """
    Sync an Overleaf project with the current folder (or --path). Without -l/-r, changes on both sides are synced, and
    you're asked before anything that was changed on both sides is overwritten.
    """
    configure_console()
    if ctx.invoked_subcommand is None:
        overleaf_client = load_client(resolve_auth_file(ctx, auth_file, legacy_auth_file, "--store-path"), server)

        # Change the current directory to the specified sync path
        os.chdir(sync_path)

        project_name = project_name or os.path.basename(os.getcwd())
        project = execute_action(
            lambda: overleaf_client.get_project(project_name),
            "Querying project",
            "Project queried successfully.",
            "Project could not be queried.",
            verbose,
        )

        project_infos = execute_action(
            lambda: overleaf_client.get_project_infos(project["id"]),
            "Querying project details",
            "Project details queried successfully.",
            "Project details could not be queried.",
            verbose,
        )

        zip_file = execute_action(
            lambda: zipfile.ZipFile(io.BytesIO(overleaf_client.download_project(project["id"]))),
            "Downloading project",
            "Project downloaded successfully.",
            "Project could not be downloaded.",
            verbose,
        )

        if not (local or remote):
            two_way_sync(overleaf_client, project, project_infos, zip_file, olignore_path, verbose)
            return

        sync = False  # -l and -r below sync in one direction only
        state = syncstate.load_state(".", overleaf_client.base_url, project["id"])

        if remote:
            remote_files = zip_file.namelist()
            deleted_files = [] if sync else [f for f in olignore_keep_list(olignore_path) if f not in remote_files]
            written = sync_func(
                files_from=remote_files,
                deleted_files=deleted_files,
                create_file_at_to=lambda name: write_file(name, zip_file.read(name)),
                delete_file_at_to=lambda name: delete_file(name),
                create_file_at_from=lambda name: upload_file(overleaf_client, project, project_infos, name),
                from_exists_in_to=lambda name: os.path.isfile(name),
                from_equal_to_to=lambda name: open(name, "rb").read() == zip_file.read(name),
                to_unchanged_since_last_sync=lambda name: unchanged_since_last_sync(
                    state, name, "local", read_file(name)
                ),
                from_name="remote",
                to_name="local",
                verbose=verbose,
            )
            record_state(overleaf_client, project, zip_file, state, written["to"], uploaded=bool(written["from"]))
        if local:
            # Computed once (#60)
            local_files = olignore_keep_list(olignore_path)
            deleted_files = [] if sync else [f for f in zip_file.namelist() if f not in local_files]
            written = sync_func(
                files_from=local_files,
                deleted_files=deleted_files,
                create_file_at_to=lambda name: upload_file(overleaf_client, project, project_infos, name),
                delete_file_at_to=lambda name: overleaf_client.delete_file(project["id"], project_infos, name),
                create_file_at_from=lambda name: write_file(name, zip_file.read(name)),
                from_exists_in_to=lambda name: name in zip_file.namelist(),
                from_equal_to_to=lambda name: open(name, "rb").read() == zip_file.read(name),
                to_unchanged_since_last_sync=lambda name: unchanged_since_last_sync(
                    state, name, "remote", zip_file.read(name)
                ),
                from_name="local",
                to_name="remote",
                verbose=verbose,
            )
            record_state(overleaf_client, project, zip_file, state, written["to"], uploaded=bool(written["to"]))


@main.command()
@auth_file_options("--path")
@click.option(
    "--cookie",
    "use_cookie",
    is_flag=True,
    help="Log in without the login window, using the session cookie from a browser that is logged in to "
    "Overleaf (`overleaf_session2` on overleaf.com, `overleaf.sid` on self-hosted servers), asked for "
    "at a hidden prompt or read from OLSYNC_COOKIE. Useful on servers without a display and for single "
    "sign-on accounts.",
)
@server_option
@click.option("-v", "--verbose", "verbose", is_flag=True, help="Enable extended error logging.")
@click.pass_context
def login(ctx, auth_file, legacy_auth_file, use_cookie, server, verbose):
    """Log in to Overleaf and store the session for the other commands."""
    server = resolve_login_server(ctx, server)
    cookie_path = resolve_auth_file(ctx, auth_file, legacy_auth_file, "--path")
    if os.path.isfile(cookie_path) and not click.confirm(
        "Persisted Overleaf cookie already exist. Do you want to override it?"
    ):
        return
    if use_cookie:
        cookie_names = OVERLEAF_COM_SESSION_COOKIES if server == BASE_URL else SELF_HOSTED_SESSION_COOKIES
        # Never accept the cookie as a command line argument, it would end up in the shell history
        cookie = os.environ.get("OLSYNC_COOKIE") or click.prompt(
            f"Value of the {cookie_names[0]} cookie", hide_input=True
        )
        execute_action(
            lambda: cookie_login_handler(cookie.strip(), cookie_path, server, cookie_names),
            "Login",
            "Login successful. Cookie persisted as `"
            + click.format_filename(cookie_path)
            + "`. You may now sync your project.",
            "Login failed: the cookie is not valid (expired, or copied incompletely).",
            verbose,
        )
        return
    olbrowserlogin = load_browser_login()
    click.clear()
    execute_action(
        lambda: login_handler(olbrowserlogin, cookie_path, server),
        "Login",
        "Login successful. Cookie persisted as `"
        + click.format_filename(cookie_path)
        + "`. You may now sync your project.",
        "Login failed. Please try again.",
        verbose,
    )


@main.command(name="list")
@auth_file_options("--store-path")
@server_option
@click.option("-v", "--verbose", "verbose", is_flag=True, help="Enable extended error logging.")
@click.pass_context
def list_projects(ctx, auth_file, legacy_auth_file, server, verbose):
    """List your Overleaf projects, most recently changed first."""

    def query_projects():
        for index, p in enumerate(sorted(overleaf_client.all_projects(), key=lambda x: x["lastUpdated"], reverse=True)):
            if not index:
                click.echo("\n")
            click.echo(f"{datetime.fromisoformat(p['lastUpdated']).strftime('%m/%d/%Y, %H:%M:%S')} - {p['name']}")
        return True

    overleaf_client = load_client(
        resolve_auth_file(ctx, auth_file, legacy_auth_file, "--store-path"),
        server or ctx.find_root().params.get("server"),
    )

    click.clear()
    execute_action(
        query_projects,
        "Querying all projects",
        "Querying all projects successful.",
        "Querying all projects failed. Please try again.",
        verbose,
    )


@main.command(name="download")
@click.option(
    "-n",
    "--name",
    "project_name",
    default="",
    help="Specify the Overleaf project name instead of the default name of the sync directory.",
)
@click.option(
    "--download-path",
    "download_path",
    default=".",
    type=click.Path(exists=True),
    help="Folder to save the PDF in (default: the current folder).",
)
@auth_file_options("--store-path")
@server_option
@click.option("-v", "--verbose", "verbose", is_flag=True, help="Enable extended error logging.")
@click.pass_context
def download_pdf(ctx, project_name, download_path, auth_file, legacy_auth_file, server, verbose):
    """Compile the project on Overleaf and download the PDF."""

    def download_project_pdf():
        nonlocal project_name
        project_name = project_name or os.path.basename(os.getcwd())
        project = execute_action(
            lambda: overleaf_client.get_project(project_name),
            "Querying project",
            "Project queried successfully.",
            "Project could not be queried.",
            verbose,
        )

        file_name, content = overleaf_client.download_pdf(project["id"])

        if file_name and content:
            # Change the current directory to the specified sync path
            os.chdir(download_path)
            open(file_name, "wb").write(content)

        return True

    overleaf_client = load_client(
        resolve_auth_file(ctx, auth_file, legacy_auth_file, "--store-path"),
        server or ctx.find_root().params.get("server"),
    )

    click.clear()

    execute_action(
        download_project_pdf,
        "Downloading project's PDF",
        "Downloading project's PDF successful.",
        "Downloading project's PDF failed. Please try again.",
        verbose,
    )


def load_browser_login():
    """
    Import the login window module. PySide6 is an optional dependency (the "gui" extra),
    so it is only imported when logging in.
    """
    try:
        try:
            # Import for pip installation / wheel
            import olsync.olbrowserlogin as olbrowserlogin
        except ImportError as e:
            if not (e.name or "").startswith("olsync"):
                raise
            # Import for development (running olsync.py from inside the olsync folder)
            import olbrowserlogin
    except ImportError as e:
        if (e.name or "").startswith("PySide6"):
            raise click.ClickException(
                'The login window needs PySide6. Install it with: pip install "overleaf-sync[gui]"\n'
                "Alternatively, log in without the window: ols login --cookie"
            )
        # PySide6 is installed but can't be loaded, e.g. because another Qt installation (such as Anaconda's)
        # conflicts with it (#59)
        raise click.ClickException(
            f"The login window could not be loaded: {e}\n"
            "This usually means another Qt installation (e.g. from Anaconda) conflicts with PySide6. Installing "
            "overleaf-sync into a fresh virtual environment based on a non-conda Python usually helps.\n"
            "Alternatively, log in without the window: ols login --cookie"
        )
    return olbrowserlogin


def resolve_login_server(ctx, server):
    """--server on the login command, else on the group (both also read OLSYNC_SERVER), else overleaf.com"""
    return (server or ctx.find_root().params.get("server") or BASE_URL).rstrip("/")


def load_client(cookie_path, server=None):
    """
    Create an OverleafClient from the persisted login. The server is --server/OLSYNC_SERVER if given, otherwise the
    server stored at login.
    """
    try:
        login = auth.load_auth(cookie_path)
    except auth.AuthFileError as e:
        raise click.ClickException(str(e))
    return OverleafClient(login["cookies"], login["csrf"], base_url=server or login["server"])


def login_handler(olbrowserlogin, path, server):
    store = olbrowserlogin.login(server)
    if store is None:
        return False
    auth.save_auth(path, store["cookie"], store["csrf"], server)
    return True


def cookie_login_handler(cookie, path, server, cookie_names):
    # Self-hosted servers name the session cookie differently depending on the version, so try each name
    for cookie_name in cookie_names:
        cookies = {cookie_name: cookie}
        csrf = OverleafClient(cookies, base_url=server).fetch_csrf()
        if csrf is not None:
            auth.save_auth(path, cookies, csrf, server)
            return True
    return False


def delete_file(path):
    _dir = os.path.dirname(path)
    if _dir == path:
        return

    if _dir != "" and not os.path.exists(_dir):
        return
    else:
        os.remove(path)


def upload_file(overleaf_client, project, project_infos, path):
    """Upload a local file; raise if Overleaf rejects it, so a failed upload is neither reported nor recorded as synced"""
    with open(path, "rb") as f:
        if not overleaf_client.upload_file(project["id"], project_infos, path, os.path.getsize(path), f):
            raise IOError("Overleaf rejected the upload of %s" % path)


def write_file(path, content):
    _dir = os.path.dirname(path)
    if _dir == path:
        return

    # path is a file
    if _dir != "" and not os.path.exists(_dir):
        os.makedirs(_dir)

    with open(path, "wb+") as f:
        f.write(content)


def read_file(path):
    with open(path, "rb") as f:
        return f.read()


def unchanged_since_last_sync(state, path, side, content):
    """True if `side` ("local" or "remote") of `path` still has the content recorded at the last sync"""
    return state.get(path, {}).get(side) == syncstate.file_hash(content)


def record_state(overleaf_client, project, zip_file, state, synced, uploaded):
    """
    Record the sync state after a one-way sync (-l/-r): files that were synced, or are identical on both sides, get
    their current hashes; other files (e.g. skipped ones) keep their previous state. After uploads, the project is read
    again, so that Overleaf's own changes to uploaded files are not mistaken for remote edits later.
    """
    remote_zip = zip_file
    if uploaded:
        try:
            remote_zip = zipfile.ZipFile(io.BytesIO(overleaf_client.download_project(project["id"])))
        except Exception:
            remote_zip = zip_file
    remote_content = {name: remote_zip.read(name) for name in remote_zip.namelist() if not name.endswith("/")}
    new_state = {}
    for path in sorted(set(remote_content) | set(state)):
        on_both_sides = path in remote_content and os.path.isfile(path)
        if on_both_sides:
            local = read_file(path)
            if path in synced or local == remote_content[path]:
                new_state[path] = {
                    "local": syncstate.file_hash(local),
                    "remote": syncstate.file_hash(remote_content[path]),
                }
                continue
        if path in state and (on_both_sides or path in remote_content or os.path.isfile(path)):
            new_state[path] = state[path]
    syncstate.save_state(".", overleaf_client.base_url, project["id"], new_state)


def two_way_sync(overleaf_client, project, project_infos, zip_file, olignore_path, verbose=False):
    """
    Two-way sync that decides per file, based on the state of the last sync (see syncstate.py), instead of the
    project-wide lastUpdated timestamp. Changes on one side are synced; files changed on both sides, or differing
    without sync history, are only overwritten after asking.
    """

    def read(path):
        with open(path, "rb") as f:
            return f.read()

    server = overleaf_client.base_url
    remote_content = {name: zip_file.read(name) for name in zip_file.namelist() if not name.endswith("/")}
    # Local candidates: files allowed by .olignore, plus local copies of remote files (to compare them)
    local_paths = set(olignore_keep_list(olignore_path)) | {name for name in remote_content if os.path.isfile(name)}
    local = {path: syncstate.file_hash(read(path)) for path in local_paths}
    remote = {name: syncstate.file_hash(content) for name, content in remote_content.items()}
    state = syncstate.load_state(".", server, project["id"])
    plan = syncstate.plan_two_way(local, remote, state)

    click.echo("\nSyncing files between [local] and [remote]")
    click.echo("=" * 40)

    downloads, uploads, skipped = list(plan["download"]), list(plan["upload"]), []
    for path in plan["conflict"]:
        reason = (
            "was changed locally and on Overleaf since the last sync"
            if path in state
            else "differs between local and Overleaf, and there is no sync history for it yet"
        )
        choice = click.prompt(
            "\n-> Conflict: <%s> %s.\nKeep the [l]ocal version, keep the [r]emote version or [s]kip?" % (path, reason),
            default="s",
            type=click.Choice(["l", "r", "s"]),
        )
        {"l": uploads, "r": downloads, "s": skipped}[choice].append(path)

    failed = []
    for path in downloads:
        try:
            write_file(path, remote_content[path])
        except OSError:
            if verbose:
                print(traceback.format_exc())
            failed.append(path)
    for path in uploads:
        try:
            with open(path, "rb") as f:
                ok = overleaf_client.upload_file(project["id"], project_infos, path, os.path.getsize(path), f)
        except Exception:
            if verbose:
                print(traceback.format_exc())
            ok = False
        if not ok:
            failed.append(path)

    for title, paths in [
        ("[DOWNLOAD] Following file(s) downloaded from [remote]", downloads),
        ("[UPLOAD] Following file(s) uploaded to [remote]", uploads),
        ("[SYNC] Following file(s) are up to date", plan["in_sync"]),
        ("[SKIP] Following conflicting file(s) have not been synced", skipped),
        ("[ERROR] Following file(s) could not be synced", failed),
    ]:
        if paths:
            click.echo("\n" + title)
            for path in paths:
                click.echo("\t%s" % path)

    # Record what both sides look like now. After uploads, read the project again, so that changes Overleaf makes
    # to uploaded files (e.g. line endings) are not mistaken for remote edits next time.
    if set(uploads) - set(failed):
        try:
            fresh = zipfile.ZipFile(io.BytesIO(overleaf_client.download_project(project["id"])))
            remote_content = {name: fresh.read(name) for name in fresh.namelist() if not name.endswith("/")}
        except Exception:
            if verbose:
                print(traceback.format_exc())
            for path in set(uploads) - set(failed):
                remote_content[path] = read(path)
    new_state = {}
    for path in sorted(set(local_paths) | set(remote_content) | set(downloads)):
        if path in skipped or path in failed:
            if path in state:
                new_state[path] = state[path]
        elif path in remote_content and os.path.isfile(path):
            new_state[path] = {
                "local": syncstate.file_hash(read(path)),
                "remote": syncstate.file_hash(remote_content[path]),
            }
    syncstate.save_state(".", server, project["id"], new_state)

    click.echo("")
    if failed:
        raise click.ClickException("%d file(s) could not be synced, see above" % len(failed))
    click.echo("✅  Synced files between [local] and [remote]")
    click.echo("")


def sync_func(
    files_from,
    deleted_files,
    create_file_at_to,
    delete_file_at_to,
    create_file_at_from,
    from_exists_in_to,
    from_equal_to_to,
    to_unchanged_since_last_sync,
    from_name,
    to_name,
    verbose=False,
):
    click.echo("\nSyncing files from [%s] to [%s]" % (from_name, to_name))
    click.echo("=" * 40)

    newly_add_list = []
    update_list = []
    delete_list = []
    restore_list = []
    not_restored_list = []
    not_sync_list = []
    synced_list = []

    for name in files_from:
        if from_exists_in_to(name):
            if not from_equal_to_to(name):
                if not to_unchanged_since_last_sync(name) and not click.confirm(
                    "\n-> Warning: file <%s> was changed on [%s] since the last sync (or there is no sync history for "
                    "it yet).\nOverwrite it with the version from [%s]?" % (name, to_name, from_name)
                ):
                    not_sync_list.append(name)
                    continue

                update_list.append(name)
            else:
                synced_list.append(name)
        else:
            newly_add_list.append(name)

    for name in deleted_files:
        delete_choice = click.prompt(
            "\n-> Warning: file <%s> does not exist on [%s] anymore (but it still exists on [%s])."
            "\nShould the file be [d]eleted, [r]estored or [i]gnored?" % (name, from_name, to_name),
            default="i",
            type=click.Choice(["d", "r", "i"]),
        )
        if delete_choice == "d":
            delete_list.append(name)
        elif delete_choice == "r":
            restore_list.append(name)
        elif delete_choice == "i":
            not_restored_list.append(name)

    click.echo("\n[NEW] Following new file(s) created on [%s]" % to_name)
    for name in newly_add_list:
        click.echo("\t%s" % name)
        try:
            create_file_at_to(name)
        except:
            if verbose:
                print(traceback.format_exc())
            raise click.ClickException("\n[ERROR] An error occurred while creating new file(s) on [%s]" % to_name)

    click.echo("\n[NEW] Following new file(s) created on [%s]" % from_name)
    for name in restore_list:
        click.echo("\t%s" % name)
        try:
            create_file_at_from(name)
        except:
            if verbose:
                print(traceback.format_exc())
            raise click.ClickException("\n[ERROR] An error occurred while creating new file(s) on [%s]" % from_name)

    click.echo("\n[UPDATE] Following file(s) updated on [%s]" % to_name)
    for name in update_list:
        click.echo("\t%s" % name)
        try:
            create_file_at_to(name)
        except:
            if verbose:
                print(traceback.format_exc())
            raise click.ClickException("\n[ERROR] An error occurred while updating file(s) on [%s]" % to_name)

    click.echo("\n[DELETE] Following file(s) deleted on [%s]" % to_name)
    for name in delete_list:
        click.echo("\t%s" % name)
        try:
            delete_file_at_to(name)
        except:
            if verbose:
                print(traceback.format_exc())
            raise click.ClickException("\n[ERROR] An error occurred while creating new file(s) on [%s]" % to_name)

    click.echo("\n[SYNC] Following file(s) are up to date")
    for name in synced_list:
        click.echo("\t%s" % name)

    click.echo("\n[SKIP] Following file(s) on [%s] have not been synced to [%s]" % (from_name, to_name))
    for name in not_sync_list:
        click.echo("\t%s" % name)

    click.echo("\n[SKIP] Following file(s) on [%s] have not been synced to [%s]" % (to_name, from_name))
    for name in not_restored_list:
        click.echo("\t%s" % name)

    click.echo("")
    click.echo("✅  Synced files from [%s] to [%s]" % (from_name, to_name))
    click.echo("")

    # Which files were written on each side, for recording the sync state
    return {"to": newly_add_list + update_list, "from": restore_list}


def execute_action(action, progress_message, success_message, fail_message, verbose_error_logging=False):
    # Colours only on a terminal; yaspin warns otherwise (e.g. when the output is piped into a file)
    with yaspin(text=progress_message, color="green" if sys.stdout.isatty() else None) as spinner:
        try:
            success = action()
        except (RateLimitError, SessionExpiredError) as e:
            # A clear reason is more helpful than the generic failure message
            spinner.fail("💥 ")
            raise click.ClickException(str(e))
        except click.ClickException:
            # Already explained, e.g. by a nested execute_action
            spinner.fail("💥 ")
            raise
        except:
            if verbose_error_logging:
                print(traceback.format_exc())
            success = False

        if success:
            spinner.write(success_message)
            spinner.ok("✅ ")
        else:
            spinner.fail("💥 ")
            raise click.ClickException(fail_message)

        return success


def olignore_keep_list(olignore_path):
    """
    The list of files to keep synced, with support for sub-folders.
    Should only be called when syncing from local to remote.
    """
    # get list of files recursively (ignore .* files)
    files = glob.glob("**", recursive=True)

    click.echo("=" * 40)
    if not os.path.isfile(olignore_path):
        click.echo("\nNotice: .olignore file does not exist, will sync all items.")
        keep_list = files
    else:
        click.echo("\n.olignore: using %s to filter items" % olignore_path)
        with open(olignore_path, "r") as f:
            # "./main.tex" and "main.tex" mean the same file, matched paths have no "./" prefix (#72)
            ignore_pattern = [pattern.removeprefix("./") for pattern in f.read().splitlines()]

        keep_list = [f for f in files if not any(fnmatch.fnmatch(f, ignore) for ignore in ignore_pattern)]

    keep_list = [Path(item).as_posix() for item in keep_list if not os.path.isdir(item)]
    return keep_list


if __name__ == "__main__":
    main()
