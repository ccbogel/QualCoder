"""Parse requirements.txt by removing arguments from lines and returning them to __main__.py.
The removed arguments are then passed as a list[dict[str,str]] in which each dir is of size 1
and contains a key descripting it's location relative to it's"""

import re

from uv_req_sync.internals.toml_data_import import (
  module_dependencies as toml_deps,
)


def _remove_blank_lines(line_list:list[str]) -> list[str]:
  line_list_out=[]
  for line in line_list:
    line=line.strip()
    if line == "" or line == "\n":
      continue
    line_list_out.append(line)
  return line_list_out


def _find_index(index_name:str, line_list:list[str])->tuple[str,str]|tuple[str, None]|tuple[None,None]:
  """Seacrh the list of lines for an expression and then returns the url and a comment, if any"""

  print(f"Finding index comment for {index_name}")
  for idx, line in enumerate(line_list):
    
    _pattern=f"--{index_name}"
    _found = re.match(fr"^({_pattern})", line)
    if _found:
      _arg=_found.group()
      line_new=line.replace(_arg,"")
      line=line_new
      try:
        line, comm = line.split("#")
      except ValueError:
        comm=None
      if comm:
        comm=f"# {comm}"
        line= line.replace(comm,"").strip()

      line=line.strip()
      line_list.pop(idx)
      if comm != None:
        print(f"Comment {comm.strip()} found for {index_name}")
        return line, comm.strip()  
      else: 
        print(f"No comment found for {index_name}")
        return line, None
  return None, None

def _strip_comments_from_line_start(line_list:list[str],comments:list[dict[str,str]])->tuple[list[str],list[dict[str,str]]]:
  """Only removes comments if they start a line. The removed comment is then added to a dict with a key that """
  poppers=[]
  for idx, line in enumerate(line_list.copy()):
    has_comment = re.match(r'#',line)
    comment_starts_line = re.match(r'^#.*$',line)
    if has_comment and comment_starts_line:
      print(f"Comment {line} found")
      # As off now only one dep has comments above it on the reqs lists: pefile.
      # So it is (for now) not necessary to add custom logic for this or for 
      # considering their position in relation to an actual dependency
      comments.append({"pefile_before":comment_starts_line.group()})
      poppers.append(idx)
      continue
        
  for idx in sorted(poppers, reverse=True):
      line_list.pop(idx)
  print("Comments from single lines removed!")
  return line_list, comments

def _strip_comment_in_the_middle_of_line(line_list:list[str], comments:list[dict[str,str]])->tuple[list[str],list[dict]]:
  print("Removing comments from lines!")
  """Removes comments at the end of the lines. """
  for idx, line in enumerate(line_list):
    check:re.Match[str]|None=re.search(r"# ", line)
    if check is None:
        continue
    line, comm = line.split("# ")
    print(f"{comm} found right beside {line}")
    line_key = re.sub(r'(\.|>|=|[0-9]|<)',"",line)
    comments.append({line_key.strip():f"# {comm}"})
    line_list[idx]=line
  
  print("Comments removed from all lines!")
  return line_list, comments

def _dedup_comments(comment_list:list[dict[str,str]]) -> list[dict[str,str]]:
  """Dedups comments based on the key each comment has. If they have the same key, they are concatenated
  into the same string with a \\n in between"""
  print("Comment deduping started\n")
  poppers:list[int]=[]
  
  for idx, comment in enumerate(comment_list):
    # k is the key for the comment
    k_current:str=next(iter(comment.keys()))
    # v is the comment
    v_current:str=next(iter(comment.values()))
    if idx-1 < 0:
      continue
    k_previous=next(iter(comment_list[idx-1].keys()))
    v_previous=next(iter(comment_list[idx-1].values()))
    if k_current.strip() != k_previous.strip():
      continue
    else:
      print(f"{v_current}'s key:{k_current} is the same as {v_previous}\nMerging them...\n")
      comment_list[idx-1]={k_previous.strip():f"{v_previous}\n{v_current}"}
      print("Comments merged")
      poppers.append(idx)
      
  for i in sorted(poppers, reverse=True):
    print(f"Popping {next(iter(comment_list[i].values()))}")
    comment_list.pop(i)
  
  print("Comment deduping concluded\n")
  return comment_list

def _check_versionated_or_new(line_list:list[str], toml_deps:list[str])->tuple[list[str],list[str]]:
  """Takes the whole list of deps and returns only the ones that
  have versionated notes or are different then what was on the toml template"""
  versionated_or_new=[]
  for line in line_list:
    line = line.replace("_","-").replace("pdfminer.six","pdfminer-six").strip().lower()
    # needed .lower() because requirements.txt use, sometimes CamelCase (Pillow -> pillow; Bio -> bio)
    # json-repair vs json_repair ->.replace
    # pdfminer.six -> .replace
    if line in toml_deps:
      continue
    versionated_or_new.append(line.strip().lower())

  return versionated_or_new, line_list

def parsing_reqs_dot_txt(reqs_dot_txt) -> tuple[list[dict[str, str]],list[str],list[str]]:
  """Congrates the logic of this internal module. Being responsible for separating the comments from the 
  bulk of the lines, stripping blank lines and organizing the """
  print("Parsing requirements.txt started" )
  print("Opening requirements.txt")
  with open(reqs_dot_txt,"r") as f:
    _reqs_lines:list[str]=f.readlines()

  _reqs_lines=_remove_blank_lines(_reqs_lines)
  _comments:list[dict[str,str]] = []

  _index,_comment_index = _find_index("index-url",_reqs_lines)
  if _comment_index is not None:
    _comment_index_dict:dict[str,str]={"index":_comment_index}  
    _comments.append(_comment_index_dict)
  _extra_index,_comment_extra_index = _find_index("extra-index-url",_reqs_lines)
  # _comment_index is manually added because uv defaults to PyPi and only sources specific packages 
  # when configured. Also and _extra_index are _comment_extra_index "generated" so the line is removed
  # from the line list
  _reqs_lines, _comments = _strip_comments_from_line_start(_reqs_lines, _comments)  
  _reqs_lines, _comments = _strip_comment_in_the_middle_of_line(_reqs_lines, _comments)
  comments=_dedup_comments(_comments)
  versionated_or_new, reqs_lines = _check_versionated_or_new(_reqs_lines, toml_deps)

  return comments, versionated_or_new, reqs_lines