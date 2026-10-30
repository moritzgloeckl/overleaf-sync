"""Overleaf Client"""
##################################################
# MIT License
##################################################
# File: olclient.py
# Description: Overleaf API Wrapper
# Author: Moritz Glöckl
# License: MIT
##################################################

import requests as reqs
from bs4 import BeautifulSoup
import json
import sys
import time
import uuid
from urllib.parse import urlparse

try:
    # Import for pip installation / wheel
    from olsync import realtime
except ImportError:
    # Import for development
    import realtime


BASE_URL = "https://www.overleaf.com"  # The default Overleaf server; self-hosted servers are passed as base_url
# Paths relative to the server's base URL
PROJECT_PATH = "/project"  # The dashboard
DOWNLOAD_PATH = "/project/{}/download/zip"  # Download all the files in zip format
UPLOAD_PATH = "/project/{}/upload"  # Upload files
FOLDER_PATH = "/project/{}/folder"  # Create folders
DELETE_PATH = "/project/{}/{}/{}"  # Delete files (entity type: doc or file)
COMPILE_PATH = "/project/{}/compile?enable_pdf_caching=true"  # Compile the project
PATH_SEP = "/"  # Use hardcoded path separator for both windows and posix system

# Overleaf answers with HTTP 429 (without Retry-After) when a rate limit is reached, e.g. 30 dashboard loads or 10 zip
# downloads per minute and project. Its limits use one-minute windows, so wait this many seconds before each retry.
RATE_LIMIT_WAITS = (5, 10, 20, 30)


class RateLimitError(reqs.HTTPError):
    """Overleaf's rate limit was still reached after waiting and retrying"""


class SessionExpiredError(Exception):
    """The persisted session is no longer valid (Overleaf redirects to its login page)"""


class AmbiguousProjectError(ValueError):
    """Several active projects have the requested name."""


def _request(method, url, session=None, **kwargs):
    """requests.request (or session.request) that waits and retries when Overleaf's rate limit is reached"""
    requester = session or reqs
    for wait in RATE_LIMIT_WAITS:
        r = requester.request(method, url, **kwargs)
        if r.status_code != 429:
            return r
        print(f"Overleaf's rate limit was reached, retrying in {wait}s ...", file=sys.stderr)
        time.sleep(wait)
        # Rewind uploaded files, the rejected request has already read them
        for value in (kwargs.get("files") or {}).values():
            file = value[1] if isinstance(value, tuple) else value
            if hasattr(file, "seek"):
                file.seek(0)
    r = requester.request(method, url, **kwargs)
    if r.status_code == 429:
        raise RateLimitError(
            "Overleaf's rate limit was reached (too many requests in a short time). "
            "Please wait a minute and try again.",
            response=r,
        )
    return r


