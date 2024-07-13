"""
This simple helper script checks if any of the .ui-files has been updated and needs recompiling.
If so, pyuic6 is used to compile it, the result is placed in "qualcoder/GUI"

Kai Dröge 2023
"""

import os
import subprocess

script_dir = os.path.dirname(os.path.abspath(__file__))

# path to .ui-files
ui_dir = os.path.join(script_dir, "GUI_UIs")

# path to .py-files
py_dir = os.path.join(script_dir, "qualcoder", "GUI")

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