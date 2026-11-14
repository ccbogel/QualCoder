"""Change the line based on the key of the comment to be line + comment in a myriad of ways. Originally this was a nested 
loop inside where this functions is called. However this was needed to be moved to a function that reassigned the values of
pyproject_lines/lines_list comment_poppers/poppers"""
import re
from copy import copy

_RE=re.compile(r'([0-9]|\.|\,|<|>|=)')

def comment_logic(comment_index:int,comment:dict[str,str],lines_list:list[str],poppers:list[int])->tuple[list[str],list[int]] :
    """Change the line based on the key of the comment to be line + comment in a myriad of ways. Originally this was a nested 
    loop inside where this functions is called. However this was needed to be moved to a function that reassigned the values of
    pyproject_lines/lines_list comment_poppers/poppers"""
    found_generic:bool=False
    # k is the key for the comment
    k:str=next(iter(comment.keys()))
    # v is the comment
    v:str=next(iter(comment.values()))
    # Added the portuguese for line (linha) so the variable has a different name
    # while the "meaning" remains the same
    for i, linha in enumerate(lines_list):
        linha_stripped=copy(linha).replace("'","").replace('"','').replace("\n","").strip()
        linha_expression=_RE.sub("",linha_stripped).strip()
        if re.search(r'_',k):
            try:
                part1, part2 = k.split("_")
            except ValueError as e:
                print(e)
                part1=None
                part2=None
            if linha_expression == part1 and part2 != None:
                match part2:
                    case "before":
                        new_line=f"{v}\n{linha}"    
                        lines_list[i]=new_line
                        poppers.append(comment_index)
                    # as of now there's no comment after a line
                    # so it is commented
                    #case "after":
                    #    new_line=f"{linha}\n{v}"    
                    #    lines_list[i]=new_line
                    #    poppers.append(idx)
                break # leaves internal loop
        elif k == "index" and linha.strip() == "[tool.uv]":
                new_line=f"{v}\n{linha}"    
                lines_list[i]=new_line
                poppers.append(comment_index)
                break # leaves internal loop
        elif k.strip() == linha_expression.strip():
            found_generic=True 
            break # leaves internal loop -> goes to next of comment loop
        else: continue # go to next of the internal
    if found_generic == True:
        new_line=f"{linha.replace("\n","")} {v.replace("\n","")}\n"
        lines_list[i]=new_line
        poppers.append(comment_index)
    
    return lines_list, poppers