import mock
import stashy
import time
import yaml

from datetime import datetime
from pybitbucket.ref import Branch
from pybitbucket.user import User
from repository_sensor import RepositorySensor
from st2tests.base import BaseSensorTestCase


class RepositorySensorTestCase(BaseSensorTestCase):
    sensor_cls = RepositorySensor

    def client_mock_for_server(self):
        def get_mock(name):
            return self.client_mock_for_server()

        def get_branches():
            return [
                {'displayId': 'master', 'id': 'master', 'latestCommit': 1},
                {'displayId': 'dev', 'id': 'dev', 'latestCommit': 2},
            ]

        def get_commits(_branch):
            for index in range(3, 0, -1):
                yield {
                    'id': index,
                    'message': 'commit-%d' % index,
                    'authorTimestamp': int(round(time.time() * 1000)),
                    'author': {'emailAddress': 'test@test.local'},
                }

        client = mock.MagicMock()
        client.projects.__getitem__.side_effect = get_mock
        client.repos.__getitem__.side_effect = get_mock
        client.branches.side_effect = get_branches
        client.commits.side_effect = get_commits

        return client

    def client_mock_for_cloud(self):
        return mock.Mock()

    def setUp(self):
        super(RepositorySensorTestCase, self).setUp()

        self.cfg_server = yaml.safe_load(self.get_fixture_content('cfg_server.yaml'))
        self.cfg_cloud = yaml.safe_load(self.get_fixture_content('cfg_cloud.yaml'))

    def test_dispatching_commit_from_server(self):
        sensor = self.get_sensor_instance(config=self.cfg_server)

        with mock.patch.object(stashy, 'connect',
                               mock.Mock(return_value=self.client_mock_for_server())):
            # setup repository_sensor to monitor BitBucket server
            sensor.setup()

            # check commits in the target repositories and dispatch them
            sensor.poll()

        contexts = self.get_dispatched_triggers()
        self.assertEqual(len(contexts), 6)
        self.assertEqual(len(filter(lambda x: x['payload']['payload']['branch'] == 'master',
                                    contexts)), 4)
        self.assertEqual(len(filter(lambda x: x['payload']['payload']['branch'] == 'dev',
                                    contexts)), 2)
        self.assertEqual(len(filter(lambda x: x['payload']['payload']['msg'] == 'commit-3',
                                    contexts)), 4)
        self.assertEqual(len(filter(lambda x: x['payload']['payload']['msg'] == 'commit-2',
                                    contexts)), 2)
        self.assertTrue(all([isinstance(x['payload']['payload']['time'], str) for x in contexts]))

    def test_dispatching_commit_from_cloud(self):
        sensor = self.get_sensor_instance(config=self.cfg_cloud)

        # prepare mock user
        user1 = mock.Mock(spec=User)
        user1.username = 'user1'

        branch1 = mock.Mock(spec=Branch)
        branch1.name = 'master'
        branch1.commits = lambda: [(yield MockCommit(x, user1)) for x in range(2, 0, -1)]

        branch2 = mock.Mock(spec=Branch)
        branch2.name = 'dev'
        branch2.commits = lambda: [(yield MockCommit(x, {'raw': 'user2'})) for x in range(3, 0, -1)]

        mock_branches = [branch1, branch2]
        with mock.patch.object(Branch, 'find_branches_in_repository',
                               mock.Mock(return_value=mock_branches)):
            # setup repository_sensor to monitor BitBucket server
            sensor.setup()

            # update commits of 'master' branch
            branch1.commits = lambda: [(yield MockCommit(x, user1)) for x in range(4, 0, -1)]

            # check commits in the target repositories and dispatch them
            sensor.poll()

        contexts = self.get_dispatched_triggers()
        self.assertEqual(len(contexts), 4)
        self.assertEqual(len(filter(lambda x: x['payload']['payload']['branch'] == 'master',
                                    contexts)), 4)
        self.assertEqual(len(filter(lambda x: x['payload']['payload']['branch'] == 'dev',
                                    contexts)), 0)
        self.assertEqual(len(filter(lambda x: x['payload']['payload']['msg'] == 'commit-4',
                                    contexts)), 2)
        self.assertEqual(len(filter(lambda x: x['payload']['payload']['msg'] == 'commit-3',
                                    contexts)), 2)
        self.assertTrue(all([isinstance(x['payload']['payload']['time'], str) for x in contexts]))


class MockCommit(object):
    def __init__(self, id, author):
        self.hash = id
        self.message = 'commit-%d' % id
        self.author = author
        self.date = datetime.now().strftime('%Y-%m-%dT%H:%M:%SZ')
