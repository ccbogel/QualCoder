import shutil
import subprocess
import tomllib
from hashlib import sha256
from os import unlink as delete
from pathlib import Path
from sys import executable as python3
from sys import exit

from uv_req_sync.internals.authors import authors_processing
from uv_req_sync.internals.compare_n_dedup import compare_deps
from uv_req_sync.internals.parse_reqs_txt import comms, versionated_or_new
from uv_req_sync.internals.toml_data_import import (
    module_dependencies as dependencies_toml,
)

# Main needs to have a check when asking for the stored 
# hash for the requirements.txt file

def check_and_return(group:dict, toml_key:str, key:str) -> str:
    "Asks for user input for the key [str] on the group [dict]"
    test=input(f"{toml_key}[\"{key}\"] is \"{group[key]}\"\nWould you like to change it?\n(Y)es (N)o\n(Default is no)\n")
    if test.lower() == "y":
        new_value:str = input("What value to put into {group}[\"{key}\"]")
        group[key] = new_value
        return group[key]

    else:
        return group[key]

root=Path(__file__).parent.parent.parent
reqs_txt_file = root/"requirements.txt"

# Main
def main() -> None:

    #Read the base origin.toml
    dev_slash_uv=Path(__file__).parent
    og_toml=dev_slash_uv / "origin.toml"
    with open(og_toml,"rb") as toml_file:
        og_toml_data= tomllib.load(toml_file,parse_float=str)

    # Backup in case bad things happen
    og_toml_bkp=dev_slash_uv / "origin.toml.bak"
    shutil.copy2(og_toml, og_toml_bkp)

    #This ensures that the old file stays the same, for now
    data=og_toml_data.copy()

    #Project tag

    # Can add a recursive function akeen to the way authors_processing, or even better
    # have this be based on arg parse
    project=data["project"]
    project["name"]=check_and_return(project, 'project',"name")
    project["version"]=check_and_return(project, 'project',"version")
    project["description"]=check_and_return(project, 'project',"description")
    project["readme"]=check_and_return(project, 'project',"readme")
    project["authors"]=authors_processing(project["authors"])
    project["requires-python"]=check_and_return(project, 'project',"requires-python")
    toml_deps:list[str]|None=compare_deps(dependencies_toml,versionated_or_new)
    print(toml_deps)


    # Scripts is already configured, it depends on project's 
    # main entrypoint, so it is easier to "manually"config
    # 
    # If at some point these thing need to be edited manually
    # 
    # scripts=project["scripts"]
    # main_script=scripts["qualcoder"]


    #Tools
    tool=data["tool"]

    # This block may take a while
    #tool["uv"]=uv_parsing()

    # Ruff is already stabilized and does not require further parsing
    # or stabilizing for now
    # ruff=tool["ruff"]

    # Comment adition
    comments:list[dict]=comms

    # Write file
    out_toml=root/"pyproject.toml"


# -------------------------------------
# Main
# -------------------------------------
try:
    from uv_req_sync.hashmap import file_hash, hashmap
    from uv_req_sync.hashmap import list_lines_hash as lines_hash
except ImportError as e:
    from uv_req_sync.internals.hash import __file__ as hash_dot_py
    print(f"{e}:Hashmap does not exist")
    subprocess.run([f'{python3}', f'{hash_dot_py}'], check=False)
    
h=sha256()
with open(reqs_txt_file, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
filehash_totest = h.hexdigest()
with open(reqs_txt_file, "rb") as f:
    lines=f.readlines()
hash_lines_totest:list[dict]=[]
for i, line in enumerate(lines):
    line = line.rstrip(b"\r\n")
    line_hash=sha256(line).hexdigest()
    hash_lines_totest.append({i:f"{line_hash}"})
if filehash_totest.strip == file_hash.strip or hash_lines_totest == lines_hash:
    print("File's hashes for requirements.txt are the same\nNo need to check for versioning\n")
    exit(0)
else:
    delete(hashmap)
    main()

if not Path.exists(Path(hashmap)):
    subprocess.run([f'{python3}', f'{hash_dot_py}'], check=False)
exit(0)