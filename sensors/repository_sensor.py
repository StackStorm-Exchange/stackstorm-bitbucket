import stashy

from pybitbucket.auth import BasicAuthenticator
from pybitbucket.bitbucket import Client
from pybitbucket.ref import Branch
from pybitbucket.user import User

from datetime import datetime
from dateutil.parser import parse as tz_parse

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
            self._init_cloud_last_commit()
        else:
            raise ValueError('specified bitbucket type (%s) is not supported' % self.service_type)
        self._increment_event_id()

    def poll(self):
        new_commits = []
        if self.service_type == 'server':
            new_commits = self._get_server_updated_commits()
        elif self.service_type == 'cloud':
            new_commits = self._get_cloud_updated_commits()

        if new_commits:
            self._dispatch_trigger_for_server('commit', new_commits)

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
                                       value=int(self._get_event_id()) + 1)

    # initialize last commit for each branches
    def _init_server_last_commit(self):
        [[self._set_last_commit('%s/%s' % (p, r), b['displayId'], b['latestCommit'])
            for b in self.client.projects[p].repos[r].branches()]
            for (p, r) in [x.split('/') for x in self.repositories]]

    def _init_cloud_last_commit(self):
        [[self._set_last_commit('%s/%s' % (o, r), b.name, b.commits().next().hash)
            for b in Branch.find_branches_in_repository(repository_name=r, client=self.client,
                                                        owner=o) if isinstance(b, Branch)]
            for (o, r) in [x.split('/') for x in self.repositories]]

    def _set_last_commit(self, repo, branch, last_commit):
        if repo not in self.last_commit:
            self.last_commit[repo] = {}
        self.last_commit[repo][branch] = last_commit

    def _get_server_updated_commits(self):
        new_commits = []
        for (proj, repo) in [x.split('/') for x in self.repositories]:
            repo_name = '%s/%s' % (proj, repo)
            for branch in self.client.projects[proj].repos[repo].branches():
                for commit in self.client.projects[proj].repos[repo].commits(branch['id']):
                    if self.last_commit[repo_name][branch['displayId']] == commit['id']:
                        break

                    # append new commit
                    commit_time = datetime.fromtimestamp(commit['authorTimestamp'] / 1000)
                    new_commits.append({
                        'repository': repo_name,
                        'branch': branch['displayId'],
                        'author': commit['author']['emailAddress'],
                        'time': commit_time.strftime(self.DATE_FORMAT),
                        'msg': commit['message'],
                    })

                # update latest commit of target branch
                self.last_commit[repo_name][branch['displayId']] = branch['latestCommit']

        return new_commits

    def _get_cloud_updated_commits(self):
        new_commits = []
        for (owner, repo) in [x.split('/') for x in self.repositories]:
            repo_name = '%s/%s' % (owner, repo)
            for branch in Branch.find_branches_in_repository(repository_name=repo,
                                                             owner=owner, client=self.client):

                # If there is no commit in this branch, pybitbucket returns dict object
                if not isinstance(branch, Branch):
                    break

                for commit in branch.commits():
                    if self.last_commit[repo_name][branch.name] == commit.hash:
                        break

                    author = 'Unknown'
                    if isinstance(commit.author, User):
                        author = commit.author.username
                    elif isinstance(commit.author, dict):
                        author = commit.author['raw']

                    # append new commit
                    new_commits.append({
                        'repository': repo_name,
                        'branch': branch.name,
                        'author': author,
                        'time': tz_parse(commit.date).strftime(self.DATE_FORMAT),
                        'msg': commit.message,
                    })

                # update latest commit of target branch
                self.last_commit[repo_name][branch.name] = branch.commits().next().hash

        return new_commits
