from st2common.runners.base_action import Action
from bitbucket.bitbucket import Bitbucket


class BitBucketAction(Action):
    def __init__(self, config):
        super(BitBucketAction, self).__init__(config)

    def _get_client(self, repo=None):
        if repo:
            bb = Bitbucket(username=self.config['username'],
                           password=self.config['password'],
                           repo_name_or_slug=repo)
        else:
            bb = Bitbucket(username=self.config['email'],
                           password=self.config['password'])
        return bb
