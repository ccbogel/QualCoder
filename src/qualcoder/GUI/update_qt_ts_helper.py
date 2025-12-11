#!/usr/bin/python
# -*- coding: utf-8 -*-

"""
This helper file updates the app_.ts files in GUI folder
Works with pylupdate5
pylupdate6 does not work

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:
backup
The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.

https://github.com/ccbogel/QualCoder
https://qualcoder.wordpress.com/
Colin Curtain 2025
"""

import os
import subprocess
project_root = os.path.dirname(os.path.abspath(__file__))
translation_files = ["app_de.ts", "app_es.ts", "app_fr.ts", "app_it.ts", "app_ja.ts",
                     "app_pt.ts", "app_sv.ts", "app_zh.ts"]

# Run from the qualcoder/GUI directory
for translation in translation_files:
    cmd = "pylupdate5 "
    for file in os.listdir():
        if file.startswith ("ui_"):
            cmd += file + " "
    cmd += f"-noobsolete -ts {translation}"
    print(f">>> {cmd}")
    subprocess.call(cmd, shell=True)

print("Finished")
