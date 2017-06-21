import stashy

from pybitbucket.bitbucket import Client 
from pybitbucket.auth import BasicAuthenticator
from pybitbucket.repository import Repository

from datetime import datetime

from st2reactor.sensor.base import PollingSensor


class RepositorySensor(PollingSensor):
    DATE_FORMAT = '%Y-%m-%d %H:%M:%S'

    def __init__(self, sensor_service, config=None, poll_interval=None):
        super(RepositorySensor, self).__init__(sensor_service=sensor_service,
                                                     config=config,
                                                     poll_interval=poll_interval)
        self._trigger_ref = 'bitbucket.repository_event'
        self._logger = self._sensor_service.get_logger(__name__)
        self.last_commit = {}

    def setup(self):
        sensor_config = self._config.get('sensor', None)
        if not sensor_config:
            raise ValueError('"sensor" config value is required')

        # validate the format of all repository names 
        self.repositories = sensor_config.get('repositories')
        if not self.repositories:
            raise ValueError('"repositories" parameter in the "sensor" is required')

        if not all([len(x.split('/')) == 2 for x in self.repositories]):
            raise ValueError('Invalid repository name is specified in the "repositories" parameter')

        # initialize global parameter
        self.commits = {}

        self.service_type = sensor_config.get('bitbucket_type', '')
        if self.service_type == 'server':
            # initialization for BitBucket Server
            self.client = stashy.connect(sensor_config.get('bitbucket_server_url'),
                                        self._config.get('username'),
                                        self._config.get('password'))

            self._init_server_last_commit()
        elif self.service_type == 'cloud':
            # initialization for BitBucket Cloud
            self.client = Client(BasicAuthenticator(
                self._config.get('username'),
                self._config.get('password'),
                self._config.get('email'),
            ))
        else:
            raise ValueError('specified bitbucket type (%s) is not supported' % self.service_type)
        self._increment_event_id()

    def poll(self):
        if self.service_type == 'server':
            for commit in self._get_server_updated_commits():
                self._dispatch_trigger_for_server('commit', commit)
        elif self.service_type == 'cloud':
            pass

    def cleanup(self):
        pass

    def add_trigger(self, trigger):
        pass

    def update_trigger(self, trigger):
        pass

    def remove_trigger(self, trigger):
        pass

    def _poll_bitbucket_server(self):
        pass

    def _poll_bitbucket_cloud(self):
        pass

    def _dispatch_trigger_for_server(self, event_type, payload):
        data = {
            'id': self._get_event_id(),
            'created_at': datetime.now().strftime(self.DATE_FORMAT),
            'type': event_type,
            'payload': payload,
        }
        self._increment_event_id()

        self._sensor_service.dispatch(trigger=self._trigger_ref, payload=data)

    # Returns unique id for the dispatching events
    def _get_event_id(self):
        ret_id = self._sensor_service.get_value(name=self._trigger_ref)
        if not ret_id:
            return 1
        return ret_id

    # Increments event id of datastore
    def _increment_event_id(self):
        self._sensor_service.set_value(name=self._trigger_ref,
                                       value=self._get_event_id() + 1)

    def _init_server_last_commit(self):
        def do_init_last_commit(repo, branch, last_commit):
            if repo not in self.last_commit:
                self.last_commit[repo] = {}
            self.last_commit[repo][branch] = last_commit
           
        # initialize last commit for each branches
        [[do_init_last_commit(x, b['displayId'], b['latestCommit'])
            for b in self.client.projects[p].repos[r].branches()]
            for (p,r) in [x.split('/') for x in self.repositories]]

    def _get_server_updated_commits(self):
        new_commits = []
        for (proj, repo) in [x.split('/') for x in self.repositories]:
            repo_name = '%s/%s' % (proj, repo)
            for branch in self.client.projects[proj].repos[repo].branches():
                for commit in self.client.projects[proj].repos[repo].commits(branch['id']):
                    if self.last_commit[repo_name][branch['displayId']] == commit['id']:
                        break

                    # append new commit
                    new_commits.append({
                        'repository': repo,
                        'branch': branch,
                        'author': commit['author']['emailAddress'],
                        'time': datetime.fromtimestamp(commit['authorTimestamp'] / 1000),
                        'msg': commit['message'],
                    })

                # update latest commit of target branch
                self.last_commit[repo_name][branch['displayId']] = branch['latestCommit']

        return new_commits
