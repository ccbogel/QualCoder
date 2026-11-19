"""Dedups the reqs list"""
import re

_NAME_RE = re.compile(r'^\s*([A-Za-z0-9_.\-]+)')

def _mod_name(dep: str) -> str:
    m = _NAME_RE.match(dep)
    if m is None:
        raise ValueError(f"invalid dependency spec: {dep!r}")
    return m.group(1).lower()

def compare_deps(deps: list[str], versionated: list[str]) -> list[str]:
    poppers=[]
    print("Starting dependencies comparison")
    # start from deps, then overlay any versionated entries that are newer
    try:
        by_name: dict[str, str] = {}
        for i, d in enumerate( deps):
            by_name[_mod_name(d)] = d         # deps first
        for i, v in enumerate(versionated):
            print(f"{v} is newer then {d}.\nAdding {v}")
            by_name[_mod_name(v)] = v          # newer wins
    
    #Dealing with blank lines
    except ValueError:
        print("A blank line was detetcted")
        print("Marking it for removal")
        poppers.append(i)

    if len(poppers) > 0:
        print(f"Popping blank {len(poppers)} lines")
        for each, _ in sorted(enumerate(poppers), reverse=True):
            del each

    print(f"{len(by_name)} dependencies compared")
    return sorted(by_name.values())