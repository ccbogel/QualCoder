"""
This file contains every specialy indexed dependency module
(i.e. it is not sourced directly from pypi). These modules need
to be named on uv as a dependency due to how uv indexing is configured
to work on this project
"""
specially_indexed:list[str]=\
[
    "torch",
    "torchaudio",
    "torchvision",
]