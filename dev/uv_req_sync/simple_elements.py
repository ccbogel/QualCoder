# Base and modifiable elemnts
qc_version:str="4.0.0"
py_version:float=3.12
authors=[[
  "{ name = \"Colin Curtain\", email = \"ccbogel@hotmail.com\" },",
  "{ name = \"Kai Dröge\" },",
  "{ name = \"Justin Missaghieh-Poncet\" }",
  "{ name = \"Lorenzo Salomón Cárdenas\" },",
]]

# Least modifiable elements
header:str = f""" \
# ------
# PyProject.toml - required for uv, ruff, ty and appimage
# ------
# Due to pypy's and uv's interaction being really
# specific, torch modules needed to be pinned

[project]
name = \"qualcoder\"
version = \"{qc_version}\"
description = "The free, open source desktop software for qualitative data analysis"
readme = \"README.md\"
authors = {authors}
requires-python = ">={py_version}"
"""

build_s_and_dev_deps="""\
[build-system]
requires = ["uv_build>=0.12.21,<0.13.0"]
build-backend = "uv_build"

[dependency-groups]
dev = [
    "appimage>=4.1.0",
    "pytest>=9.2.0",
    "ruff>=0.17.3",
    "ty>=0.0.96",
    "uv>=0.13.6",
]
"""

entrypoint_script=""" \
[project.scripts]
qualcoder = "qualcoder.__main__:gui"
"""