"""Sync state for two-way sync"""
##################################################
# MIT License
##################################################
# File: syncstate.py
# Description: Per-file sync state, so two-way sync can tell which side changed a file
# Author: Moritz Glöckl
# License: MIT
##################################################

import hashlib
import json
import os
import tempfile
from pathlib import Path

# Stored in the sync folder. Dotfiles are never uploaded (glob skips them), so it stays local.
STATE_FILE = ".olsync-state.json"
STATE_VERSION = 1


def file_hash(content):
    """
    Content hash used to detect changes
    Params: content, the file content (bytes)
    Returns: hex digest
    """
    return hashlib.sha256(content).hexdigest()


def load_state(sync_dir, server, project_id):
    """
    Load the per-file state of the last successful sync of this project
    Params: sync_dir, server, project_id
    Returns: {path: {"local": hash, "remote": hash}}, empty if there is no (valid) state for this server and project
    """
    try:
        with open(Path(sync_dir) / STATE_FILE) as f:
            state = json.load(f)
    except (OSError, ValueError):
        return {}
    if not isinstance(state, dict) or state.get("version") != STATE_VERSION \
            or state.get("server") != server or state.get("project_id") != project_id:
        return {}
    return state.get("files", {})


def save_state(sync_dir, server, project_id, files):
    """
    Save the per-file state atomically, so an interrupted sync never leaves a broken state file
    Params: sync_dir, server, project_id, files ({path: {"local": hash, "remote": hash}})
    """
    state = {"version": STATE_VERSION, "server": server, "project_id": project_id, "files": files}
    fd, tmp_path = tempfile.mkstemp(dir=sync_dir, prefix=STATE_FILE + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(state, f, indent=1, sort_keys=True)
        os.replace(tmp_path, Path(sync_dir) / STATE_FILE)
    except BaseException:
        os.unlink(tmp_path)
        raise


def plan_two_way(local, remote, state):
    """
    Decide per file what a two-way sync has to do
    Params:
    local: {path: hash} of the local files
    remote: {path: hash} of the files on Overleaf
    state: {path: {"local": hash, "remote": hash}} from the last successful sync
    Returns: {"upload": [...], "download": [...], "conflict": [...], "in_sync": [...]} (sorted paths)
    """
    plan = {"upload": [], "download": [], "conflict": [], "in_sync": []}
    for path in sorted(set(local) | set(remote)):
        local_hash, remote_hash, last = local.get(path), remote.get(path), state.get(path)
        if remote_hash is None:
            action = "upload"
        elif local_hash is None:
            action = "download"
        elif local_hash == remote_hash:
            action = "in_sync"
        elif last is None:
            # No sync history for this file: never guess which version is newer
            action = "conflict"
        else:
            local_changed = local_hash != last.get("local")
            remote_changed = remote_hash != last.get("remote")
            if local_changed and remote_changed:
                action = "conflict"
            elif local_changed:
                action = "upload"
            elif remote_changed:
                action = "download"
            else:
                # Differs, but neither side changed since the last sync (e.g. Overleaf normalised the file)
                action = "in_sync"
        plan[action].append(path)
    return plan
