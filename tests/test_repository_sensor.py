import mock
import stashy
import time
import json
import yaml

from datetime import datetime
from datetime import timedelta
from pybitbucket.commit import Commit
from pybitbucket.user import User
from repository_sensor import RepositorySensor
from st2tests.base import BaseSensorTestCase


class RepositorySensorTestCase(BaseSensorTestCase):
    sensor_cls = RepositorySensor

    def filter_payload(self, contexts, k, v):
        return [x['payload']['payload'] for x in contexts if x['payload']['payload'][k] == v]

    def client_mock_for_server(self):
        def get_mock(name):
            return self.client_mock_for_server()

        def get_commits(_branch):
            for commit in self.dummy_commits:
                time.sleep(self.delay)
                yield commit

        mock_response = mock.Mock()
        mock_response.content = json.dumps({
            'values': [
                {
                    'type': 'ADD',
                    'path': {'toString': 'foo/bar'},
                },
                {
                    'type': 'MOVE',
                    'path': {'toString': 'foo/baz'},
                },
                {
                    'type': 'DELETE',
                    'path': {'toString': 'abcd'},
                },
                {
                    'type': 'MODIFY',
                    'path': {'toString': 'hoge'},
                },
                {
                    'type': 'MODIFY',
                    'path': {'toString': 'fuga'},
                },
            ],
        })

        client = mock.MagicMock()
        client.projects.__getitem__.side_effect = get_mock
        client.repos.__getitem__.side_effect = get_mock
        client.commits.side_effect = get_commits
        client._client.get.return_value = mock_response

        return client

    def setUp(self):
        super(RepositorySensorTestCase, self).setUp()

        self.cfg_server = yaml.safe_load(self.get_fixture_content('cfg_server.yaml'))
        self.cfg_cloud = yaml.safe_load(self.get_fixture_content('cfg_cloud.yaml'))

    def test_dispatching_commit_from_server(self):
        # set variables for Bitbucket Server test
        self.dummy_commits = MockCommitsForServer(3, {'emailAddress': 'test@test.local'})
        self.delay = 0

        sensor = self.get_sensor_instance(config=self.cfg_server)

        with mock.patch.object(stashy, 'connect',
                               mock.Mock(return_value=self.client_mock_for_server())):
            # setup repository_sensor to monitor BitBucket server
            sensor.setup()

            # add a commit after finishing the setup()
            self.dummy_commits.insert_commit(1)

            # check commits in the target repositories and dispatch them
            sensor.poll()

        contexts = self.get_dispatched_triggers()

        # Sensor monitors the commits each repositories which are specified in the configuration
        self.assertEqual(len(contexts), 3)

        payloads = self.filter_payload(contexts, 'branch', 'master')
        self.assertEqual(len(payloads), 2)

        self.assertEqual([len(x['commits']) for x in payloads], [1, 1])
        self.assertTrue(any([x['repository'] == 'foo/bar' for x in payloads]))
        self.assertTrue(any([x['repository'] == 'hoge/fuga' for x in payloads]))

        payloads = self.filter_payload(contexts, 'branch', 'dev')
        self.assertEqual(len(payloads), 1)
        self.assertEqual([len(x['commits']) for x in payloads], [1])
        self.assertEqual(payloads[0]['repository'], 'hoge/fuga')

        # checks that commit info has expected parameters
        commit_keys = ['repository', 'branch', 'author', 'time', 'msg']
        self.assertTrue(all([x in payloads[0]['commits'][0]] for x in commit_keys))

        # checks that payloads has the information about the changed files
        changing_types = ['added', 'moved', 'deleted', 'modified']
        changing_files = payloads[0]['changed_files']

        self.assertTrue(all([key in changing_files for key in changing_types]))
        self.assertEqual(changing_files['added'], ['foo/bar'])
        self.assertEqual(changing_files['moved'], ['foo/baz'])
        self.assertEqual(changing_files['deleted'], ['abcd'])
        self.assertEqual(sorted(changing_files['modified']), sorted(['hoge', 'fuga']))

    def test_dispatching_commit_from_server_with_timeout(self):
        # set variables for Bitbucket Server test
        self.dummy_commits = MockCommitsForServer(3, {'emailAddress': 'test@test.local'})
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

            # add large amount of commits that can't be fully processed
            for i in range(100, 1, -1):
                self.dummy_commits.insert_commit(i)

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

        commits_baz_master = MockCommitsForCloud(2, user1)
        commits_puyo_master = MockCommitsForCloud(3, user1)
        commits_puyo_dev = MockCommitsForCloud(4, {'raw': 'user2'})

        def side_effect(username, repository_name, branch, client):
            if repository_name == 'baz' and branch == 'master':
                return commits_baz_master
            elif repository_name == 'puyo' and branch == 'master':
                return commits_puyo_master
            elif repository_name == 'puyo' and branch == 'dev':
                return commits_puyo_dev

        with mock.patch.object(Commit, 'find_commits_in_repository',
                               mock.Mock(side_effect=side_effect)):
            # setup repository_sensor to monitor BitBucket server
            sensor.setup()

            # update commits except for 'dev' branch of 'fuga/puyo' repository
            commits_baz_master.insert_commit(1)
            commits_puyo_master.insert_commit(1)

            # check commits in the target repositories and dispatch them
            sensor.poll()

        contexts = self.get_dispatched_triggers()

        # Trigger is going to dispatch three times every following (repository, branch) sets.
        # - ('bar/baz', 'master')
        # - ('fuga/puyo', 'master')
        self.assertEqual(len(contexts), 2)
        self.assertEqual(len(self.filter_payload(contexts, 'repository', 'bar/baz')), 1)
        self.assertEqual(len(self.filter_payload(contexts, 'repository', 'fuga/puyo')), 1)
        self.assertEqual(len(self.filter_payload(contexts, 'branch', 'master')), 2)
        self.assertEqual(len(self.filter_payload(contexts, 'branch', 'dev')), 0)

        # checks that commit info has expected parameters
        commit_keys = ['repository', 'branch', 'author', 'time', 'msg']
        commit_info = self.filter_payload(contexts, 'branch', 'master')[0]['commits'][0]
        self.assertTrue(all([x in commit_info for x in commit_keys]))


