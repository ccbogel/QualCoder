"Main"
import os
import re
import tomllib
from argparse import ArgumentParser, Namespace
from copy import copy
from pathlib import Path
from sys import exit
from textwrap import dedent
from time import sleep

from uv_req_sync.internals.authors import authors_processing
from uv_req_sync.internals.compare_n_dedup import compare_deps

RE = re.compile(r'[<>=!~]=?\s*\d+(?:\.\d+)*')

def argparser() -> Namespace:
    parser = ArgumentParser(
                    prog='uv_req_sync',
                    description='Syncs Uv\'s pyptoject.toml with requirements.txt.\n\
                                 By Default it checks hashmap.py to see if requirements.txt\
                                 wasn changed, if so, syncs pyproject.toml with it ',
                    epilog='See the utilitie\'s README.md for more info',
    )
    parser.add_argument('-f','--force', help='Forces the sync regardless off hashmap state', action='store_true',default=False)
    args = parser.parse_args()
    return args

def check_and_return(group:dict, toml_key:str, key:str) -> str:
    "Asks for user input for the key [str] on the group [dict]"
    print("------------------------")
    print(f"Verify {key}")
    print("------------------------")
    test=input(f"{toml_key}[\"{key}\"] is \"{group[key]}\"\nWould you like to change it?\n(Y)es (N)o\n(Default is no)\n")
    if test.lower() == "y":
        new_value:str = input("What value to put into {group}[\"{key}\"]")
        group[key] = new_value
        return group[key]
    else:
        return group[key]

ROOT=Path(__file__).parent.parent.parent.parent.parent
REQS_DOT_TXT = ROOT/"requirements.txt"
DEV_SLASH_UV=Path(__file__).parent.parent.parent
OUT_TOML=ROOT/"pyproject.toml"
HASHMAPS=DEV_SLASH_UV/"src"/"uv_req_sync"/"hashmap.py"
# ---------------
# Main processing
# ---------------
def process() -> None:
    print("------------------------")
    print("Starting processing")
    print("------------------------")
    
    print("Read TOML\n")
    #Read the base origin.toml
    template=DEV_SLASH_UV/"template"/"pyproject.toml"
    with open(template,"rb") as toml_file:
        template_data= tomllib.load(toml_file,parse_float=str)

    # This ensures that the old file stays the same and it's data's
    # copy is the one being modified
    print("Copy the data\n")
    data=template_data.copy()

    # -----------
    # Project tag
    # -----------
    print("------------------------")
    print("Simple elements")
    print("------------------------")
    project=data["project"]
    project["name"]=check_and_return(project, 'project',"name")
    project["version"]=check_and_return(project, 'project',"version")
    project["description"]=check_and_return(project, 'project',"description")
    project["readme"]=check_and_return(project, 'project',"readme")
    project["requires-python"]=check_and_return(project, 'project',"requires-python")
    
    project["authors"]=authors_processing(project["authors"])
    
    # -----------------------
    # [project.dependencies]
    # -----------------------
    print("------------------------")
    print("Dependencies")
    print("------------------------")
    print("Starting dependencies management")
    from uv_req_sync.internals.parse_reqs_txt import parsing_reqs_dot_txt

    comments, versionated_or_new, reqs_lines=parsing_reqs_dot_txt(REQS_DOT_TXT)


    new_toml_deps:list[str]=compare_deps(copy(project["dependencies"]),versionated_or_new)
    
    
    # Checks weather any old dependency was removed from
    # requirements.txt or needs a special index
    from uv_req_sync.internals.specially_indexed import specially_indexed
    # see internals/specially_index.py for a little bit more info

    print("Dependency cleaninig started")
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
        print(f"popping \"{new_toml_deps[i]}\"")
        new_toml_deps.pop(i)
    
    project["dependencies"]=new_toml_deps
    print("Dependencies management ended")
    
    # Scripts is already configured, it depends on project's 
    # main entrypoint, so it is easier to "manually" config
    
    # If at some point these thing need to be edited manually
    # they can be acessed with
    
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
    print("------------------------")
    print("Finlazing")
    print("------------------------")
    print("Deleting old TOML\n")
    try:
        OUT_TOML.unlink()
        print("Old TOML deleted")
    except FileNotFoundError:
        pass
    
    # As tomllib is read only, tomli_w is required
    import tomli_w
    with open(OUT_TOML,"wb") as f:
        tomli_w.dump(data, f)

    print("TOML data saved\nStarting comment adition")

    # ---------------
    # Comment adition
    # ---------------
    print("TOML file reopened to add comments")
    with open(OUT_TOML,"r") as f:
        pyproject_lines=f.readlines()

    from uv_req_sync.internals.coms_logic import comment_logic
    
    print("Starting while loop to add inline comments")
    comment_poppers:list[int]=[]
    while len(comments) > 0:
        go_out:bool=False
        for idx, each in enumerate(comments):
            pyproject_lines, comment_poppers = comment_logic(idx,each,pyproject_lines,comment_poppers)
        
        for i in sorted(comment_poppers, reverse=True):
            try:
                comments.pop(i)
            except IndexError:
                print(dedent(f"""
                Was not able to pop a comment ({comments[i]})
                due to an IndexError!
                This means the of comment list was reached!
                Exiting while loop
                """))
                go_out=True
                if go_out == True:
                    break
        print("Saving changes to the TOML file\n")
        with open(OUT_TOML,"w") as w:
            w.writelines(pyproject_lines)
        
        #Just for safety
        sleep(1)

        print("Reopenning TOML file\n")
        with open(OUT_TOML,"r") as r:
            pyproject_lines=r.readlines()
        
        if comments and go_out == False:
            print("Remaining comments:\n")
            for comm in comments:
                print(f"{next(iter(comm.values()))}\n")
            print("Going to start iterrating again...\n")
        if go_out == True:
            print("Inline comments done\n")
            break
    
    print("While loop exited")
    # Header comment
    # So simple it can be added here
    from datetime import UTC, datetime
    
    header_comment=dedent(f"""\
    # ------
    # PyProject.toml - required for uv, ruff and ty
    # ------
    # This file is generated from dev/uv_req_sync/src/uv_req_sync/_init__.py.
    # Generated on {datetime.now(UTC)}

    """)
    pyproject_lines.insert(0, header_comment)
    print("Header comment added")

    print("Saving changes to the TOML file\n")
    with open(OUT_TOML,"w") as w:
        w.writelines(pyproject_lines)
    
    print("File sync is completed!\nStarting cleanup...\n")
    
    # ---------------
    # Small Cleanup
    # ---------------
    # Removes uv locks so it don't locks a thing if
    # it ever gets misconfigured. uv recreates when syncing
    # uv sync
    root_uvlock=ROOT/"uv.lock"
    uv_req_synq_uvlock=DEV_SLASH_UV/"uv.lock"
    if root_uvlock.exists():
        os.unlink(root_uvlock)
        print(f"{root_uvlock} deleted!")
    if uv_req_synq_uvlock.exists():
        os.unlink(uv_req_synq_uvlock)
        print(f"{uv_req_synq_uvlock} deleted!")

    # ----------------------------------
    # Final process: make a new hashmap
    # ----------------------------------
    if not OUT_TOML.exists():
            print(f"{OUT_TOML} was not generated sucessfully.")
            print("Please verify your paths, permissions and module instalation.")
            exit(1)
    print(f"A \"pyproject.toml\" was sucessfully generated at {ROOT}")
    print("You can now run \"uv sync\" from project ROOT so you can use uv")
    print("for development work, daily driving, or syncing\npyproject.toml with requirements.txt ")
    print()
    print("Generating hashmap.py as a locking mechanism")
    from uv_req_sync.internals.hash import main as make_hashmap
    make_hashmap()

