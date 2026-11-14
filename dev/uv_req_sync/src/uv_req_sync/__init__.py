"""The utility for syncing pyproject.toml based on requirements.txt. 
It checks for all the requirements and only adds those which were changed
in some way. The focus is on versionated and newer additions"""