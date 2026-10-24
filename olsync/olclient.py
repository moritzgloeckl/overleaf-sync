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
import ssl
import uuid
import websocket
from socketIO_client import SocketIO
import time

# socketIO_client/transports.py has `except websocket.SSLError`, an attribute
# recent websocket-client (1.9.0+) no longer exposes; that raises AttributeError
# and masks whatever the actual connection error is. Keep this shim for as long
# as we depend on socketIO-client.
if not hasattr(websocket, "SSLError"):
    websocket.SSLError = ssl.SSLError

# Where to get the CSRF Token and where to send the login request to
LOGIN_URL = "https://www.overleaf.com/login"
PROJECT_URL = "https://www.overleaf.com/project"  # The dashboard URL
# The URL to download all the files in zip format
DOWNLOAD_URL = "https://www.overleaf.com/project/{}/download/zip"
UPLOAD_URL = "https://www.overleaf.com/project/{}/upload"  # The URL to upload files
FOLDER_URL = "https://www.overleaf.com/project/{}/folder"  # The URL to create folders
DELETE_URL = "https://www.overleaf.com/project/{}/doc/{}"  # The URL to delete files
COMPILE_URL = "https://www.overleaf.com/project/{}/compile?enable_pdf_caching=true"  # The URL to compile the project
BASE_URL = "https://www.overleaf.com"  # The Overleaf Base URL
PATH_SEP = "/"  # Use hardcoded path separator for both windows and posix system

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

    def __init__(self, cookie=None, csrf=None):
        self._cookie = cookie  # Store the cookie for authenticated requests
        self._csrf = csrf  # Store the CSRF token since it is needed for some requests

    def login(self, username, password):
        """
        WARNING - DEPRECATED - Not working as Overleaf introduced captchas
        Login to the Overleaf Service with a username and a password
        Params: username, password
        Returns: Dict of cookie and CSRF
        """

        get_login = reqs.get(LOGIN_URL)
        self._csrf = BeautifulSoup(get_login.content, 'html.parser').find(
            'input', {'name': '_csrf'}).get('value')
        login_json = {
            "_csrf": self._csrf,
            "email": username,
            "password": password
        }
        post_login = reqs.post(LOGIN_URL, json=login_json,
                               cookies=get_login.cookies)

        # On a successful authentication the Overleaf API returns a new authenticated cookie.
        # If the cookie is different than the cookie of the GET request the authentication was successful
        if post_login.status_code == 200 and get_login.cookies["overleaf_session2"] != post_login.cookies[
            "overleaf_session2"]:
            self._cookie = post_login.cookies

            # Enrich cookie with GCLB cookie from GET request above
            self._cookie['GCLB'] = get_login.cookies['GCLB']

            # CSRF changes after making the login request, new CSRF token will be on the projects page
            projects_page = reqs.get(PROJECT_URL, cookies=self._cookie)
            self._csrf = BeautifulSoup(projects_page.content, 'html.parser').find('meta', {'name': 'ol-csrfToken'}) \
                .get('content')

            return {"cookie": self._cookie, "csrf": self._csrf}

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
        soup = BeautifulSoup(page_content, 'html.parser')
        tag = soup.find('meta', {'name': 'ol-prefetchedProjectsBlob'}) or soup.find('meta', {'name': 'ol-projects'})
        json_content = json.loads(tag.get('content'))
        if isinstance(json_content, dict):
            json_content = json_content.get('projects', [])
        return json_content

    def fetch_csrf(self):
        """
        Get the CSRF token from the project dashboard, e.g. after logging in with a cookie copied from a browser
        Returns: the CSRF token, or None if the session cookie is not (or no longer) valid
        """
        projects_page = reqs.get(PROJECT_URL, cookies=self._cookie, allow_redirects=False)
        if not projects_page.ok or projects_page.is_redirect:
            return None
        csrf_tag = BeautifulSoup(projects_page.content, 'html.parser').find('meta', {'name': 'ol-csrfToken'})
        return csrf_tag.get('content') if csrf_tag is not None else None

    def all_projects(self):
        """
        Get all of a user's active projects (= not archived and not trashed)
        Returns: List of project objects
        """
        projects_page = reqs.get(PROJECT_URL, cookies=self._cookie)
        json_content = OverleafClient._extract_projects(projects_page.content)
        return list(OverleafClient.filter_projects(json_content))

    def get_project(self, project_name):
        """
        Get a specific project by project_name
        Params: project_name, the name of the project
        Returns: project object
        """

        projects_page = reqs.get(PROJECT_URL, cookies=self._cookie)
        json_content = OverleafClient._extract_projects(projects_page.content)
        return next(OverleafClient.filter_projects(json_content, {"name": project_name}), None)

    def download_project(self, project_id):
        """
        Download project in zip format
        Params: project_id, the id of the project
        Returns: bytes string (zip file)
        """
        r = reqs.get(DOWNLOAD_URL.format(project_id),
                     stream=True, cookies=self._cookie)
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

        params = {
            "parent_folder_id": parent_folder_id,
            "name": folder_name
        }
        headers = {
            "X-Csrf-Token": self._csrf
        }
        r = reqs.post(FOLDER_URL.format(project_id),
                      cookies=self._cookie, headers=headers, json=params)

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
        Get detailed project infos about the project

        Params:
        project_id: the id of the project

        Returns: project details
        """
        project_infos = None

        # Callback for the joinProjectResponse event the server pushes right
        # after a successful connect+auto-join (see below) -- delivered as a
        # plain named event, not as an ack to an explicit emit, and shaped as
        # {"publicId": ..., "project": {...}}. Downstream code (upload_file,
        # delete_file) indexes project_infos['rootFolder'][0][...] directly,
        # so unwrap to the inner "project" dict here rather than returning
        # the wrapper.
        def set_project_infos(data):
            nonlocal project_infos
            project_infos = data.get('project')

        # The Socket.IO handshake below (done again internally by the SocketIO()
        # constructor) has Overleaf issue a *fresh* load-balancer affinity cookie
        # (currently named GCLB, see olbrowserlogin.COOKIE_NAMES and commit
        # 0cc61e7) on its response -- but socketIO_client calls requests.get()
        # directly rather than through a Session, so that Set-Cookie is silently
        # dropped, and the WebSocket upgrade that follows then 502s without it.
        # Perform the same handshake ourselves first, purely to capture that
        # cookie, and merge it into the header used for the real connection.
        # (Built from whatever cookies are present rather than hardcoded names:
        # a session may not carry every cookie -- this previously raised
        # KeyError here even though overleaf_session2 alone is enough to connect.)
        handshake = reqs.get(
            "{}/socket.io/1/".format(BASE_URL),
            params={"t": int(time.time() * 1000)},
            cookies=self._cookie,
        )
        cookie_dict = dict(self._cookie)
        cookie_dict.update(handshake.cookies.get_dict())
        cookie = "; ".join(
            "{}={}".format(name, value) for name, value in cookie_dict.items()
        )

        # projectId must be a query parameter on THIS handshake -- the one
        # socketIO_client performs internally when SocketIO() connects, not
        # the pre-fetch above. Overleaf now binds the session to a project at
        # handshake time and rejects the connection otherwise
        # (connectionRejected: "missing/bad ?projectId=... query flag on
        # handshake"); confirmed it rejects even when projectId is only on
        # the WebSocket upgrade URL -- it must be on the initial
        # /socket.io/1/ GET specifically.
        socket_io = SocketIO(
            BASE_URL,
            params={'t': int(time.time()), 'projectId': project_id},
            headers={'Cookie': cookie}
        )

        # Wait until we connect to the socket
        socket_io.on('connect', lambda: None)
        socket_io.wait_for_callbacks()

        # With projectId on the handshake, the server auto-joins and pushes
        # the result as a joinProjectResponse event -- no explicit joinProject
        # emit needed (confirmed live: the emit's ack callback never fires
        # since the server responds with a named event, not an ack).
        # wait_for_callbacks() only waits for a pending *ack* callback, which
        # .on() never registers -- it would return immediately without
        # reading anything. Wait in short slices instead, stopping as soon as
        # the event has actually been processed.
        socket_io.on('joinProjectResponse', set_project_infos)
        for _ in range(20):
            if project_infos is not None:
                break
            socket_io.wait(seconds=1)

        # Disconnect from the socket if still connected
        if socket_io.connected:
            socket_io.disconnect()

        return project_infos

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
        folder_id = project_infos['rootFolder'][0]['_id']

        # The file name contains path separators, check folders
        if PATH_SEP in file_name:
            local_folders = file_name.split(PATH_SEP)[:-1]  # Remove last item since this is the file name
            current_overleaf_folder = project_infos['rootFolder'][0]['folders']  # Set the current remote folder

            for local_folder in local_folders:
                exists_on_remote = False
                for remote_folder in current_overleaf_folder:
                    # Check if the folder exists on remote, continue with the new folder structure
                    if local_folder.lower() == remote_folder['name'].lower():
                        exists_on_remote = True
                        folder_id = remote_folder['_id']
                        current_overleaf_folder = remote_folder['folders']
                        break
                # Create the folder if it doesn't exist
                if not exists_on_remote:
                    new_folder = self.create_folder(project_id, folder_id, local_folder)
                    current_overleaf_folder.append(new_folder)
                    folder_id = new_folder['_id']
                    current_overleaf_folder = new_folder['folders']
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
            "qqfile": file
        }

        # Upload the file to the predefined folder
        r = reqs.post(UPLOAD_URL.format(project_id), cookies=self._cookie, params=params, files=files)

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

        file = None

        # The file name contains path separators, check folders
        if PATH_SEP in file_name:
            local_folders = file_name.split(PATH_SEP)[:-1]  # Remove last item since this is the file name
            current_overleaf_folder = project_infos['rootFolder'][0]['folders']  # Set the current remote folder

            for local_folder in local_folders:
                for remote_folder in current_overleaf_folder:
                    if local_folder.lower() == remote_folder['name'].lower():
                        file = next((v for v in remote_folder['docs'] if v['name'] == file_name.split(PATH_SEP)[-1]),
                                    None)
                        current_overleaf_folder = remote_folder['folders']
                        break
        # File is in root folder
        else:
            file = next((v for v in project_infos['rootFolder'][0]['docs'] if v['name'] == file_name), None)

        # File not found!
        if file is None:
            return False

        headers = {
            "X-Csrf-Token": self._csrf
        }

        r = reqs.delete(DELETE_URL.format(project_id, file['_id']), cookies=self._cookie, headers=headers, json={})

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
        headers = {
            "X-Csrf-Token": self._csrf
        }

        body = {
            "check": "silent",
            "draft": False,
            "incrementalCompilesEnabled": True,
            "rootDoc_id": "",
            "stopOnFirstError": False
        }

        r = reqs.post(COMPILE_URL.format(project_id), cookies=self._cookie, headers=headers, json=body)

        if not r.ok:
            raise reqs.HTTPError()

        compile_result = json.loads(r.content)

        if compile_result["status"] != "success":
            raise reqs.HTTPError()

        pdf_file = next(v for v in compile_result['outputFiles'] if v['type'] == 'pdf')

        download_req = reqs.get(BASE_URL + pdf_file['url'], cookies=self._cookie, headers=headers)

        if download_req.ok:
            return pdf_file['path'], download_req.content

        return None
