# Change Log

# 0.5.3

- Added a parameter `changed_files` on the dispatching payload to enable to identify the changed files in the updated commits.
  (But this parameter is only set for the repository on the BitBucket server)

# 0.5.2

- Changed configuration schema to allow specifying branch to monitor for each repository. You will need to update your configuration.
  This fixed a crash that occured when a new branch is created after the sensor starts (#9).

# 0.5.1

- Corrected RepositorySensor to dispatch trigger about update commits by the set of (repository, branch)

# 0.5.0

- Added sensor to monitor events of specified repositories in the BitBucket Cloud or specified BitBucket Server

# 0.4.0

- Updated action `runner_type` from `run-python` to `python-script`

# 0.3.0

- Use `packs.install` capabilities in StackStorm 2.1

# 0.2.0

- Rename `config.yaml` to `config.schema.yaml` and update to use schema.

# 0.1.0

- First release
