"""Parse requirements.txt"""
import re
from pathlib import Path

from uv_req_sync.internals.toml_data_import import (
  toml_module_dependencies_normalized as toml_deps_normalized,
)


def find_index(index_name:str, reqs_lines:list[str])->tuple[str,str]|tuple[str, None]|tuple[None,None]:
  """Seacrh the list of lines for an expression and then returns 
  the url and a comment, if any"""

  for idx, line in enumerate(reqs_lines):
    pattern=f"--{index_name}"
    found = re.match(fr"^({pattern})", line)
    if found:
      arg=found.group()
      line_new=line.replace(arg,"")
      line=line_new
      try:
        line, comm = line.split("#")
      except ValueError:
        comm=None
      if comm:
        comm=f"# {comm}"
        line= line.replace(comm,"").strip()

      line=line.strip()
      reqs_lines.pop(idx)
      if comm != None:
        return line, comm.strip()  
      else: 
        return line, None
  return None, None

def strip_comments_from_line_list(line_list:list[str],comms:list[dict])->tuple[list[str],list[dict]]:
  """Only removes if coments is in start of a line"""
  poppers=[]
  for idx, line in enumerate(line_list.copy()):
    has_comment = re.match(r'#',line)
    if has_comment:
      comment_starts_line = re.match(r'^#.*$',line)
      # As off now only one dep has comments above it on the reqs lists: pefile.
      # So it is (for now) not necessary to check for this
      if comment_starts_line:
        comms.append({"pefile_before":comment_starts_line.group()})
        poppers.append(idx)
        continue
        
  for idx in sorted(poppers, reverse=True):
      reqs_lines.pop(idx)
  return reqs_lines, comms

def search_for_comm_see(reqs_lines:list[str], comms:list[dict])->tuple[list[str],list[dict]]:
  """Almost same logic as other functions but, for some reason, python did not liked when I putted
  this inside other functions"""
  for idx, line in enumerate(reqs_lines):
    check:re.Match[str]|None=re.search(r"# ", line)
    if check is None:
        continue
    line, comm = line.split("# ")
    line_key = re.sub(r'(\.|>|=|[0-9]|<)',"",line)
    comms.append({line_key.strip():f"# {comm}"})
    reqs_lines[idx]=line
      
  return reqs_lines, comms


def check_versionated_or_new(reqs_lines:list[str], toml_deps_normalized:list[str])->tuple[list[str],list[str]]:
  """This one takes the whole list of deps and returns only the ones that
  have versionated notes or new requirements"""
  versionated_or_new=[]
  for line in reqs_lines:
    search:re.Match[str]|None=re.search(r">=|<=|==|<|>",line)
    line_mod_name = re.sub(r'[<>=!~]=?\s*\d+(?:\.\d+)*',"",line).replace("_","-")\
      .replace("pdfminer.six","pdfminer-six").strip().lower()
    # needed .lower() because requirements.txt use, sometimes CamelCase (Pillow -> pillow; Bio -> bio)
    # json-repair vs json_repair ->.replace
    # pdfminer.six -> .replace
    if search is None and line_mod_name in toml_deps_normalized:
      continue
    versionated_or_new.append(line.strip().lower())

  return versionated_or_new, reqs_lines

#Main

root:Path=Path(__file__).parent.parent.parent.parent.parent.parent
reqs_dot_txt:Path= root / "requirements.txt"

with open(reqs_dot_txt,"r") as f:
  reqs_lines:list[str]=f.readlines()

comms = [] 

index,comm_index = find_index("index-url",reqs_lines)
comms.append({"index":comm_index})

extra_index,comm_extra_index = find_index("extra-index-url",reqs_lines)

reqs_lines, comms = strip_comments_from_line_list(reqs_lines, comms)

reqs_lines, comms = search_for_comm_see(reqs_lines, comms)

versionated_or_new, reqs_lines = check_versionated_or_new(reqs_lines, toml_deps_normalized)