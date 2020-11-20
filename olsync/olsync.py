"""Overleaf Two-Way Sync Tool"""
##################################################
# MIT License
##################################################
# File: olsync.py
# Description: Overleaf Two-Way Sync
# Author: Moritz Glöckl
# License: MIT
# Version: 1.1.1
##################################################

import click
import os
from yaspin import yaspin
import pickle
import zipfile
import io
import dateutil.parser
import glob
import fnmatch

try:
    # Import for pip installation / wheel
    from olsync.olclient import OverleafClient
except ImportError:
    # Import for development
    from olclient import OverleafClient


@click.group(invoke_without_command=True)
@click.option('-l', '--local-only', 'local', is_flag=True, help="Sync local project files to Overleaf only.")
@click.option('-r', '--remote-only', 'remote', is_flag=True,
              help="Sync remote project files from Overleaf to local file system only.")
@click.option('--store-path', 'cookie_path', default=".olauth", type=click.Path(exists=False),
              help="Relative path to load the persisted Overleaf cookie.")
@click.option('-p', '--path', 'sync_path', default=".", type=click.Path(exists=True),
              help="Path of the project to sync.")
@click.option('-i', '--olignore', 'olignore_path', default=".olignore", type=click.Path(exists=False),
              help="Relative path of the .olignore file (ignored if sync from remote to local).")
@click.version_option()
@click.pass_context
def main(ctx, local, remote, cookie_path, sync_path, olignore_path):
    if ctx.invoked_subcommand is None:
        if not os.path.isfile(cookie_path):
            raise click.ClickException(
                "Persisted Overleaf cookie not found. Please login or check store path.")

        with open(cookie_path, 'rb') as f:
            store = pickle.load(f)

        ce_url = olceChecker(sync_path)

        overleaf_client = OverleafClient(store["cookie"], store["csrf"], ce_url)

        project = execute_action(
            lambda: overleaf_client.get_project(
                os.path.basename(os.path.join(sync_path, os.getcwd()))),
            "Querying project",
            "Project queried successfully.",
            "Project could not be queried.")

        project_infos = execute_action(
            lambda: overleaf_client.get_project_infos(project["id"]),
            "Querying project details",
            "Project details queried successfully.",
            "Project details could not be queried.")

        zip_file = execute_action(
            lambda: zipfile.ZipFile(io.BytesIO(
                overleaf_client.download_project(project["id"]))),
            "Downloading project",
            "Project downloaded successfully.",
            "Project could not be downloaded.")

        sync = not (local or remote)

        if remote or sync:
            sync_func(
                files_from=zip_file.namelist(),
                create_file_at_to=lambda name: write_file(
                    os.path.join(sync_path, name), zip_file.read(name)),
                from_exists_in_to=lambda name: os.path.isfile(
                    os.path.join(sync_path, name)),
                from_equal_to_to=lambda name: open(os.path.join(
                    sync_path, name), 'rb').read() == zip_file.read(name),
                from_newer_than_to=lambda name: dateutil.parser.isoparse(project["lastUpdated"]).timestamp() > os.path.getmtime(
                    os.path.join(sync_path, name)),
                from_name="remote",
                to_name="local")
        if local or sync:
            sync_func(
                files_from=olignore_keep_list(sync_path, olignore_path),
                create_file_at_to=lambda name: overleaf_client.upload_file(
                    project["id"], project_infos, name, os.path.getsize(
                        os.path.join(sync_path, name)), open(os.path.join(sync_path, name), 'rb')),
                from_exists_in_to=lambda name: name in zip_file.namelist(),
                from_equal_to_to=lambda name: open(os.path.join(sync_path, name),
                                                   'rb').read() == zip_file.read(name),
                from_newer_than_to=lambda name: os.path.getmtime(os.path.join(sync_path, name)) > dateutil.parser.isoparse(
                    project["lastUpdated"]).timestamp(),
                from_name="local",
                to_name="remote")


@main.command()
@click.option('-u', '--username', prompt=True, required=True,
              help="You Overleaf username. Will NOT be stored or used for anything else.")
@click.option('-p', '--password', prompt=True, hide_input=True, required=True,
              help="You Overleaf password. Will NOT be stored or used for anything else.")
@click.option('--path', 'cookie_path', default=".olauth", type=click.Path(exists=False),
              help="Path to store the persisted Overleaf cookie.")
