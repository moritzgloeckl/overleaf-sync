"""Overleaf Client"""
##################################################
# MIT License
##################################################
# File: test_olclient.py
# Description: Overleaf API Wrapper Tests
# Author: Moritz Glöckl
# License: MIT
# Version: 1.1.4
##################################################

import unittest
import mock
import responses
from requests import HTTPError
from olsync.olclient import OverleafClient


class TestOlClient(unittest.TestCase):

    def test_filter_projects(self):
        project_a = {"id": "a", "name": "Project A", "archived": False, "trashed": False}
        project_b = {"id": "b", "name": "Project B", "archived": True, "trashed": False}
        project_c = {"id": "c", "name": "Project C", "archived": False, "trashed": True}
        project_d = {"id": "d", "name": "Project D", "archived": False, "trashed": False}
        projects = [project_a, project_b, project_c, project_d]

        self.assertEqual(list(OverleafClient.filter_projects(projects))[0]["id"], "a", "Should be Project A")
        self.assertEqual(list(OverleafClient.filter_projects(projects, {'name': 'Project D'}))[0]["id"], "d",
                         "Should be Project D")

    @responses.activate
    def test_login(self):
        def get_request_callback(request):
            return (
                200,
                [
                    ("set-cookie", "overleaf_session2=AABBCC123"),
                    ("set-cookie", "GCLB=GGCCLLBB123"),
                ],
                b"<input name='_csrf' type='hidden' value='AAABBB123_CCC' autocomplete='off'>")

        responses.add_callback(responses.GET, 'https://www.overleaf.com/login', get_request_callback)
        responses.add(responses.POST, 'https://www.overleaf.com/login',
                      status=200,
                      headers={"set-cookie": "overleaf_session2=ovlsess2"})
        responses.add(responses.GET, 'https://www.overleaf.com/project',
                      status=200,
                      body='<meta name="ol-csrfToken" content="AAA123">')

        overleaf_client = OverleafClient()
        response = overleaf_client.login("a@a.a", "a")

        self.assertEqual(response["csrf"], "AAA123", "Should contain correct csrf")
        self.assertEqual(response["cookie"]["GCLB"], "GGCCLLBB123", "Should contain correct GCLB")
        self.assertEqual(response["cookie"]["overleaf_session2"], "ovlsess2",
                         "Should contain correct overleaf_session2")

    @responses.activate
    def test_all_projects(self):
        body = b'<meta name="ol-projects" data-type="json" content=\'[{"id": "a", "name": "Project A", "archived": ' \
               b'false, "trashed": false}, {"id": "b", "name": "Project B", "archived": false, "trashed": false}]\'> '
        responses.add(responses.GET, 'https://www.overleaf.com/project', status=200, body=body)
        overleaf_client = OverleafClient()
        response = overleaf_client.all_projects()

        self.assertEqual(response[0]["id"], "a", "Should return the project A")
        self.assertEqual(response[1]["id"], "b", "Should return the project B")

    @responses.activate
    def test_get_project(self):
        body = b'<meta name="ol-projects" data-type="json" content=\'[{"id": "a", "name": "Project A", "archived": ' \
               b'false, "trashed": false}, {"id": "b", "name": "Project B", "archived": false, "trashed": false}]\'> '
        responses.add(responses.GET, 'https://www.overleaf.com/project', status=200, body=body)
        overleaf_client = OverleafClient()
        response = overleaf_client.get_project("Project B")

        self.assertEqual(response["id"], "b", "Should return the project B")

    @responses.activate
    def test_download_project(self):
        body = b'aabbcc'
        responses.add(responses.GET, 'https://www.overleaf.com/project/projecta/download/zip', status=200, body=body)
        overleaf_client = OverleafClient()
        response = overleaf_client.download_project("projecta")

        self.assertEqual(response, b"aabbcc", "Should return content of project A")

    @responses.activate
    def test_create_folder(self):
        overleaf_client = OverleafClient()
        responses.add(
            responses.POST,
            'https://www.overleaf.com/project/projecta/folder',
            status=200,
            body=b'{ \"_id\": \"aabbcc\" }',
            match=[
                responses.json_params_matcher({"parent_folder_id": "abc", "name": "test folder"})
            ]
        )
        response = overleaf_client.create_folder("projecta", "abc", "test folder")
        self.assertEqual(response, "aabbcc", "Should return folder id of created folder")

        responses.replace(
            responses.POST,
            'https://www.overleaf.com/project/projecta/folder',
            status=400,
            match=[
                responses.json_params_matcher({"parent_folder_id": "abc", "name": "test folder"})
            ]
        )
        response = overleaf_client.create_folder("projecta", "abc", "test folder")
        self.assertEqual(response, None, "Should return None if folder exists")

        responses.replace(
            responses.POST,
            'https://www.overleaf.com/project/projecta/folder',
            status=403,
            match=[
                responses.json_params_matcher({"parent_folder_id": "abc", "name": "test folder"})
            ]
        )
        try:
            overleaf_client.create_folder("projecta", "abc", "test folder")
            self.fail()
        except HTTPError as e:
            self.assertNotEqual(e, None)

    @mock.patch('olsync.olclient.reqs.utils.dict_from_cookiejar',
                mock.MagicMock(return_value={"GCLB": "ggccllbb", "overleaf_session2": "ovlfsess2"}))
    @mock.patch('olsync.olclient.SocketIO')
    def test_get_project_infos(self, mocked_socket):
        socket_io_instance = mocked_socket.return_value
        socket_io_instance.connected.return_value = True

        overleaf_client = OverleafClient()
        project_infos = overleaf_client.get_project_infos("projecta")
        mocked_socket.assert_called_with(
            'https://www.overleaf.com',
            params={'t': mock.ANY},
            headers={'Cookie': 'GCLB=ggccllbb; overleaf_session2=ovlfsess2'}
        )
        socket_io_instance.on.assert_called_once_with('connect', mock.ANY)
        self.assertEqual(socket_io_instance.wait_for_callbacks.call_count, 2, "Should be called twice")
        socket_io_instance.emit.assert_called_once_with('joinProject', {'project_id': "projecta"}, mock.ANY)
        socket_io_instance.disconnect.assert_called_once()

    @mock.patch('olsync.olclient.uuid.uuid4', mock.MagicMock(return_value="uuidAABBCC"))
    @responses.activate
    def test_upload_file(self):
        responses.add(
            responses.POST,
            'https://www.overleaf.com/project/projecta/upload?folder_id=fold1&_csrf=ccssrrff&qquuid=uuidAABBCC'
            '&qqfilename=File+A&qqtotalfilesize=1000',
            status=200,
            body='{ "success": true }',
            match_querystring=True
        )
        overleaf_client = OverleafClient()
        overleaf_client._csrf = "ccssrrff"
        response = overleaf_client.upload_file("projecta", {'rootFolder': [{'_id': 'fold1'}]}, "File A", 1000, "a")
        self.assertTrue(response, "Should return positive success state")


if __name__ == '__main__':
    unittest.main()
