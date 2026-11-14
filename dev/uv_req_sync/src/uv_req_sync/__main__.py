"Main"
import os
import shutil
import tomllib
from hashlib import sha256
from pathlib import Path
from sys import exit
from textwrap import dedent

import tomli_w

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

root=Path(__file__).parent.parent.parent.parent.parent
reqs_txt_file = root/"requirements.txt"
dev_slash_uv=Path(__file__).parent.parent.parent

# Main
def main() -> None:

    #Read the base origin.toml
    og_toml=dev_slash_uv / "origin.toml"
    with open(og_toml,"rb") as toml_file:
        og_toml_data= tomllib.load(toml_file,parse_float=str)

    # Backup in case bad things happen
    og_toml_bkp=dev_slash_uv / "origin.toml.bak"
    shutil.copy2(og_toml, og_toml_bkp)

    #This ensures that the old file stays the same, for now
    data=og_toml_data.copy()

    #Project tag
    project=data["project"]
    project["name"]=check_and_return(project, 'project',"name")
    project["version"]=check_and_return(project, 'project',"version")
    project["description"]=check_and_return(project, 'project',"description")
    project["readme"]=check_and_return(project, 'project',"readme")
    project["authors"]=authors_processing(project["authors"])
    project["requires-python"]=check_and_return(project, 'project',"requires-python")
    
    new_toml_deps:list[str]|None=compare_deps(dependencies_toml,versionated_or_new)
    

    # Checks weather any old dependency was removed from
    # requirements.txt
    from uv_req_sync.internals.parse_reqs_txt import reqs_lines

    for idx, line in enumerate(reqs_lines):
        line=line.strip()
        reqs_lines[idx]=line

    print(reqs_lines)
    poppers=[]
    for idx, dep in enumerate(new_toml_deps):
        print(dep)
        if dep not in reqs_lines:
            poppers.append(idx)
    
    for i in sorted(poppers, reverse=True):
        new_toml_deps.pop(i)
    
    print(poppers)
    project["dependencies"]=new_toml_deps

    # Scripts is already configured, it depends on project's 
    # main entrypoint, so it is easier to "manually"config
    # 
    # If at some point these thing need to be edited manually
    # 
    # scripts=project["scripts"]
    # main_script=scripts["qualcoder"]


    #Tools
    #tool=data["tool"]

    # This block may take a while
    #tool["uv"]=uv_parsing()

    # Ruff is already stabilized and does not require further parsing
    # or stabilizing for now
    # ruff=tool["ruff"]
    # Write file
    out_toml=root/"pyproject.toml"
    
    try:
        os.unlink(out_toml)
    except FileNotFoundError:
        print("file not found")

    with open(out_toml,"wb") as f:
        tomli_w.dump(data, f)

    # Comment adition
    comments:list[dict]=comms
    header_comment=dedent("""\
    # ------
    # PyProject.toml - required for uv, ruff, ty and appimage
    # ------
    # This file is generated from dev/uv_req_sync/__init__.py.
    # It is used to sync pyproject.toml with requirements.txt. 
    # Please do not touch
    # 
    # This one is just the "shell"/or base doc, it is this one
    # that the build_toml.py will edit


    """)

    with open(out_toml,"r") as f:
        pyproject_lines=f.readlines()

    pyproject_lines.insert(0, header_comment)


    #Insert coments

    # To see which comment needs to be appended
    print(comments)

    with open(out_toml,"w") as w:
        w.writelines(pyproject_lines)



# -------------------------------------
# Main
# -------------------------------------
if __name__ ==  "__main__":
    hashmap_file=dev_slash_uv/"src"/"uv_req_sync"/"hashmap.py"
    if not hashmap_file.exists():
        from uv_req_sync.internals.hash import main as make_hashmap
        
        make_hashmap()

    from uv_req_sync.hashmap import file_hash
    from uv_req_sync.hashmap import list_lines_hash as lines_hash

    me=Path(__file__)
    hash_dot_py=str(root/"dev"/"uv_req_sync"/"internals"/"hash.py")
    print(hash_dot_py)

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
    if filehash_totest.strip() == file_hash.strip() or hash_lines_totest == lines_hash:
        print("File's hashes for requirements.txt are the same\nNo need to check for versioning\n")
        exit(0)
    else:
        main()
        print("Done")
