# uv_req_sync
### The custom QC utility for syncing pyproject.toml based on requirements.txt. 
#### It checks for all the requirements and only adds those which were changed in some way.
---
It is recomended to run the utility with uv, also read the pyproject.toml as it can help understand how to make this work

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