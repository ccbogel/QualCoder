# uv_req_sync
### The custom QC utility for syncing pyproject.toml based on requirements.txt. 
---
This script builds a new `pyproject.toml` based on the contents of `requirements.txt`, effectively, "synchying" both documents, making so that only one dependency list (`requirements.txt`) needs to be maintained.As a result, this utility allows QualCoder develompemnt to be compatible with Atral's [`uv`](https://github.com/astral-sh/uv) tool while maintaining only one the regular depency list.
It is recomended that if you use uv on your workflow to always give the utility a quick run (preferably with force) before each work session to check the Qualcoder Team has updated any dependency on `requirements.txt` the utility. 

It is also recomended to take quick look at `pyproject.toml` and `requirements.txt` to check if an error was ever commited to either QualCoder or the utility

>[!CAUTION]
>The utility is deliberatly isolated from QualCoder's source code and develop/runtime 
>enviroment. It has it's own virtual enviroment and dependency list, it is best to always 
>call it directly by going (`cd`) to `dev/uv_req_sync` or `dev/uv_req_sync/src` 
>dependending on the tool used to summon the utility

>[!TIP]
>The steps here assume you have uv already installed and added it to your PATH. 
>If you don't have it (or don't want to install it) on your system, you can first
>install it via `pip` + `venv` on your virtual enviroment (Qualcoder's or utility's)
>
>```bash
>cd dev/uv_req_sync/ # Goes to utility root
># or cd path/to/QualCoder/
>#QualCoder's root if you want to use it
># in development/use (your choice)
>python -m venv .venv # create a virtual enviroment
>#Activate the virtual enviroment
>source .venv/bin/activate # Unix like (Mac, Linux, BSD, etc)
>.venv\Scripts\activate.bat # Windows (cmd.exe)
>.venv\Scripts\activate.ps1 # Windows (PowerShell) 
>pip install uv
>uv sync
>```

#### Usage:

uv_req_sync [-a|--arguments]

Arguments:
  -h, --help      show this help message and exit
  -f, --force     force TOML generation regardless off hashmap state
  -m, --metadata  enable edits for the metadata of pyproject.toml and generate a new template at the end of TOML generation

##### Running with deafult Python:

Since the tool is isolated in order to run one needs to go into the utiliy's directory
(`cd dev/uv_req_sync/`) before running it

```bash
cd dev/uv_req_sync/ # Goes to utility root
python -m venv .venv # create a virtual enviroment
#Activate the virtual enviroment
source .venv/bin/activate # Unix like (Mac, Linux, BSD, etc)
.venv\Scripts\activate.bat # Windows (cmd.exe)
.venv\Scripts\activate.ps1 # Windows (PowerShell) 
pip install tomli-w # required as Python's tomllib is read only
cd src # goes into the src dir
python -m uv_req_sync
```

##### Running with uv:

One can run the utility with uv in two ways:

1. By going into utility's root (`cd dev/uv_req_sync/`) before before running it
```bash
cd dev/uv_req_sync # Goes to utility root
uv run uv-req-sync # Just run the utility, uv will download the 
                   # dependencies and build them on the first run
uv run force-req-sync # This command is the same as -f|--force
                      # for regular python
```

2. By passing the `--project` flag to uv (command):

```bash
# cd path/to/QualCoder/
uv run --project dev/uv_req_sync uv-req-sync
```

> [!TIP]
> uv also can pass command arguments to the utility just like regular with Python
>
> e.g.`uv run uv-req-sync -m`