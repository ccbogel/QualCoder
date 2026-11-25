"""
Import some data from TOML template so the script don't makes circular imports by importing them from `__main__.py`
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
import tomllib
from pathlib import Path

_dev_slash_uv=Path(__file__).parent.parent.parent.parent
_template=_dev_slash_uv /"template"/"pyproject.toml"
with open(_template,"rb") as _toml_file:
    _template_data= tomllib.load(_toml_file,parse_float=str)

_data=_template_data.copy()
_project:dict=_data["project"]
module_dependencies:list[str]=_project["dependencies"]