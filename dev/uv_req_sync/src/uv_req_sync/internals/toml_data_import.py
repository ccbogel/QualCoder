"""Import some data from toml so it don't do circular imports"""
import re
import tomllib
from pathlib import Path

dev_slash_uv=Path(__file__).parent.parent.parent.parent
template=dev_slash_uv /"template"/"pyproject.toml"
with open(template,"rb") as toml_file:
    template_data= tomllib.load(toml_file,parse_float=str)

data=template_data.copy()
project:dict=data["project"]
module_dependencies:list[str]=project["dependencies"]


toml_module_dependencies_normalized:list[str]=[]
for dep in module_dependencies:
    dep_norm:str = re.sub(r'[<>=!~]=?\s*\d+(?:\.\d+)*',"",dep)
    toml_module_dependencies_normalized.append(dep_norm)