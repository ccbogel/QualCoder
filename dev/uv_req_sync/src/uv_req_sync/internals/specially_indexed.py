"""
This file contains every specialy indexed dependency module
(i.e. its not sourced directly from pypi). These modules need
to be named on uv as a dependency due to how uv indexing works
"""
specially_indexed:list[str]=\
[
    "torch",
    "torchaudio",
    "torchvision",
]