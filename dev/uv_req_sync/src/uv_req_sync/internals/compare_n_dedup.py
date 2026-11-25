"""
Dedups the requirements list. Since the logic of the comparison on `parse_reqs.txt` adds the "new" lines at the end of `req_list`
it is important to dedup that list giving priority for the newer/latter items of the list
---

This file is part of QualCoder.

QualCoder is free software: you can redistribute it and/or modify it under the
terms of the GNU Lesser General Public License as published by the Free Software
Foundation, either version 3 of the License, or (at your option) any later version.

QualCoder is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY;
without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
See the GNU General Public License for more details.

You should have received a copy of the GNU Lesser General Public License along with QualCoder.
If not, see <https://www.gnu.org/licenses/>.

Author: Alberto Antonio Rebonatto Neto (BetoNetu)
https://github.com/ccbogel/QualCoder
https://qualcoder-org.github.io
https://qualcoder.wordpress.com/
https://qualcoder.org/
"""
import re

_NAME_RE = re.compile(r'^\s*([A-Za-z0-9_.\-]+)')

def _mod_name(dep: str) -> str:
    m = _NAME_RE.match(dep)
    if m is None:
        raise ValueError(f"invalid dependency spec: {dep!r}")
    return m.group(1).lower()

def compare_deps(deps: list[str], versionated: list[str]) -> list[str]:
    """Dedups the requirements list. Since the logic of the comparison on `parse_reqs.txt` adds the "new" lines at the end of `req_list`
    it is important to dedup that list giving priority for the newer/latter items of the list"""
    poppers=[]
    print("Starting dependencies comparison")
# Start from deps, then overlay any versionated entries that are newer
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