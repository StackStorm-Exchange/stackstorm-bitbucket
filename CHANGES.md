# Change Log

# 0.5.2

- Fixed the problem that crashes when a new branch is crated after starting by changing configuration schema to specify branches to monitor for each repositories (#9).

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