def work_and_exit() -> None:
        process()
        from sys import exit
        print("Done")
        exit(0)

# -------------------------------------
# Runtime logic - Actual main()
# -------------------------------------
def main():
    args=argparser()

    # Forcing uses the same logic as pyproject.toml not existing
    # i.e. they both do not want to check the hashmap. So they can
    # Share the same conditional block 
    if args.force == True or not OUT_TOML.exists():
        if not OUT_TOML.exists():
            print("\"pyproject.toml\" not found in project ROOT. Generating ")
        work_and_exit()
    
    if not HASHMAPS.exists():
        print("hashmap.py does not exist, generating pyproject.toml (which builds hashmap.py at the end)")
        file_hash=None
        lines_hash=None
        work_and_exit()

    else:
        # It was easier to just copy the code from internals/hash.py
        # then to change it to hold variables and assign them dinamically
        from hashlib import sha256

        from uv_req_sync.hashmap import file_hash
        from uv_req_sync.hashmap import list_lines_hash as lines_hash


        h=sha256()
        with open(REQS_DOT_TXT, "rb") as f:
                    for chunk in iter(lambda: f.read(65536), b""):
                        h.update(chunk)
        filehash_totest = h.hexdigest()

        with open(REQS_DOT_TXT, "rb") as f:
            lines=f.readlines()

        hash_lines_totest:list[dict[int, str]]=[]

        for i, line in enumerate(lines):
            line = line.rstrip(b"\r\n")
            linha_hash=sha256(line).hexdigest()
            hash_lines_totest.append({i:f"{linha_hash}"})
    
    if filehash_totest.strip() == file_hash or hash_lines_totest == lines_hash:
        print("File's hashes for requirements.txt are the same\nNo need to check for versioning\n")
        exit(0)
    else:
        print("requirements.txt' hashes are different between stored hashmap and freshly generated!")
        print("requirements.txt' was probably changed!")
        print("Regenerating pyproject.toml")
        process()
        

if __name__ ==  "__main__":
    main()