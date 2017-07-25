import mock
import stashy
import time
import yaml

from datetime import datetime
from datetime import timedelta
from pybitbucket.ref import Branch
from pybitbucket.user import User
from repository_sensor import RepositorySensor
from st2tests.base import BaseSensorTestCase


class RepositorySensorTestCase(BaseSensorTestCase):
    sensor_cls = RepositorySensor

    def filter_payload(self, contexts, k, v):
        return [x['payload']['payload'] for x in contexts if x['payload']['payload'][k] == v]

    def get_mock_commits_for_server(self, commit_num):
        return [{
            'id': index,
            'message': 'commit-%d' % index,
            'authorTimestamp': int(round((time.time() + index * 100) * 1000)),
            'author': {'emailAddress': 'test@test.local'},
        } for index in range(commit_num, 0, -1)]

    def client_mock_for_server(self):
        def get_mock(name):
            return self.client_mock_for_server()

        def get_branches():
            return [
                {'displayId': 'master', 'id': 'master', 'latestCommit': 1},
                {'displayId': 'dev', 'id': 'dev', 'latestCommit': 2},
            ]

        def get_commits(_branch):
            for commit in self.dummy_commits:
                time.sleep(self.delay)
                yield commit

        client = mock.MagicMock()
        client.projects.__getitem__.side_effect = get_mock
        client.repos.__getitem__.side_effect = get_mock
        client.branches.side_effect = get_branches
        client.commits.side_effect = get_commits

        return client

    def setUp(self):
        super(RepositorySensorTestCase, self).setUp()

        self.cfg_server = yaml.safe_load(self.get_fixture_content('cfg_server.yaml'))
        self.cfg_cloud = yaml.safe_load(self.get_fixture_content('cfg_cloud.yaml'))

    def test_dispatching_commit_from_server(self):
        # set variables for Bitbucket Server test
        self.dummy_commits = self.get_mock_commits_for_server(3)
        self.delay = 0

        sensor = self.get_sensor_instance(config=self.cfg_server)

        with mock.patch.object(stashy, 'connect',
                               mock.Mock(return_value=self.client_mock_for_server())):
            # setup repository_sensor to monitor BitBucket server
            sensor.setup()

            # check commits in the target repositories and dispatch them
            sensor.poll()

        contexts = self.get_dispatched_triggers()

        self.assertEqual(len(contexts), 4)

        payloads = self.filter_payload(contexts, 'branch', 'master')
        self.assertEqual(len(payloads), 2)
        self.assertEqual([len(x['commits']) for x in payloads], [2, 2])

        payloads = self.filter_payload(contexts, 'branch', 'dev')
        self.assertEqual(len(payloads), 2)
        self.assertEqual([len(x['commits']) for x in payloads], [1, 1])

    def test_dispatching_commit_from_server_with_timeout(self):
        # set variables for Bitbucket Server test
        self.dummy_commits = self.get_mock_commits_for_server(100)
        self.delay = 0

        sensor = self.get_sensor_instance(config=self.cfg_server)

        with mock.patch.object(stashy, 'connect',
                               mock.Mock(return_value=self.client_mock_for_server())):
            # setup repository_sensor to monitor BitBucket server
            sensor.setup()

            # set delay and modify timeout-setting for testing
            # this settings restrict payload number less than 10
            self.delay = 0.1
            sensor.TIMEOUT_SECONDS = 1

            # check commits in the target repositories and dispatch them
            sensor.poll()
            contexts_first = self.get_dispatched_triggers()

            # clear dispatch_triggers for getting rest update information in the next polling
            self.sensor_service.dispatched_triggers = []

            # get commits that could not acquired due to the timeout
            sensor.poll()
            contexts_second = self.get_dispatched_triggers()

        self.assertEqual(len(contexts_first), 1)

        # If all commits are dispatched in the first polling processing, this value will be 0
        self.assertEqual(len(contexts_second), 1)
        self.assertTrue(len(contexts_first[0]['payload']['payload']) <= 10)

        # checking duplicated payload isn't sent in the second dispatching
        p1 = contexts_first[0]['payload']['payload']
        p2 = contexts_second[0]['payload']['payload']
        for (r, b) in set([(x['repository'], x['branch']) for x in p1['commits']]):
            self.assertEqual(filter(lambda x: x['repository'] == r and x['branch'] == b,
                                    p2['commits']), [])

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
        self.assertEqual(len(contexts), 2)

        payloads = self.filter_payload(contexts, 'branch', 'master')
        self.assertEqual(len(payloads), 2)
        self.assertEqual([len(x['commits']) for x in payloads], [2, 2])

        payloads = self.filter_payload(contexts, 'branch', 'dev')
        self.assertEqual(len(payloads), 0)


class MockCommit(object):
    def __init__(self, id, author):
        self.hash = id
        self.message = 'commit-%d' % id
        self.author = author
        self.date = (datetime.now() + timedelta(seconds=id)).strftime('%Y-%m-%dT%H:%M:%SZ')
