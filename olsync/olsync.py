"""Overleaf Two-Way Sync Tool"""
##################################################
# MIT License
##################################################
# File: olsync.py
# Description: Overleaf Two-Way Sync
# Author: Moritz Glöckl
# License: MIT
# Version: 1.2.0
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
import traceback
from pathlib import Path

try:
    # Import for pip installation / wheel
    from olsync.olclient import OverleafClient
    import olsync.olbrowserlogin as olbrowserlogin
except ImportError:
    # Import for development
    from olclient import OverleafClient
    import olbrowserlogin


@click.group(invoke_without_command=True)
@click.option('-l', '--local-only', 'local', is_flag=True, help="Sync local project files to Overleaf only.")
@click.option('-r', '--remote-only', 'remote', is_flag=True,
              help="Sync remote project files from Overleaf to local file system only.")
@click.option('-n', '--name', 'project_name', default="",
              help="Specify the Overleaf project name instead of the default name of the sync directory.")
@click.option('--store-path', 'cookie_path', default=".olauth", type=click.Path(exists=False),
              help="Relative path to load the persisted Overleaf cookie.")
@click.option('-p', '--path', 'sync_path', default=".", type=click.Path(exists=True),
              help="Path of the project to sync.")
@click.option('-i', '--olignore', 'olignore_path', default=".olignore", type=click.Path(exists=False),
              help="Path to the .olignore file relative to sync path (ignored if syncing from remote to local). See "
                   "fnmatch / unix filename pattern matching for information on how to use it.")
@click.option('-v', '--verbose', 'verbose', is_flag=True, help="Enable extended error logging.")
@click.version_option(package_name='overleaf-sync')
@click.pass_context
def main(ctx, local, remote, project_name, cookie_path, sync_path, olignore_path, verbose):
    if ctx.invoked_subcommand is None:
        if not os.path.isfile(cookie_path):
            raise click.ClickException(
                "Persisted Overleaf cookie not found. Please login or check store path.")

        with open(cookie_path, 'rb') as f:
            store = pickle.load(f)

        overleaf_client = OverleafClient(store["cookie"], store["csrf"])

        # Change the current directory to the specified sync path
        os.chdir(sync_path)

        project_name = project_name or os.path.basename(os.getcwd())
        project = execute_action(
            lambda: overleaf_client.get_project(project_name),
            "Querying project",
            "Project queried successfully.",
            "Project could not be queried.",
            verbose)

        project_infos = execute_action(
            lambda: overleaf_client.get_project_infos(project["id"]),
            "Querying project details",
            "Project details queried successfully.",
            "Project details could not be queried.",
            verbose)

        zip_file = execute_action(
            lambda: zipfile.ZipFile(io.BytesIO(
                overleaf_client.download_project(project["id"]))),
            "Downloading project",
            "Project downloaded successfully.",
            "Project could not be downloaded.",
            verbose)
            
        if not os.path.isfile(olignore_path):
            click.echo("\nNotice: .olignore file does not exist, will sync all items.")
        else:
            click.echo("\n.olignore: using %s to filter items" % olignore_path)

        sync = not (local or remote)

        if remote or sync:
            sync_func(
                files_from=zip_file.namelist(),
                deleted_files=[f for f in olignore_keep_list(olignore_path) if f not in zip_file.namelist() and not sync],
                create_file_at_to=lambda name: write_file(name, zip_file.read(name)),
                delete_file_at_to=lambda name: delete_file(name),
                create_file_at_from=lambda name: overleaf_client.upload_file(
                    project["id"], project_infos, name, os.path.getsize(name), open(name, 'rb')),
                from_exists_in_to=lambda name: os.path.isfile(name),
                from_equal_to_to=lambda name: open(name, 'rb').read() == zip_file.read(name),
                from_newer_than_to=lambda name: dateutil.parser.isoparse(project["lastUpdated"]).timestamp() >
                                                os.path.getmtime(name),
                from_name="remote",
                to_name="local",
                verbose=verbose)
        if local or sync:
            sync_func(
                files_from=olignore_keep_list(olignore_path),
                deleted_files=[f for f in zip_file.namelist() if f not in olignore_keep_list(olignore_path) and not sync],
                create_file_at_to=lambda name: overleaf_client.upload_file(
                    project["id"], project_infos, name, os.path.getsize(name), open(name, 'rb')),
                delete_file_at_to=lambda name: overleaf_client.delete_file(project["id"], project_infos, name),
                create_file_at_from=lambda name: write_file(name, zip_file.read(name)),
                from_exists_in_to=lambda name: name in zip_file.namelist(),
                from_equal_to_to=lambda name: open(name, 'rb').read() == zip_file.read(name),
                from_newer_than_to=lambda name: os.path.getmtime(name) > dateutil.parser.isoparse(
                    project["lastUpdated"]).timestamp(),
                from_name="local",
                to_name="remote",
                verbose=verbose)


