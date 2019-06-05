"""Overleaf Two-Way Sync Tool"""
##################################################
# MIT License
##################################################
# File: olclient.py
# Description: Overleaf API Wrapper
# Author: Moritz Glöckl
# License: MIT
# Version: 1.0.0
##################################################

import requests as reqs
from bs4 import BeautifulSoup
import json
import uuid

LOGIN_URL = "https://www.overleaf.com/login"  # Where to get the CSRF Token and where to send the login request to
PROJECT_URL = "https://www.overleaf.com/project"  # The dashboard URL
DOWNLOAD_URL = "https://www.overleaf.com/project/{}/download/zip"  # The URL to download all the files in zip format
UPLOAD_URL = "https://www.overleaf.com/project/{}/upload"  # The URL to upload files


class OverleafClient(object):
    """
    Overleaf API Wrapper
    Supports login, querying all projects, querying a specific project, downloading a project and
    uploading a file to a project.
    """

    def __init__(self, cookie=None, csrf=None):
        self._cookie = cookie  # Store the cookie for authenticated requests
        self._csrf = csrf  # Store the CSRF token since it is needed for some requests

    def login(self, username, password):
        """
        Login to the Overleaf Service with a username and a password
        Params: username, password
        Returns: Dict of cookie and CSRF
        """

        get_login = reqs.get(LOGIN_URL)
        self._csrf = BeautifulSoup(get_login.content, 'html.parser').find('input', {'name': '_csrf'}).get('value')
        login_json = {
            "_csrf": self._csrf,
            "email": username,
            "password": password
        }
        post_login = reqs.post(LOGIN_URL, json=login_json, cookies=get_login.cookies)

        # On a successful authentication the Overleaf API returns a new authenticated cookie.
        # If the cookie is different than the cookie of the GET request the authentication was successful
        if post_login.status_code == 200 and get_login.cookies["overleaf_session"] != post_login.cookies[
            "overleaf_session"]:
            self._cookie = post_login.cookies
            return {"cookie": self._cookie, "csrf": self._csrf}

    def all_projects(self):
        """
        Get all of a user's active projects (= not archived)
        Returns: List of project objects
        """
        projects_page = reqs.get(PROJECT_URL, cookies=self._cookie)
        json_content = json.loads(
            BeautifulSoup(projects_page.content, 'html.parser').find('script', {'id': 'data'}).contents[0])
        return list(filter(lambda x: not x.get("archived"), json_content.get("projects")))

    def get_project(self, project_name):
        """
        Get a specific project by project_name
        Params: project_name, the name of the project
        Returns: project object
        """
        projects_page = reqs.get(PROJECT_URL, cookies=self._cookie)
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
        r = reqs.get(DOWNLOAD_URL.format(project_id), stream=True, cookies=self._cookie)
        return r.content

    def upload_file(self, project_id, file_name, file_size, file):
        """
        Upload a file to the project
        Params: project_id, the id of the project, file_name, how the file will be named, file_size, the size of the
                file in bytes, file, the file itself
        Returns: True on success, False on fail
        """

        # To get the folder_id, we convert the hex project_id to int, subtract 1 and convert it back to hex
        params = {
            "folder_id": format(int(project_id, 16) - 1, 'x'),
            "_csrf": self._csrf,
            "qquuid": str(uuid.uuid4()),
            "qqfilename": file_name,
            "qqtotalfilesize": file_size,
        }
        files = {
            "qqfile": file
        }
        r = reqs.post(UPLOAD_URL.format(project_id), cookies=self._cookie, params=params, files=files)
        return r.status_code == 200 and json.loads(r.content)["success"]
