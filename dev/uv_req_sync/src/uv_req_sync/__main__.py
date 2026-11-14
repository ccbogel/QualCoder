"Main"
import os
import re
import tomllib
from pathlib import Path
from time import sleep

from uv_req_sync.internals.authors import authors_processing
from uv_req_sync.internals.compare_n_dedup import compare_deps
from uv_req_sync.internals.parse_reqs_txt import comments, versionated_or_new
from uv_req_sync.internals.toml_data_import import (
    module_dependencies as dependencies_toml,
)

RE = re.compile(r'[<>=!~]=?\s*\d+(?:\.\d+)*')

def argparser() -> None:
    print("This will be the argparser")

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

# ---------------
# Main processing
# ---------------
def process() -> None:

    #Read the base origin.toml
    template=dev_slash_uv/"template"/"pyproject.toml"
    with open(template,"rb") as toml_file:
        template_data= tomllib.load(toml_file,parse_float=str)

    # This ensures that the old file stays the same and it's data's
    # copy is the one being modified
    data=template_data.copy()

    # -----------
    # Project tag
    # -----------
    project=data["project"]
    project["name"]=check_and_return(project, 'project',"name")
    project["version"]=check_and_return(project, 'project',"version")
    project["description"]=check_and_return(project, 'project',"description")
    project["readme"]=check_and_return(project, 'project',"readme")
    project["authors"]=authors_processing(project["authors"])
    project["requires-python"]=check_and_return(project, 'project',"requires-python")
    
    # -----------------------
    # [project.dependencies]
    # -----------------------
    new_toml_deps:list[str]|None=compare_deps(dependencies_toml,versionated_or_new)
    
    
    # Checks weather any old dependency was removed from
    # requirements.txt or needs a special index
    from uv_req_sync.internals.parse_reqs_txt import reqs_lines
    from uv_req_sync.internals.specially_indexed import specially_indexed
    # see internals/specially_index.py for a little bit more info

    reqs_lines_normalized:list[str]=reqs_lines.copy()
    for idx, line in enumerate(reqs_lines):
        line=RE.sub("",line).strip()
        reqs_lines_normalized[idx]=line

    poppers=[]
    for idx, dep in enumerate(new_toml_deps):
        dep_normalized=RE.sub("",dep)
        if dep_normalized not in reqs_lines_normalized and dep_normalized not in specially_indexed:
            poppers.append(idx)
    
    for i in sorted(poppers, reverse=True):
        new_toml_deps.pop(i)
    
    project["dependencies"]=new_toml_deps
    
    # Scripts is already configured, it depends on project's 
    # main entrypoint, so it is easier to "manually" config
    # If at some point these thing need to be edited manually
    #scripts=project["scripts"]
    #main_script=scripts["qualcoder"]


    # -----------
    # Tools tag
    # -----------
    #tool=data["tool"]

    # Since the only modules that require index are already configured
    # it is not needed to change the uv parsing logic
    #uv= tool["uv"]

    # Ruff is already stabilized and does not require further parsing
    # or stabilizing for now
    # ruff=tool["ruff"]
    
    
    # -----------
    # Toml Write
    # -----------
    out_toml=root/"pyproject.toml"
    
    try:
        os.unlink(out_toml)
    except FileNotFoundError:
        print("file not found")
    
    # As tomllib is only RO, tomli_w is required
    import tomli_w
    with open(out_toml,"wb") as f:
        tomli_w.dump(data, f)

    print("TOML data saved\nStarting comment adition")

    # ---------------
    # Comment adition
    # ---------------
    with open(out_toml,"r") as f:
        pyproject_lines=f.readlines()

    # Rest of the comments
    from uv_req_sync.internals.coms_logic import comment_logic
    comment_poppers:list[int]=[]
    while len(comments) > 0:
        go_out:bool=False
        for idx, each in enumerate(comments):
            pyproject_lines, comment_poppers = comment_logic(idx,each,pyproject_lines,comment_poppers)
        
        for i in sorted(comment_poppers, reverse=True):
            try:
                comments.pop(i)
            except IndexError as e:
                print(e)
                go_out=True
                if go_out == True:
                    break
        
        with open(out_toml,"w") as w:
            w.writelines(pyproject_lines)
        
        sleep(1)

        with open(out_toml,"r") as r:
            pyproject_lines=r.readlines()
        
        if comments and go_out == False:
            print("remaining:")
            print(comments)
            print("going again")
        if go_out == True:
            print("Inline comments done\n")
            break

    # Header comment
    from datetime import UTC, datetime
    from textwrap import dedent
    
    header_comment=dedent(f"""\
    # ------
    # PyProject.toml - required for uv, ruff and ty
    # ------
    # This file is generated from dev/uv_req_sync/src/uv_req_sync/_init__.py.
    # Generated on {datetime.now(UTC)}

    """)
    pyproject_lines.insert(0, header_comment)

    with open(out_toml,"w") as w:
        w.writelines(pyproject_lines)
    
    # ---------------
    # Small Cleanup
    # ---------------
    # Removes uv locks so it don't locks a thing if
    # it ever gets misconfigured. uv recreates when syncing
    root_uvlock=root/"uv.lock"
    uv_req_synq_uvlock=dev_slash_uv/"uv.lock"
    if root_uvlock.exists():
        os.unlink(root_uvlock)
    if uv_req_synq_uvlock.exists():
        os.unlink(uv_req_synq_uvlock)


# -------------------------------------
# Runtime logic - Actual main()
# -------------------------------------
def main():
    from uv_req_sync.internals.hash import main as make_hashmap
    # This way hash map always exist
    make_hashmap()

    # It was easier to just copy the code from internals/hash.py
    # then to change it to hold variables and assign them dinamically
    from hashlib import sha256

    from uv_req_sync.hashmap import file_hash
    from uv_req_sync.hashmap import list_lines_hash as lines_hash
    h=sha256()
    with open(reqs_txt_file, "rb") as f:
                for chunk in iter(lambda: f.read(65536), b""):
                    h.update(chunk)
    filehash_totest = h.hexdigest()
    
    with open(reqs_txt_file, "rb") as f:
        lines=f.readlines()
    
    hash_lines_totest:list[dict[int, str]]=[]
    
    for i, line in enumerate(lines):
        line = line.rstrip(b"\r\n")
        linha_hash=sha256(line).hexdigest()
        hash_lines_totest.append({i:f"{linha_hash}"})
    
    if filehash_totest.strip() == file_hash.strip() or hash_lines_totest == lines_hash:
        print("File's hashes for requirements.txt are the same\nNo need to check for versioning\n")
        from sys import exit
        exit(0)
    else:
        process()
        print("Done")

if __name__ ==  "__main__":
    main()