@main.command()
@click.option('--path', 'cookie_path', default=".olauth", type=click.Path(exists=False),
              help="Path to store the persisted Overleaf cookie.")
@click.option('-v', '--verbose', 'verbose', is_flag=True, help="Enable extended error logging.")
def login(cookie_path, verbose):
    if os.path.isfile(cookie_path) and not click.confirm(
            'Persisted Overleaf cookie already exist. Do you want to override it?'):
        return
    click.clear()
    execute_action(lambda: login_handler(cookie_path), "Login",
                   "Login successful. Cookie persisted as `" + click.format_filename(
                       cookie_path) + "`. You may now sync your project.",
                   "Login failed. Please try again.", verbose)


@main.command(name='list')
@click.option('--store-path', 'cookie_path', default=".olauth", type=click.Path(exists=False),
              help="Relative path to load the persisted Overleaf cookie.")
@click.option('-v', '--verbose', 'verbose', is_flag=True, help="Enable extended error logging.")
def list_projects(cookie_path, verbose):
    def query_projects():
        for index, p in enumerate(sorted(overleaf_client.all_projects(), key=lambda x: x['lastUpdated'], reverse=True)):
            if not index:
                click.echo("\n")
            click.echo(f"{dateutil.parser.isoparse(p['lastUpdated']).strftime('%m/%d/%Y, %H:%M:%S')} - {p['name']}")
        return True

    if not os.path.isfile(cookie_path):
        raise click.ClickException(
            "Persisted Overleaf cookie not found. Please login or check store path.")

    with open(cookie_path, 'rb') as f:
        store = pickle.load(f)

    overleaf_client = OverleafClient(store["cookie"], store["csrf"])

    click.clear()
    execute_action(query_projects, "Querying all projects",
                   "Querying all projects successful.",
                   "Querying all projects failed. Please try again.", verbose)


@main.command(name='download')
@click.option('-n', '--name', 'project_name', default="",
              help="Specify the Overleaf project name instead of the default name of the sync directory.")
@click.option('--download-path', 'download_path', default=".", type=click.Path(exists=True))
@click.option('--store-path', 'cookie_path', default=".olauth", type=click.Path(exists=False),
              help="Relative path to load the persisted Overleaf cookie.")
@click.option('-v', '--verbose', 'verbose', is_flag=True, help="Enable extended error logging.")
def download_pdf(project_name, download_path, cookie_path, verbose):
    def download_project_pdf():
        nonlocal project_name
        project_name = project_name or os.path.basename(os.getcwd())
        project = execute_action(
            lambda: overleaf_client.get_project(project_name),
            "Querying project",
            "Project queried successfully.",
            "Project could not be queried.",
            verbose)

        file_name, content = overleaf_client.download_pdf(project["id"])

        if file_name and content:
            # Change the current directory to the specified sync path
            os.chdir(download_path)
            open(file_name, 'wb').write(content)

        return True
    
    click.echo("="*40)
    if not os.path.isfile(cookie_path):
        raise click.ClickException(
            "Persisted Overleaf cookie not found. Please login or check store path.")

    with open(cookie_path, 'rb') as f:
        store = pickle.load(f)

    overleaf_client = OverleafClient(store["cookie"], store["csrf"])

    click.clear()

    execute_action(download_project_pdf, "Downloading project's PDF",
                   "Downloading project's PDF successful.",
                   "Downloading project's PDF failed. Please try again.", verbose)


def login_handler(path):
    store = olbrowserlogin.login()
    if store is None:
        return False
    with open(path, 'wb+') as f:
        pickle.dump(store, f)
    return True


