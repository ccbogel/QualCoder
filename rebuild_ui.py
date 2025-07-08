#!/usr/bin/python
# -*- coding: utf-8 -*-

"""
This simple helper script checks if any of the .ui-files has been updated and needs recompiling.
If so, pyuic6 is used to compile it, the result is placed in "qualcoder/GUI"

Kai Dröge 2023

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
"""

import os
import subprocess

project_root = os.path.dirname(os.path.abspath(__file__))

# path to .ui-files
ui_dir = os.path.join(project_root, "src", "GUI_UIs")

# path to .py-files
py_dir = os.path.join(project_root, "src", "qualcoder", "GUI")

for file in os.listdir(ui_dir):
    if file.endswith(".ui"):
        ui_path = os.path.join(ui_dir, file)
        py_file = file[:-3] + ".py"
        py_path = os.path.join(py_dir, py_file)
        # Check if ui-file has been updated and is newer than the corresponding py-file
        if (os.path.exists(py_path) == False) or (os.path.getmtime(ui_path) > os.path.getmtime(py_path)):
            cmd = f"pyuic6 {ui_path} -o {py_path}"
            answer = input(f'Do you want to create/update "{py_path}"? (y/n)')
            if answer == 'y':
                # print(f">>> {cmd}")
                subprocess.call(cmd, shell=True)
                print(f"{py_file} has been updated.")
            else:
                print(f'Skipping "{py_path}".')

print("Finished")
