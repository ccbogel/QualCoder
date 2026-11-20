# uv_req_sync
### The custom QC utility for syncing pyproject.toml based on requirements.txt. 
#### It checks for all the requirements and only adds those which were changed in some way.
---
This script builds a new `pyproject.toml` based on the contents of `requirements.txt`, effectively, "synchying" both documents, making so that only one dependency list (`requirements.txt`) needs to be maintained.
It is recomended that if you use uv on your workflow to always give the utility a quick run (preferably with force) before each work session to check the Qualcoder Team has updated any dependency on `requirements.txt` the utility. 

It is also recomended take quick look at `pyproject.toml` and `requirements` as to understand how they work

Running with uv
```bash
cd dev/uv_req_synq

uv run uv-req-sync # Checks wheater the 
                   # requirements.txt was changes 
                   # and if so updates it
uv run force-req-sync # Forces the "sync"
```

Running without uv
```bash
cd dev
python -m venv uv_req_sync/.venv
source uv_req_sync/.venv/bin/activate
pip install tomli-w # required because python_stdlib_tomllib 
                    # is read only
cd src

python -m uv_req_sync #Checks wheater the 
                      #requirements.txt was changes 
                      # and if so updates it
python -m uv_req_sync -f      # Forces the "sync"
python -m uv_req_sync --force # Forces the "sync"
```

> uv also can deal with argparse `uv run uv-req-sync -f`