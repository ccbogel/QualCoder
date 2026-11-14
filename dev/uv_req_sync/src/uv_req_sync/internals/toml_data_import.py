"""Import some data from toml so it don't do circular imports"""
import re
import tomllib
from pathlib import Path

_dev_slash_uv=Path(__file__).parent.parent.parent.parent
_template=_dev_slash_uv /"template"/"pyproject.toml"
with open(_template,"rb") as _toml_file:
    _template_data= tomllib.load(_toml_file,parse_float=str)

_data=_template_data.copy()
_project:dict=_data["project"]
module_dependencies:list[str]=_project["dependencies"]


toml_module_dependencies_normalized:list[str]=[]
for _dep in module_dependencies:
    _dep_norm:str = re.sub(r'[<>=!~]=?\s*\d+(?:\.\d+)*',"",_dep)
    toml_module_dependencies_normalized.append(_dep_norm)