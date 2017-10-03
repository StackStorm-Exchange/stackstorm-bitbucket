
# Bitbucket Integration Pack

Pack for integration of Bitbucket into StackStorm. The pack includes the
functionality to perform actions on Bitbucket through StackStorm.

## Configuration

Copy the example configuration in [bitbucket.yaml.example](./bitbucket.yaml.example)
to `/opt/stackstorm/configs/bitbucket.yaml` and edit as required.

It must contain:

* ``username`` - Bitbucket username
* ``password`` - Bitbucket password
* ``email`` - Email associated with bitbucket username

You can also use dynamic values from the datastore. See the
[docs](https://docs.stackstorm.com/reference/pack_configs.html) for more info.

**Note** : When modifying the configuration in `/opt/stackstorm/configs/` please
           remember to tell StackStorm to load these new values by running
           `st2ctl reload --register-configs`

## Actions

### Repositories

#### List Repositories

This action is used to list all the repositories of a user.

Usage:

```bash
st2 run bitbucket.list_repos
```

#### Create Repository

This action is used to create a repository.

Usage:

```bash
st2 run bitbucket.create_repo repo="<repo-name-to-create>"
```

#### Delete Repository

This action is used to delete a repository.

Usage:

```bash
st2 run bitbucket.delete_repo repo="<repo-name-to-delete>"
```

#### Archiving a Repository

This action archives a repository and returns a path to the archived repository.

Usage:

```bash
st2 run bitbucket.archive_repo repo="<repo-name-to-archive>"
```

### Issues

#### Create Issue

This action is used to create an issue.

Usage:

```bash
st2 run bitbucket.create_issue repo="<repo-name>" title="<issue-title>" desc="<description-of-issue>" status=<new,open,resolved> kind="<bug, proposal>"
```

#### List Issues

This action is used to list all issues for a given repository.

Usage:

```bash
st2 run bitbucket.list_issues repo="<repo-name>"
```

#### Update Issues

This action is used to update issue's description for a given repository.

Usage:

```bash
st2 run bitbucket.update_issue repo="<repo-name>" id=<issue-id> desc="<updated-description>"
```

#### Delete Issues

This action is used to delete issues for a given repository. Provide an array of IDs (this can be
provided as a comma separated string of IDs using the CLI) to delete more than one issue.

Usage:

```bash
st2 run bitbucket.delete_issues repo="<repo-name>" ids=<1,2,3,4>
```

### Services

#### Create Service

This action to create a service/hook.

Usage:

```bash
st2 run bitbucket.create_service repo="<repo-name>" url="<URL-for-service>" service="<service-name-to-hook>"
```

#### List Services

This action is used to list services/hooks.

Usage:

```bash
st2 run bitbucket.list_services repo="<repo-name>"
```

#### Update Service

This action is used to update service/hook.

Usage:

```bash
st2 run bitbucket.update_service repo="<repo-name>" id=<id-of-service> url="<url-to-update>"
```

#### Delete Services

This action is used to delete services/hooks for a given repository.

Usage:

```bash
st2 run bitbucket.delete_services repo="<repo-name>" ids=<1,2,3,4>
```

### SSH Keys

#### List SSH keys

This action lists the SSH keys of a user.

Usage:

```bash
st2 run bitbucket.list_ssh_keys
```

#### Delete SSH key

This action deletes a SSH key associated with user's account.

Usage:

```bash
st2 run bitbucket.delete_ssh_key key_id=<id-of-ssh-key>
```

#### Associate SSH key

This action associates a SSH key associated with user's account.

Usage:

```bash
st2 run bitbucket.associate_ssh_key ssh_key="<ssh-key>" label="<label-for-SSH-key>"
```

### Branches

#### List Branches of a repository

This action lists the branches of a given repository.

Usage:

```bash
st2 run bitbucket.list_branches repo="<repo_name>"
```

## Sensors

### RepositorySensor

This sensor monitors the BitBucket(Cloud/Server) repositories and dispatches following `bitbucket.repository_event` trigger.

Currently, this supports following event type.

* `commit` - Triggered when new commit(s) are made.

#### Trigger: bitbucket.repository_event trigger

Here is an example of trigger payload:
```
{
  "id": "25",
  "created_at": "2017-09-29 03:19:50",
  "type": "commit",
  "payload": {
    "repository": "xaas/deploy-test",
    "branch": "master",
    "changed_files": {"deleted": [], "added": [], "moved": [], "modified": ["foo/bar", u"hoge/fuga/tmp01"]},
    "commits": [
      {
        "msg": "A test commit message",
        "author": "user.localhost2000@gmail.com",
        "repository": "XAAS/deploy-test",
        "branch": "master",
        "time": "2017-09-29 03:19:36",
        "files": {"deleted": [], "added": [], "moved": [], "modified": ["foo/bar"]},
      },
      ...
    ]
  }
}
```

*restriction* The `files` and `changed_files` parameters are not set in the Bitbucket cloud (The feature is not implemented, yet)

## Rules

### Post-Receive WebHook

This rule triggers ``packs.install`` action (in StackStorm v2.1+) to allow
auto-deployment of a pack from a git repository.

This has a number of pre-dependencies:

- Setting Workflow / Hooks / Post-Receive WebHooks pointing at the URL:

```
https://<my-server>/api/v1/webhooks/bitbucket_post_receive?st2-api-key=<ST2-API-Key>
```

- The rule is disabled by default and needs to be enabled with

```bash
st2 rule enable bitbucket.post_receive_webhook
```

*Important:* The BitBucket server (or cloud) needs to be able to reach
your StackStorm server and consider the SSL cert as valid. The
`ST2-API-Key` should be generated as per the instructions at
https://docs.stackstorm.com/authentication.html.
