"""
Mutates the line from the toml based on the key of the comment_dict {key:comment} to be `f"{line} + {comment}"` in four ways (of which three are
currently implemented as they're are the only needed for now). See the description for function provided by 
this module for more information
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
from copy import copy
from textwrap import dedent

_RE=re.compile(r'([0-9]|\.|\,|<|>|=)')

def comment_logic(comment_index:int,comment:dict[str,str],lines_list:list[str],poppers:list[int])->tuple[list[str],list[int]] :
    """    
    Mutates the line based on the key of the comment to be line + comment in three ways. 
    
    Logic:
    
    Every comment is a dict with one item (schematically: `{k:str : v:str}`) in which:

    - `k` is the key that `parse_req_txt.py` assigns it and express it's "relation"/"placement"
    regarfing the line it acompanies on `requirements.txt`
    - `v` is the comment itself (with #)

    Below, one can find a schematic logic of this function and how it decides where the comment needs
    to be readded:

    ```python
    if "_" in k:
    #e.g. k = "pefile_before" -> True
        part1, part2 = k.split(_)
        match part2 in k:
            case "after": # this option is commented out as it not needed for now
                new_line=f"{line}\\n{comment}"
            case "before"
                new_line=f"{comment}\\n{line}"
    elif k == "index" and line == "[tool.uv]"
        new_line=f"{v}\\n{line}"
    elif k == line
        new_line=f"{line} {v}\\n"
    else
        continiue
    ```
    Originally this was a nested loop inside another loop(located where this functions is called). 
    However it needed to be moved to a function that reassigned the values of pyproject_lines/lines_list 
    and comment_poppers/poppers"""
    
    # "generic" means any regular comment that does
    # not have any particular distinct key (e.g. index,
    # "module_before")
    found_generic:bool=False
    
    # Every comment is a dict[str:str] with one item
    # k is the key for the comment
    k:str=next(iter(comment.keys()))
    # v is the comment
    v:str=next(iter(comment.values()))
    for i, line in enumerate(lines_list):
        line_stripped=copy(line).replace("'","").replace('"','').replace("\n","").strip()
        line_expression=_RE.sub("",line_stripped).strip()
        if re.search(r'_',k):
            
            try:
                part1, part2 = k.split("_")
            except ValueError as e:
                print(e)
                part1=None
                part2=None
                            
            if line_expression == part1 and part2 != None:
                match part2:
                    case "before":
                        new_line=f"{v}\n{line}"    
                        lines_list[i]=new_line
                        poppers.append(comment_index)
                    
                    # As of now, there's no comment after a line
                    # so it is commented. If it's ever needed, 
                    # it is here:
                    
                    # case "after":
                    #    new_line=f"{line}\n{v}"    
                    #    lines_list[i]=new_line
                    #    poppers.append(idx)

                print(f"Comment {v} added {part2} {part1}")
                break # leaves internal loop (aka this function)
        elif k == "index" and line.strip() == "[tool.uv]":
            new_line=f"{v}\n{line}"    
            lines_list[i]=new_line
            poppers.append(comment_index)
            print(f"Comment {v} added before {line.strip()}")
            break # leaves internal loop (aka this function)
        elif k.strip() == line_expression.strip():
            found_generic=True 
            break # leaves internal loop (aka this function)
        else: continue # go to next item of the internal loop (aka this function) 
    if found_generic == True:
        new_line=f"{line.replace("\n","")} {v.replace("\n","")}\n"
        lines_list[i]=new_line
        print(f"Adding {v.replace("\n","")} to the end of {dedent(line.replace("\n",""))}")
        poppers.append(comment_index)
    
    return lines_list, poppers