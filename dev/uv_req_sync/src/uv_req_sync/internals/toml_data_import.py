"""Import some data from TOML template so the script don't makes circular imports by importing them from `__main__.py`"""
import tomllib
from pathlib import Path

_dev_slash_uv=Path(__file__).parent.parent.parent.parent
_template=_dev_slash_uv /"template"/"pyproject.toml"
with open(_template,"rb") as _toml_file:
    _template_data= tomllib.load(_toml_file,parse_float=str)

_data=_template_data.copy()
_project:dict=_data["project"]
module_dependencies:list[str]=_project["dependencies"]