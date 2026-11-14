"""Parse requirements.txt"""
import re
from pathlib import Path

from uv_req_sync.internals.toml_data_import import (
  toml_module_dependencies_normalized as toml_deps_normalized,
)


def _find_index(index_name:str, line_list:list[str])->tuple[str,str]|tuple[str, None]|tuple[None,None]:
  """Seacrh the list of lines for an expression and then returns 
  the url and a comment, if any"""

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
        return line, comm.strip()  
      else: 
        return line, None
  return None, None

def _strip_comments_from_line_start(line_list:list[str],comments:list[dict])->tuple[list[str],list[dict]]:
  """Only removes if coments is in start of a line"""
  poppers=[]
  for idx, line in enumerate(line_list.copy()):
    has_comment = re.match(r'#',line)
    if has_comment:
      comment_starts_line = re.match(r'^#.*$',line)
      # As off now only one dep has comments above it on the reqs lists: pefile.
      # So it is (for now) not necessary to add custom logic for this
      if comment_starts_line:
        comments.append({"pefile_before":comment_starts_line.group()})
        poppers.append(idx)
        continue
        
  for idx in sorted(poppers, reverse=True):
      line_list.pop(idx)
  return line_list, comments

def _strip_comment_in_the_middle_of_line(line_list:list[str], comments:list[dict[str,str]])->tuple[list[str],list[dict]]:
  """Almost same logic as other functions but, for some reason, python did not liked when I putted
  this inside other functions"""
  for idx, line in enumerate(line_list):
    check:re.Match[str]|None=re.search(r"# ", line)
    if check is None:
        continue
    line, comm = line.split("# ")
    line_key = re.sub(r'(\.|>|=|[0-9]|<)',"",line)
    comments.append({line_key.strip():f"# {comm}"})
    line_list[idx]=line
      
  return line_list, comments

def _dedup_comments(comment_list:list[dict[str,str]]) -> list[dict[str,str]]:
  """Dedups comments based on the key"""
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
      comment_list[idx-1]={k_previous.strip():f"{v_previous}\n{v_current}"}
      poppers.append(idx)
      comment_list.pop(idx)
  
  return comment_list


def _check_versionated_or_new(line_list:list[str], toml_deps_normalized:list[str])->tuple[list[str],list[str]]:
  """This one takes the whole list of deps and returns only the ones that
  have versionated notes or new requirements"""
  versionated_or_new=[]
  for line in line_list:
    search:re.Match[str]|None=re.search(r">=|<=|==|<|>",line)
    line_mod_name = re.sub(r'[<>=!~]=?\s*\d+(?:\.\d+)*',"",line).replace("_","-")\
      .replace("pdfminer.six","pdfminer-six").strip().lower()
    # needed .lower() because requirements.txt use, sometimes CamelCase (Pillow -> pillow; Bio -> bio)
    # json-repair vs json_repair ->.replace
    # pdfminer.six -> .replace
    if search is None and line_mod_name in toml_deps_normalized:
      continue
    versionated_or_new.append(line.strip().lower())

  return versionated_or_new, line_list

#Main

root:Path=Path(__file__).parent.parent.parent.parent.parent.parent
reqs_dot_txt:Path= root / "requirements.txt"
with open(reqs_dot_txt,"r") as f:
  _reqs_lines:list[str]=f.readlines()

_comments = []
_index,_comment_index = _find_index("index-url",_reqs_lines)
_comments.append({"index":_comment_index})
_extra_index,_comment_extra_index = _find_index("extra-index-url",_reqs_lines)
_reqs_lines, _comments = _strip_comments_from_line_start(_reqs_lines, _comments)
_reqs_lines, _comments = _strip_comment_in_the_middle_of_line(_reqs_lines, _comments)

#Callable
comments=_dedup_comments(_comments)
versionated_or_new, reqs_lines = _check_versionated_or_new(_reqs_lines, toml_deps_normalized)