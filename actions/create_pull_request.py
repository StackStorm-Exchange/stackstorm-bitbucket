from lib.action import BitBucketAction


class CreatePullRequestAction(BitBucketAction):
    def run(self, project, repository, title, description, source, target, reviewers=None):
        client = self._get_stashy_client()
        return list(
            client.projects[project].repos[repository].pull_requests.create(
                title,
                description,
                source,
                target,
                reviewers))
