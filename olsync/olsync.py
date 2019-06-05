"""Overleaf Two-Way Sync Tool"""
##################################################
# MIT License
##################################################
# File: olsync.py
# Description: Overleaf Two-Way Sync
# Author: Moritz Glöckl
# License: MIT
# Version: 1.0.0
##################################################

import click
import os
from yaspin import yaspin
from olsync.olclient import OverleafClient
import pickle
import zipfile
import io
import dateutil.parser


@click.group(invoke_without_command=True)
@click.option('-l', '--local-only', 'local', is_flag=True, help="Sync local project files to Overleaf only.")
@click.option('-r', '--remote-only', 'remote', is_flag=True,
              help="Sync remote project files from Overleaf to local file system only.")
@click.option('--store-path', 'cookie_path', default=".olauth", type=click.Path(exists=False),
              help="Path to load the persisted Overleaf cookie.")
@click.option('-p', '--path', 'sync_path', default=".", type=click.Path(exists=True),
              help="Path of the project to sync.")
@click.pass_context
def main(ctx, local, remote, cookie_path, sync_path):
    if ctx.invoked_subcommand is None:
        if not os.path.isfile(cookie_path):
            raise click.ClickException("Persisted Overleaf cookie not found. Please login or check store path.")

        with open(cookie_path, 'rb') as f:
            store = pickle.load(f)

        overleaf_client = OverleafClient(store["cookie"], store["csrf"])

        project = execute_action(
            lambda: overleaf_client.get_project(os.path.basename(os.path.join(sync_path, os.getcwd()))),
            "Querying project", "Project queried successfully.", "Project could not be queried.")
        zip_file = execute_action(lambda: zipfile.ZipFile(io.BytesIO(overleaf_client.download_project(project["id"])))
                                  , "Downloading project", "Project downloaded successfully.",
                                  "Project could not be downloaded.")

        sync = not (local or remote)

        if remote or sync:
            sync_func(zip_file.namelist(),
                      lambda name: write_file(os.path.join(sync_path, name), zip_file.read(name)),
                      lambda name: os.path.isfile(os.path.join(sync_path, name)),
                      lambda name: open(os.path.join(sync_path, name), 'rb').read() == zip_file.read(name),
                      lambda name: dateutil.parser.isoparse(project["lastUpdated"]).timestamp() > os.path.getmtime(
                          os.path.join(sync_path, name)),
                      "remote", "local")
        if local or sync:
            sync_func(
                [f for f in os.listdir(sync_path) if
                 os.path.isfile(os.path.join(sync_path, f)) and not f.startswith(".")],
                lambda name: overleaf_client.upload_file(project["id"], name,
                                                         os.path.getsize(os.path.join(sync_path, name)),
                                                         open(os.path.join(sync_path, name), 'rb')),
                lambda name: name in zip_file.namelist(),
                lambda name: open(os.path.join(sync_path, name), 'rb').read() == zip_file.read(name),
                lambda name: os.path.getmtime(os.path.join(sync_path, name)) > dateutil.parser.isoparse(
                    project["lastUpdated"]).timestamp(),
                "local", "remote")


@main.command()
@click.option('-u', '--username', prompt=True, required=True,
              help="You Overleaf username. Will NOT be stored or used for anything else.")
@click.option('-p', '--password', prompt=True, hide_input=True, required=True,
              help="You Overleaf password. Will NOT be stored or used for anything else.")
@click.option('--path', 'cookie_path', default=".olauth", type=click.Path(exists=False),
              help="Path to store the persisted Overleaf cookie.")
def login(username, password, cookie_path):
    if os.path.isfile(cookie_path) and not click.confirm(
            'Persisted Overleaf cookie already exist. Do you want to override it?'): return
    click.clear()
    execute_action(lambda: login_handler(username, password, cookie_path), "Login",
                   "Login successful. Cookie persisted as `" + click.format_filename(
                       cookie_path) + "`. You may now sync your project.",
                   "Login failed. Check username and/or password.")


def login_handler(username, password, path):
    overleaf_client = OverleafClient()
    store = overleaf_client.login(username, password)
    if store is None:
        return False
    with open(path, 'wb+') as f:
        pickle.dump(store, f)
    return True


def write_file(path, content):
    with open(path, 'wb+') as f:
        f.write(content)


def sync_func(files_from, create_file_at_to, from_exists_in_to, from_equal_to_to, from_newer_than_to, from_name,
              to_name):
    click.echo("\nSyncing files from %s to %s" % (from_name, to_name))
    click.echo("====================\n")
    for name in files_from:
        click.echo("[SYNCING] %s" % name)
        if from_exists_in_to(name):
            if not from_equal_to_to(name):
                if not from_newer_than_to(name) and not click.confirm(
                        'Warning %s file will be overwritten by %s. Continue?' % (to_name, from_name)):
                    continue

                click.echo("%s syncing from %s to %s." % (name, from_name, to_name))
                create_file_at_to(name)
            else:
                click.echo("%s file is equal to %s file. No sync necessary." % (name, to_name))
        else:
            click.echo("%s does not exist on %s. Creating file." % (name, to_name))
            create_file_at_to(name)

        click.echo("")

    click.echo("")
    click.echo("✅  Syncing files from %s to %s" % (from_name, to_name))
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


if __name__ == "__main__":
    main()
