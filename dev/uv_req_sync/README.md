# uv_req_sync
### The custom QC utility for syncing pyproject.toml based on requirements.txt. 
#### It checks for all the requirements and only adds those which were changed in some way. The focus is on versionated and newer additions
---
Please run from here `dev/uv_req_sync` with uv, also read the pyproject.toml as it can help understand how to make this work

Running with uv
```bash
uv run uv-req-sync #Checks wheater the 
                   #requirements.txt was changes 
                   # and if so updates it
uv run force-req-sync # Forces the "sync"
```

Running without uv
```bash
python -m venv .venv
source .venv/bin/activate
pip install toml_li # required because python_stdlib_tomllib 
                    # is read only
# if not at QualCoder/dev cd QualCoder/dev
python uv_req_sync #Checks wheater the 
                   #requirements.txt was changes 
                   # and if so updates it
# still do not have the force option without uv
# but it will be this:
python uv_req_sync -f # Forces the "sync"
python uv_req_sync --force # Forces the "sync"
```