class OverleafClient(object):
    """
    Overleaf API Wrapper
    Supports login, querying all projects, querying a specific project, downloading a project and
    uploading a file to a project.
    """

    @staticmethod
    def filter_projects(json_content, more_attrs=None):
        more_attrs = more_attrs or {}
        for p in json_content:
            if not p.get("archived") and not p.get("trashed"):
                if all(p.get(k) == v for k, v in more_attrs.items()):
                    yield p

    def __init__(self, cookie=None, csrf=None, base_url=BASE_URL):
        self._cookie = cookie  # Store the cookie for authenticated requests
        self._csrf = csrf  # Store the CSRF token since it is needed for some requests
        self._base_url = base_url.rstrip("/")  # overleaf.com or a self-hosted server

    @property
    def base_url(self):
        return self._base_url

    def _url(self, path):
        return self._base_url + path

    @staticmethod
    def _extract_projects(page_content):
        """
        Extract the project list from the Overleaf dashboard page.

        Overleaf used to embed the list as a bare JSON array in a
        <meta name="ol-projects"> tag. It now embeds
        {"totalSize": N, "projects": [...]} in a
        <meta name="ol-prefetchedProjectsBlob"> tag instead. Support both so
        this keeps working if Overleaf reverts or if an older cookie/page is
        cached somewhere.
        """
        soup = BeautifulSoup(page_content, "html.parser")
        tag = soup.find("meta", {"name": "ol-prefetchedProjectsBlob"}) or soup.find("meta", {"name": "ol-projects"})
        json_content = json.loads(tag.get("content"))
        if isinstance(json_content, dict):
            json_content = json_content.get("projects", [])
        return json_content

    def _dashboard(self):
        """The project dashboard; raises SessionExpiredError if Overleaf sends us to its login page instead"""
        r = _request("GET", self._url(PROJECT_PATH), cookies=self._cookie)
        if any(step.is_redirect for step in r.history) and urlparse(r.url).path.rstrip("/").endswith("/login"):
            raise SessionExpiredError(
                "Your Overleaf session has expired or is no longer valid. Please log in again with `ols login`."
            )
        return r

    def fetch_csrf(self):
        """
        Get the CSRF token from the project dashboard, e.g. after logging in with a cookie copied from a browser
        Returns: the CSRF token, or None if the session cookie is not (or no longer) valid
        """
        projects_page = _request("GET", self._url(PROJECT_PATH), cookies=self._cookie, allow_redirects=False)
        if not projects_page.ok or projects_page.is_redirect:
            return None
        csrf_tag = BeautifulSoup(projects_page.content, "html.parser").find("meta", {"name": "ol-csrfToken"})
        if csrf_tag is None:
            return None
        return csrf_tag.get("content")

    def all_projects(self):
        """
        Get all of a user's active projects (= not archived and not trashed)
        Returns: List of project objects
        """
        json_content = OverleafClient._extract_projects(self._dashboard().content)
        return list(OverleafClient.filter_projects(json_content))

    def get_project(self, project_name):
        """
        Get a specific project by project_name
        Params: project_name, the name of the project
        Returns: project object, or None if no active project has that name
        Raises: AmbiguousProjectError if several active projects have that name
        """

        json_content = OverleafClient._extract_projects(self._dashboard().content)
        projects = list(OverleafClient.filter_projects(json_content, {"name": project_name}))
        if len(projects) > 1:
            raise AmbiguousProjectError(
                f"Multiple active projects are named {project_name!r}. "
                "Use `ols list` to find their IDs, then select one with `--project-id <id>`."
            )
        return projects[0] if projects else None

    def download_project(self, project_id):
        """
        Download project in zip format
        Params: project_id, the id of the project
        Returns: bytes string (zip file)
        """
        r = _request("GET", self._url(DOWNLOAD_PATH.format(project_id)), stream=True, cookies=self._cookie)
        return r.content

    def create_folder(self, project_id, parent_folder_id, folder_name):
        """
        Create a new folder in a project

        Params:
        project_id: the id of the project
        parent_folder_id: the id of the parent folder, root is the project_id
        folder_name: how the folder will be named

        Returns: folder id or None
        """

        params = {"parent_folder_id": parent_folder_id, "name": folder_name}
        headers = {"X-Csrf-Token": self._csrf}
        r = _request(
            "POST", self._url(FOLDER_PATH.format(project_id)), cookies=self._cookie, headers=headers, json=params
        )

        if r.ok:
            return json.loads(r.content)
        elif r.status_code == 400:
            # Folder already exists. status_code is an int; comparing to
            # str(400) was always False, so this branch never actually
            # fired -- a real folder-exists response fell through to the
            # HTTPError below instead of silently continuing.
            return
        else:
            raise reqs.HTTPError()

    def get_project_infos(self, project_id):
        """
        Get detailed project infos about the project, incl. its file tree, from Overleaf's real-time service

        Params:
        project_id: the id of the project

        Returns: project details
        """
        session = reqs.Session()
        session.cookies.update(self._cookie or {})
        return realtime.join_project(session, self._base_url, project_id, request=_request)

    def upload_file(self, project_id, project_infos, file_name, file_size, file):
        """
        Upload a file to the project

        Params:
        project_id: the id of the project
        file_name: how the file will be named
        file_size: the size of the file in bytes
        file: the file itself

        Returns: True on success, False on fail
        """

        # Set the folder_id to the id of the root folder
        folder_id = project_infos["rootFolder"][0]["_id"]

        # The file name contains path separators, check folders
        if PATH_SEP in file_name:
            local_folders = file_name.split(PATH_SEP)[:-1]  # Remove last item since this is the file name
            current_overleaf_folder = project_infos["rootFolder"][0]["folders"]  # Set the current remote folder

            for local_folder in local_folders:
                exists_on_remote = False
                for remote_folder in current_overleaf_folder:
                    # Check if the folder exists on remote, continue with the new folder structure
                    if local_folder.lower() == remote_folder["name"].lower():
                        exists_on_remote = True
                        folder_id = remote_folder["_id"]
                        current_overleaf_folder = remote_folder["folders"]
                        break
                # Create the folder if it doesn't exist
                if not exists_on_remote:
                    new_folder = self.create_folder(project_id, folder_id, local_folder)
                    current_overleaf_folder.append(new_folder)
                    folder_id = new_folder["_id"]
                    current_overleaf_folder = new_folder["folders"]
        params = {
            "folder_id": folder_id,
            "_csrf": self._csrf,
            "qquuid": str(uuid.uuid4()),
            "qqfilename": file_name,
            "qqtotalfilesize": file_size,
        }
        files = {
            # Overleaf's upload endpoint now rejects the request with 422
            # {"success":false,"error":"invalid_filename"} unless the
            # filename is also present as a plain multipart field, not just
            # in qqfilename above. Confirmed live: identical request without
            # this field gets 422; with it, 200 and the file is actually
            # updated. It must be the bare file name: Overleaf rejects names
            # containing "/" (SafePath), the folder is chosen via folder_id.
            "name": (None, file_name.split(PATH_SEP)[-1]),
            "qqfile": file,
        }

        # Upload the file to the predefined folder
        r = _request(
            "POST", self._url(UPLOAD_PATH.format(project_id)), cookies=self._cookie, params=params, files=files
        )

        # status_code is an int; comparing to str(200) was always False here,
        # so this reported failure on every call regardless of the real
        # result. Harmless today only because callers don't check the return
        # value, but worth fixing since it's the only signal this method
        # gives back.
        return r.status_code == 200 and json.loads(r.content)["success"]

    def delete_file(self, project_id, project_infos, file_name):
        """
        Deletes a project's file

        Params:
        project_id: the id of the project
        file_name: how the file will be named

        Returns: True on success, False on fail
        """

        # Walk down to the folder that contains the file (folder names match case-insensitively, as in upload_file)
        *local_folders, name = file_name.split(PATH_SEP)
        current_folder = project_infos["rootFolder"][0]
        for local_folder in local_folders:
            current_folder = next(
                (f for f in current_folder["folders"] if f["name"].lower() == local_folder.lower()), None
            )
            if current_folder is None:
                return False

        # Text files are "docs", binary files (images, PDFs, ...) are "fileRefs" with their own endpoint
        file = next((v for v in current_folder.get("docs", []) if v["name"] == name), None)
        entity_type = "doc"
        if file is None:
            file = next((v for v in current_folder.get("fileRefs", []) if v["name"] == name), None)
            entity_type = "file"

        # File not found!
        if file is None:
            return False

        headers = {"X-Csrf-Token": self._csrf}

        r = _request(
            "DELETE",
            self._url(DELETE_PATH.format(project_id, entity_type, file["_id"])),
            cookies=self._cookie,
            headers=headers,
            json={},
        )

        # status_code is an int; comparing to str(204) was always False
        # regardless of the real result, same bug class as upload_file and
        # create_folder above.
        return r.status_code == 204

    def download_pdf(self, project_id):
        """
        Compiles and returns a project's PDF

        Params:
        project_id: the id of the project

        Returns: PDF file name and content on success
        """
        headers = {"X-Csrf-Token": self._csrf}

        body = {
            "check": "silent",
            "draft": False,
            "incrementalCompilesEnabled": True,
            # No rootDoc_id: Overleaf validates it as an optional ObjectId and rejects "" (400)
            "stopOnFirstError": False,
        }

        r = _request(
            "POST",
            self._url(COMPILE_PATH.format(project_id)),
            cookies=self._cookie,
            headers=headers,
            json=body,
            timeout=(10, 300),
        )

        if not r.ok:
            raise reqs.HTTPError()

        compile_result = json.loads(r.content)

        if compile_result["status"] != "success":
            raise reqs.HTTPError()

        pdf_file = next(v for v in compile_result["outputFiles"] if v["type"] == "pdf")

        # The output is only served (otherwise 404) when the compile group and CLSI server are passed along,
        # like Overleaf's own frontend does. Self-hosted servers may not send them.
        params = {}
        if compile_result.get("compileGroup"):
            params["compileGroup"] = compile_result["compileGroup"]
        if compile_result.get("clsiServerId"):
            params["clsiserverid"] = compile_result["clsiServerId"]

        download_req = _request(
            "GET",
            self._url(pdf_file["url"]),
            cookies=self._cookie,
            headers=headers,
            params=params,
            timeout=(10, 120),
        )

        if not download_req.ok:
            raise reqs.HTTPError(
                f"Overleaf did not serve the compiled PDF (HTTP {download_req.status_code}).",
                response=download_req,
            )

        return pdf_file["path"], download_req.content