class MockCommits(object):
    def __init__(self, count, author, commit_model):
        self.commits = []
        self.index = 0
        self.author = author
        self.model = commit_model

        for x in range(0, count):
            self.commits.append(self.model(x, self.author, self.index * -1))

    def __iter__(self):
        self.index = 0
        return self

    def next(self):
        if self.index >= len(self.commits):
            raise StopIteration()
        value = self.commits[self.index]
        self.index += 1
        return value

    def insert_commit(self, delta_seconds=0):
        self.commits.insert(0, self.model(len(self.commits), self.author, delta_seconds))


class MockCommitsForServer(MockCommits):
    class CommitModel(object):
        def __init__(self, index, author, delta_seconds):
            self.data = {
                'id': '0123456789abcdefghijklmnopqrstuvwxyzABCD',
                'message': 'commit-%d' % index,
                'authorTimestamp': int(round((time.time() + delta_seconds * 100) * 1000)),
                'author': author,
            }

        def __getitem__(self, key):
            return self.data[key]

    def __init__(self, count, author):
        super(MockCommitsForServer, self).__init__(count, author, self.CommitModel)


class MockCommitsForCloud(MockCommits):
    class CommitModel(object):
        def __init__(self, index, author, delta_seconds):
            commit_time = (datetime.now() +
                           timedelta(seconds=delta_seconds)).strftime('%Y-%m-%dT%H:%M:%SZ')

            self.message = 'commit-%d' % index
            self.author = author
            self.date = commit_time

    def __init__(self, count, author):
        super(MockCommitsForCloud, self).__init__(count, author, self.CommitModel)