def login(username, password, cookie_path):
    if os.path.isfile(cookie_path) and not click.confirm(
            'Persisted Overleaf cookie already exist. Do you want to override it?'):
        return
    click.clear()
    execute_action(lambda: login_handler(username, password, cookie_path), "Login",
                   "Login successful. Cookie persisted as `" + click.format_filename(
                       cookie_path) + "`. You may now sync your project.",
                   "Login failed. Check username and/or password.")


def login_handler(username, password, path):
    overleaf_client = OverleafClient(None, None, olceChecker())
    store = overleaf_client.login(username, password)
    if store is None:
        return False
    with open(path, 'wb+') as f:
        pickle.dump(store, f)
    return True


def write_file(path, content):
    _dir = os.path.dirname(path)
    if _dir == path:
        return

    # path is a file
    if not os.path.exists(_dir):
        os.makedirs(_dir)

    with open(path, 'wb+') as f:
        f.write(content)


def sync_func(files_from, create_file_at_to, from_exists_in_to, from_equal_to_to, from_newer_than_to, from_name, to_name):
    click.echo("\nSyncing files from [%s] to [%s]" % (from_name, to_name))
    click.echo('='*40)

    newly_add_list = []
    update_list = []
    not_sync_list = []
    synced_list = []

    for name in files_from:
        if from_exists_in_to(name):
            if not from_equal_to_to(name):
                if not from_newer_than_to(name) and not click.confirm(
                        '\n-> Warning: last-edit time stamp of file <%s> from [%s] is older than [%s].\nContinue to '
                        'overwrite with an older version?' % (name, from_name, to_name)):
                    not_sync_list.append(name)
                    continue

                update_list.append(name)
            else:
                synced_list.append(name)
        else:
            newly_add_list.append(name)

    click.echo(
        "\n[NEW] Following new file(s) created on [%s]" % to_name)
    for name in newly_add_list:
        click.echo("\t%s" % name)
        create_file_at_to(name)

    click.echo(
        "\n[UPDATE] Following file(s) updated on [%s]" % to_name)
    for name in update_list:
        click.echo("\t%s" % name)
        create_file_at_to(name)

    click.echo(
        "\n[SYNC] Following file(s) are up to date")
    for name in synced_list:
        click.echo("\t%s" % name)

    click.echo(
        "\n[SKIP] Following file(s) on [%s] have not been synced to [%s]" % (from_name, to_name))
    for name in not_sync_list:
        click.echo("\t%s" % name)

    click.echo("")
    click.echo("✅  Synced files from [%s] to [%s]" % (from_name, to_name))
    click.echo("")


def execute_action(action, progress_message, success_message, fail_message):
    with yaspin(text=progress_message, color="green") as spinner:
        try:
            success = action()
        except:
            success = False

        if success:
            spinner.write(success_message)
            spinner.ok("✅ ")
        else:
            raise click.ClickException(fail_message)
            spinner.fail("💥 ")

        return success


def olignore_keep_list(sync_path, olignore_path):
    """
    The list of files to keep synced, with support for sub-folders.
    Should only be called when syncing from local to remote.
    """
    # get list of files recursively (ignore .* files)
    files = glob.glob('**', recursive=True)

    olignore_file = os.path.join(sync_path, olignore_path)
    click.echo("="*40)
    if not os.path.isfile(olignore_file):
        click.echo("\nNotice: .olignore file does not exist, will sync all items.")
        keep_list = files
    else:
        click.echo("\n.olignore: using %s to filter items" % olignore_file)
        with open(olignore_file, 'r') as f:
            ignore_pattern = f.read().splitlines()

        keep_list = [f for f in files if not any(
            fnmatch.fnmatch(f, ignore) for ignore in ignore_pattern)]

    keep_list = [item for item in keep_list if not os.path.isdir(item)]
    return keep_list

def olceChecker(sync_path = ""):

    # Read .olce file for URL to local installation of Overleaf/Sharelatex
    olce_file = os.path.join(sync_path, ".olce")

    click.echo("=" * 40)
    ce_url = None
    if not os.path.isfile(olce_file):
        click.echo("\nNotice: .olce file does not exist, will sync with overleaf.com.")
    else:

        with open(olce_file, 'r') as f:
            ce_url = f.readline()
            f.close()

        click.echo("\n.olce: using %s as CE server" % ce_url)

    return ce_url

if __name__ == "__main__":
    main()
