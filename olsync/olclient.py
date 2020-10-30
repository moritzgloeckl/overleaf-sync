"""Overleaf Client"""
##################################################
# MIT License
##################################################
# File: olclient.py
# Description: Overleaf API Wrapper
# Author: Moritz Glöckl
# License: MIT
# Version: 1.1.1
##################################################

import requests as reqs
from bs4 import BeautifulSoup
import json
import uuid
from socketIO_client import SocketIO
import time

class OverleafClient(object):
    """
    Overleaf API Wrapper
    Supports login, querying all projects, querying a specific project, downloading a project and
    uploading a file to a project.
    """
    _ce = False

    def __init__(self, cookie=None, csrf=None, ce_url=None):
        self._cookie = cookie  # Store the cookie for authenticated requests
        self._csrf = csrf  # Store the CSRF token since it is needed for some requests

        # Where to get the CSRF Token and where to send the login request to
        if ce_url != None:
            self._ce = True
            self._BASE_URL = ce_url
        else:
            self._BASE_URL = "https://www.overleaf.com"  # The Overleaf Base URL

        self._LOGIN_URL = self._BASE_URL + "/login"
        self._PROJECT_URL = self._BASE_URL + "/project"  # The dashboard URL
        # The URL to download all the files in zip format
        self._DOWNLOAD_URL = self._BASE_URL + "/project/{}/download/zip"
        self._UPLOAD_URL = self._BASE_URL + "/project/{}/upload"  # The URL to upload files
        self._FOLDER_URL = self._BASE_URL + "/project/{}/folder"  # The URL to create folders

    def login(self, username, password):
        """
        Login to the Overleaf Service with a username and a password
        Params: username, password
        Returns: Dict of cookie and CSRF
        """

        get_login = reqs.get(self._LOGIN_URL)
        self._csrf = BeautifulSoup(get_login.content, 'html.parser').find(
            'input', {'name': '_csrf'}).get('value')
        login_json = {
            "_csrf": self._csrf,
            "email": username,
            "password": password
        }
        post_login = reqs.post(self._LOGIN_URL, json=login_json,
                               cookies=get_login.cookies)

        # On a successful authentication the Overleaf API returns a new authenticated cookie.
        # If the cookie is different than the cookie of the GET request the authentication was successful
        if post_login.status_code == 200 and ((self._ce and get_login.cookies["sharelatex.sid"] != post_login.cookies[
            "sharelatex.sid"]) or get_login.cookies["overleaf_session2"] != post_login.cookies[
            "overleaf_session2"]):

            self._cookie = post_login.cookies

            if not self._ce:
                # Enrich cookie with gke-route cookie from GET request above
                self._cookie['gke-route'] = get_login.cookies['gke-route']

            return {"cookie": self._cookie, "csrf": self._csrf}

    def all_projects(self):
        """
        Get all of a user's active projects (= not archived)
        Returns: List of project objects
        """
        projects_page = reqs.get(self._PROJECT_URL, cookies=self._cookie)
        json_content = json.loads(
            BeautifulSoup(projects_page.content, 'html.parser').find('script', {'id': 'data'}).contents[0])
        return list(filter(lambda x: not x.get("archived"), json_content.get("projects")))

    def get_project(self, project_name):
        """
        Get a specific project by project_name
        Params: project_name, the name of the project
        Returns: project object
        """

        projects_page = reqs.get(self._PROJECT_URL, cookies=self._cookie)
        json_content = json.loads(
            BeautifulSoup(projects_page.content, 'html.parser').find('script', {'id': 'data'}).contents[0])
        return next(
            filter(lambda x: not x.get("archived") and x.get("name") == project_name, json_content.get("projects")),
            None)

    def download_project(self, project_id):
        """
        Download project in zip format
        Params: project_id, the id of the project
        Returns: bytes string (zip file)
        """
        r = reqs.get(self._DOWNLOAD_URL.format(project_id),
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
            "_csrf": self._csrf,
            "name": folder_name
        }
        r = reqs.post(self._FOLDER_URL.format(project_id),
                      cookies=self._cookie, json=params)

        if r.ok:
            return json.loads(r.content)["_id"]
        elif r.status_code == str(400):
            # Folder already exists
            return

    def get_project_infos(self, project_id):
        """
        Get detailed project infos about the project

        Params:
        project_id: the id of the project

        Returns: project details
        """
        project_infos = None

        # Callback function for the joinProject emitter
        def set_project_infos(a, project_infos_dict, c, d):
            # Set project_infos variable in outer scope
            nonlocal project_infos
            project_infos = project_infos_dict

        # Convert cookie from CookieJar to string
        cookie = None
        if self._ce:
            cookie = "sharelatex.sid={}" \
                .format(
                    reqs.utils.dict_from_cookiejar(self._cookie)["sharelatex.sid"]
                )
        else:
            cookie = "gke-route={}; overleaf_session2={}" \
                .format(
                    reqs.utils.dict_from_cookiejar(self._cookie)["gke-route"],
                    reqs.utils.dict_from_cookiejar(self._cookie)["overleaf_session2"]
                )

        # Connect to Overleaf Socket.IO, send a time parameter and the cookies
        socket_io = SocketIO(
            self._BASE_URL,
            params={'t': int(time.time())},
            headers={'Cookie': cookie}
        )

        # Wait until we connect to the socket
        socket_io.on('connect', lambda: None)
        socket_io.wait_for_callbacks()

        # Send the joinProject event and receive the project infos
        socket_io.emit('joinProject', {'project_id': project_id}, set_project_infos)
        socket_io.wait_for_callbacks()

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
        if "/" in file_name:
            local_folders = file_name.split("/")[:-1]  # Remove last item since this is the file name
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
                    folder_id = self.create_folder(project_id, folder_id, local_folder)

        params = {
            "folder_id": folder_id,
            "_csrf": self._csrf,
            "qquuid": str(uuid.uuid4()),
            "qqfilename": file_name,
            "qqtotalfilesize": file_size,
        }
        files = {
            "qqfile": file
        }

        # Upload the file to the predefined folder
        r = reqs.post(self._UPLOAD_URL.format(project_id), cookies=self._cookie, params=params, files=files)

        return r.status_code == str(200) and json.loads(r.content)["success"]