def delete_file(path):
    _dir = os.path.dirname(path)
    if _dir == path:
        return

    if _dir != '' and not os.path.exists(_dir):
        return
    else:
        os.remove(path)


def write_file(path, content):
    _dir = os.path.dirname(path)
    if _dir == path:
        return

    # path is a file
    if _dir != '' and not os.path.exists(_dir):
        os.makedirs(_dir)

    with open(path, 'wb+') as f:
        f.write(content)


def sync_func(files_from, deleted_files, create_file_at_to, delete_file_at_to, create_file_at_from, from_exists_in_to,
              from_equal_to_to, from_newer_than_to, from_name,
              to_name, verbose=False):
    click.echo("\nSyncing files from [%s] to [%s]" % (from_name, to_name))
    click.echo('=' * 40)

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

    for name in deleted_files:
        delete_choice = click.prompt(
            '\n-> Warning: file <%s> does not exist on [%s] anymore (but it still exists on [%s]).'
            '\nShould the file be [d]eleted, [r]estored or [i]gnored?' % (name, from_name, to_name),
            default="i",
            type=click.Choice(['d', 'r', 'i']))
        if delete_choice == "d":
            delete_list.append(name)
        elif delete_choice == "r":
            restore_list.append(name)
        elif delete_choice == "i":
            not_restored_list.append(name)

    click.echo(
        "\n[NEW] Following new file(s) created on [%s]" % to_name)
    for name in newly_add_list:
        click.echo("\t%s" % name)
        try:
            create_file_at_to(name)
        except:
            if verbose:
                print(traceback.format_exc())
            raise click.ClickException("\n[ERROR] An error occurred while creating new file(s) on [%s]" % to_name)

    click.echo(
        "\n[NEW] Following new file(s) created on [%s]" % from_name)
    for name in restore_list:
        click.echo("\t%s" % name)
        try:
            create_file_at_from(name)
        except:
            if verbose:
                print(traceback.format_exc())
            raise click.ClickException("\n[ERROR] An error occurred while creating new file(s) on [%s]" % from_name)

    click.echo(
        "\n[UPDATE] Following file(s) updated on [%s]" % to_name)
    for name in update_list:
        click.echo("\t%s" % name)
        try:
            create_file_at_to(name)
        except:
            if verbose:
                print(traceback.format_exc())
            raise click.ClickException("\n[ERROR] An error occurred while updating file(s) on [%s]" % to_name)

    click.echo(
        "\n[DELETE] Following file(s) deleted on [%s]" % to_name)
    for name in delete_list:
        click.echo("\t%s" % name)
        try:
            delete_file_at_to(name)
        except:
            if verbose:
                print(traceback.format_exc())
            raise click.ClickException("\n[ERROR] An error occurred while creating new file(s) on [%s]" % to_name)

    click.echo(
        "\n[SYNC] Following file(s) are up to date")
    for name in synced_list:
        click.echo("\t%s" % name)

    click.echo(
        "\n[SKIP] Following file(s) on [%s] have not been synced to [%s]" % (from_name, to_name))
    for name in not_sync_list:
        click.echo("\t%s" % name)

    click.echo(
        "\n[SKIP] Following file(s) on [%s] have not been synced to [%s]" % (to_name, from_name))
    for name in not_restored_list:
        click.echo("\t%s" % name)

    click.echo("")
    click.echo("✅  Synced files from [%s] to [%s]" % (from_name, to_name))
    click.echo("")


def execute_action(action, progress_message, success_message, fail_message, verbose_error_logging=False):
    with yaspin(text=progress_message, color="green") as spinner:
        try:
            success = action()
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
    files = glob.glob('**', recursive=True)

    # click.echo("="*40)
    if not os.path.isfile(olignore_path):
        # click.echo("\nNotice: .olignore file does not exist, will sync all items.")
        keep_list = files
    else:
        # click.echo("\n.olignore: using %s to filter items" % olignore_path)
        with open(olignore_path, 'r') as f:
            ignore_pattern = f.read().splitlines()

        keep_list = [f for f in files if not any(
            fnmatch.fnmatch(f, ignore) for ignore in ignore_pattern)]

    keep_list = [Path(item).as_posix() for item in keep_list if not os.path.isdir(item)]
    return keep_list


if __name__ == "__main__":
    main()
