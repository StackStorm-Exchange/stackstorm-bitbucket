import json
import stashy

from pybitbucket.auth import BasicAuthenticator
from pybitbucket.bitbucket import Client
from pybitbucket.commit import Commit
from pybitbucket.user import User

from requests.exceptions import HTTPError

from timeout_decorator import timeout
from timeout_decorator.timeout_decorator import TimeoutError

from datetime import datetime

from st2reactor.sensor.base import PollingSensor


class RepositorySensor(PollingSensor):
    DATE_FORMAT = '%Y-%m-%d %H:%M:%S'
    TIMEOUT_SECONDS = 20

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
        self.targets = sensor_config.get('targets')
        if not self.targets:
            raise ValueError('"targets" parameter in the "sensor" is required')

        if not all(['repository' in x and 'branches' in x for x in self.targets]):
            raise ValueError('"repository" and "branches" are mandatory in "sensor.target"')

        if not all([len(x['repository'].split('/')) == 2 for x in self.targets]):
            raise ValueError('Invalid repository name is specified in the "targets" parameter')

        self.TIMEOUT_SECONDS = sensor_config.get('timeout', self.TIMEOUT_SECONDS)

        # initialize global parameter
        self.commits = {}

        self.service_type = sensor_config.get('bitbucket_type')
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

        self._logger.info("It's ready to monitor events.")

    def poll(self):
        @timeout(self.TIMEOUT_SECONDS)
        def get_server_updated_commits():
            def get_commit_info(repo, commit_id):
                """
                This returns detail information associated with the specific commit-id
                to get the changed files in the commit.
                """
                res = repo._client.get(repo.url('/commits/{}/changes'.format(commit_id)))
                return json.loads(res.content)

            def get_updated_files(commit):
                """
                This returns file-pathes which are changed in this commit.
                """
                def do_get_updated_files(req_type):
                    return [x['path']['toString'] for x in commit['values']
                            if x['type'] == req_type]

                return {
                    'added': do_get_updated_files('ADD'),
                    'moved': do_get_updated_files('MOVE'),
                    'deleted': do_get_updated_files('DELETE'),
                    'modified': do_get_updated_files('MODIFY'),
                }

            for target in self.targets:
                (proj, repo) = target['repository'].split('/')

                # The case of initialized processing was failed
                if not target['repository'] in self.last_commit:
                    self._logger.warning('Initialization processing might be failed')
                    self.last_commit[target['repository']] = {}

                for branch in target['branches']:
                    # The case that last_commit for branch was blank by some reasons
                    if branch not in self.last_commit[target['repository']]:
                        self._logger.info("The branch(%s) isn't initialized" % (branch))
                        self.last_commit[target['repository']][branch] = datetime.now()

                    try:
                        robj = self.client.projects[proj].repos[repo]
                        for commit in robj.commits(branch):
                            commit_time = datetime.fromtimestamp(commit['authorTimestamp'] / 1000)
                            if commit_time <= self.last_commit[target['repository']][branch]:
                                break

                            # append new commit
                            self.new_commits.append({
                                'repository': target['repository'],
                                'branch': branch,
                                'author': commit['author']['emailAddress'],
                                'time': commit_time.strftime(self.DATE_FORMAT),
                                'msg': commit['message'],
                                'files': get_updated_files(get_commit_info(robj, commit['id'])),
                            })
                    except stashy.errors.NotFoundException as e:
                        self._logger.warning("branch(%s) doesn't exist in the repository(%s) [%s]" %
                                             (branch, target['repository'], e))

        @timeout(self.TIMEOUT_SECONDS)
        def get_cloud_updated_commits():
            for target in self.targets:
                (proj, repo) = target['repository'].split('/')

                # The case of initialized processing was failed
                if not target['repository'] in self.last_commit:
                    self._logger.warning('Initialization processing might be failed')
                    self.last_commit[target['repository']] = {}

                for branch in target['branches']:
                    # The case that last_commit for branch was blank by some reasons
                    if branch not in self.last_commit[target['repository']]:
                        self._logger.info("The branch(%s) isn't initialized" % (branch))
                        self.last_commit[target['repository']][branch] = datetime.now()

                    try:
                        for commit in Commit.find_commits_in_repository(username=proj,
                                                                        repository_name=repo,
                                                                        branch=branch,
                                                                        client=self.client):

                            commit_time = datetime.strptime(commit.date, "%Y-%m-%dT%H:%M:%SZ")
                            if commit_time <= self.last_commit[target['repository']][branch]:
                                break

                            author = 'Unknown'
                            if isinstance(commit.author, User):
                                author = commit.author.username
                            elif isinstance(commit.author, dict):
                                author = commit.author['raw']

                            # append new commit
                            self.new_commits.append({
                                'repository': target['repository'],
                                'branch': branch,
                                'author': author,
                                'time': commit_time.strftime(self.DATE_FORMAT),
                                'msg': commit.message,
                                'files': {},  # XXX: This is not implemented, yet.
                            })
                    except (ValueError, HTTPError):
                        self._logger.warning("branch(%s) doesn't exist in the repository(%s)" %
                                             (branch, target['repository']))

        # On the assumption the case that the processing is aborted by timeout,
        # we need to prepare the variable to save update information (may be inchoate).
        #
        # This variable is cleared at the outset of each polling processing.
        self.new_commits = []

        try:
            if self.service_type == 'server':
                get_server_updated_commits()
            elif self.service_type == 'cloud':
                get_cloud_updated_commits()
        except TimeoutError:
            self._logger.info('checking processing is timedout')

        if self.new_commits:
            # update last_commit instance variable
            self._update_last_commit()

            # dispatch new commit informatoins every repository/branch
            for (repo, branch) in set([(x['repository'], x['branch']) for x in self.new_commits]):
                payload = {
                    'repository': repo,
                    'branch': branch,
                    'commits': [x for x in self.new_commits if (x['repository'] == repo and
                                                                x['branch'] == branch)],
                    # The file informations which are changed in the added commits are set.
                    'changed_files': {'added': [], 'moved': [], 'deleted': [], 'modified': []},
                }

                # This processing enables to make a more complex criteria in the Rule
                for t in ['added', 'moved', 'deleted', 'modified']:
                    # Tally up the all changed-files
                    payload['changed_files'][t] += sum([x['files'][t] for x in self.new_commits
                                                        if t in x['files']], [])

                    # De-duplicate each changed-files
                    payload['changed_files'][t] = list(set(payload['changed_files'][t]))

                self._dispatch_trigger('commit', payload)

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

    def _dispatch_trigger(self, event_type, payload):
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
        def _last_ctime(project, repository, branch):
            commits = self.client.projects[project].repos[repository].commits(branch)
            last_commit = commits.next()

            if last_commit:
                return datetime.fromtimestamp(last_commit['authorTimestamp'] / 1000)
            else:
                return datetime.strptime('1900-01-01 00:00:00', self.DATE_FORMAT)

        for target in self.targets:
            (proj, repo) = target['repository'].split('/')

            for branch in target['branches']:
                try:
                    self._set_last_commit_time(target['repository'],
                                               branch,
                                               _last_ctime(proj, repo, branch))
                except stashy.errors.NotFoundException as e:
                    self._logger.warning("branch(%s) doesn't exist in the repository(%s) [%s]" %
                                         (branch, target['repository'], e))

    def _init_cloud_last_commit(self):
        for target in self.targets:
            (proj, repo) = target['repository'].split('/')

            for branch in target['branches']:
                commits = Commit.find_commits_in_repository(username=proj,
                                                            repository_name=repo,
                                                            branch=branch,
                                                            client=self.client)

                try:
                    self._set_last_commit_time(target['repository'],
                                               branch,
                                               datetime.strptime(commits.next().date,
                                                                 "%Y-%m-%dT%H:%M:%SZ"))
                except (ValueError, HTTPError) as e:
                    self._logger.warning("branch(%s) doesn't exist in the repository(%s) [%s]" %
                                         (branch, target['repository'], e))

    def _set_last_commit_time(self, repo, branch, last_commit_time):
        if repo not in self.last_commit:
            self.last_commit[repo] = {}
        self.last_commit[repo][branch] = last_commit_time

    def _update_last_commit(self):
        for commit in self.new_commits:
            commit_time = datetime.strptime(commit['time'], self.DATE_FORMAT)

            if self.last_commit[commit['repository']][commit['branch']] < commit_time:
                self.last_commit[commit['repository']][commit['branch']] = commit_time
