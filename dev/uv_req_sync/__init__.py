import tomllib
from pathlib import Path

from _internals.authors import authors_processing
from _internals.parse_reqs_txt import comms, versionated

# Main needs to have a check when asking for the stored 
# hash for the requirements.txt file

def check_and_return(group:dict, key:str) -> str:
    "Asks for user input for the key [str] on the group [dict]"
    test=input(f"{group}[\"{key}\"] is {group[key]}\nWould you like to change it?\n(Y)es (N)o\n(Default is no)\n")
    if test.lower == "y":
        new_value = input("What value to put into {group}[\"{key}\"]")
        group[key] = new_value
        return group[key]

    else:
        return group[key]

def compare_deps(deps:list[str], versionated:list[str]) -> None:
    """
    For every item on deps(toml) checks it's equal to versionated[i].
    If so continue. If not try the next i up until the end of 
    versionated. If it checks everyone and fails to find a correspon
    """
    for item in deps:
        i=0
        for _ in range(versionated):
            try:
                if item == versionated[i]:
                    continue
                else:
                    #check weather the MOD NAME is there
                    #if so change it
                    i+=1
            except IndexError as e:
                
                print(f"{e}:{item}")
                deps.append(versionated[i])

root=Path(__file__).parent.parent.parent
out_toml=root/"pyproject.toml"

#Read the base pyproject.toml
dev_slash_uv=Path(__file__).parent
og_toml=dev_slash_uv / "pyproject.toml"
with open(og_toml,"rb") as toml_file:
    og_toml_data= tomllib.load(toml_file,parse_float=str)

#This ensures that the old file stays the same, for now
data=og_toml_data.copy()

#Project tag

# Can add a recursive function akeen to the way authors_processing, or even better
# have this be based on arg parse
project=data["project"]
project["name"]=check_and_return(project,"name")
project["version"]=check_and_return(project,"version")
project["description"]=check_and_return(project,"description")
project["readme"]=check_and_return(project,"readme")
project["authors"]=authors_processing(project["authors"])
project["requires-python"]=check_and_return(project,"requires-python")
toml_deps:list[str]=compare_deps(project["dependencies"],versionated)



# Scripts is already configured, it depends on project's 
# main entrypoint, so it is easier to "manually"config
# 
# If at some point these thing need to be added
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