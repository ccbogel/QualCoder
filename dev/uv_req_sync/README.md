# uv_req_sync
### The custom QC utility for syncing pyproject.toml based on requirements.txt. 
#### It checks for all the requirements and only adds those which were changed in some way.
---
This script builds a new `pyproject.toml` based on the contents of `requirements.txt`, effectively, "synchying" both documents, making so that only one dependency list (`requirements.txt`) needs to be maintained.
It is recomended that if you use uv on your workflow to always give the utility a quick run (preferably with force) before each work session to check the Qualcoder Team has updated any dependency on `requirements.txt` the utility. 

It is also recomended to take quick look at `pyproject.toml` and `requirements.txt` to check if error was ever commited

Usage:
uv_req_sync [-a|--arguments]

Arguments:
  -h, --help      show this help message and exit
  -f, --force     force TOML generation regardless off hashmap state
  -m, --metadata  enable edits for the metadata of pyproject.toml and generate a new template at the end of TOML generation

Running without deafult Python:
```bash
cd dev

# ensures the script's venv is separated from Qualcoder's
python -m venv uv_req_sync/.venv 
source uv_req_sync/.venv/bin/activate
pip install tomli-w # required as Python's tomllib is read only
cd src
```

Running with uv:
```bash
cd dev/uv_req_synq

uv run uv-req-sync 
uv run force-req-sync # same as -f|--force
```
> uv also can pass command arguments (e.g.`uv run uv-req-sync -m`)

