import re


def compare_deps(deps:list[str], versionated:list[str]):
    """
    For every item on deps(toml) checks if it's equal to versionated[i].
    If so continue. If not try the next i up until the end of 
    versionated. If it checks everyone and fails to find a match
    adds that entry to new_deps_list. it also dedups the list
    """
    added_lines=[]
    new_deps_list = deps.copy()
    for item in new_deps_list:
        for i in range(len(versionated)):
            try:
                if item == versionated[i]:
                    continue
                else:
                    #check weather the MOD NAME is there
                    #if so change it
                    i+=1
            except IndexError as e:
                print(f"{e}:{item}")
                new_deps_list.append(versionated[i])
                added_lines.append(versionated[i])
    
    # Since the newer versions/deps are always appended, it is best to hold this mutable list
    # so it dont pops a dep twice. Also  The way this was build is to pop the list all at
    # once by idx, so the logic here with will_be_popped and poppers is the first match for a line 
    # occurs it is assumed (because of what we just talked about this comparison logic) 

    # Names already whose indexes are already marked to pop
    will_be_popped=[]
    # Indexes to pop
    poppers=[]
    for idx in range(len(new_deps_list)):
        dep_mod_name=re.sub(r'[<>=!~]=?\s*\d+(?:\.\d+)*',"",new_deps_list.copy()[idx]).strip()
        for each in added_lines:
            added_lines_dep_name = re.sub(r'[<>=!~]=?\s*\d+(?:\.\d+)*',"",each).strip()
            if dep_mod_name != added_lines_dep_name or dep_mod_name in will_be_popped:
                continue
            else:
                will_be_popped.append(dep_mod_name.strip())
                poppers.append(idx)

    for idx in sorted(poppers, reverse=True):
        new_deps_list.pop(idx)

    return new_deps_list

if __name__ == "__main__":
    deps = []
    versionated = []    