import re
from pathlib import Path

import tomllib

dev_slash_uv=Path(__file__).parent.parent
og_toml=dev_slash_uv / "origin.toml"
with open(og_toml,"rb") as toml_file:
    og_toml_data= tomllib.load(toml_file,parse_float=str)

data=og_toml_data.copy()
project:dict=data["project"]
module_dependencies:list[str]=project["dependencies"]


toml_module_dependencies_normalized:list[str]=[]
for dep in module_dependencies:
    dep_norm:str = re.sub(r'[<>=!~]=?\s*\d+(?:\.\d+)*',"",dep)
    toml_module_dependencies_normalized.append(dep_norm)
print(toml_module_dependencies_normalized)