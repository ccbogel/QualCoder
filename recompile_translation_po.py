"""
This simple helper script checks if any of the .po- or .mo-files has been updated and needs recompiling.

Kai Dröge 2024
"""

import os
import subprocess
import polib

script_dir = os.path.dirname(os.path.abspath(__file__))
lrelease_path = "C:\\Users\\kai\\anaconda3\\envs\\QualCOder\\Lib\\site-packages\\qt6_applications\\Qt\\bin\\lrelease.exe"

language_list = ['de', 'en', 'es', 'fr', 'it', 'pt']

# GETTEXT TRANSLATION

# .po-files
po_dir = os.path.join(script_dir, "qualcoder")
po_files = []
for lang in language_list:
    po_files.append(os.path.join(po_dir, f'{lang}.po'))

# .mo-files
mo_basedir = os.path.join(script_dir, "qualcoder", "locale")
mo_files = []
for lang in language_list:
    mo_files.append(os.path.join(mo_basedir, lang, 'LC_MESSAGES', f'{lang}.mo'))

for i in range(len(po_files)):
    po_file = po_files[i]
    mo_file = mo_files[i]
    if os.path.exists(po_file):
        # Check if po-file has been updated and is newer than the corresponding mo-file
        if (os.path.exists(mo_file) == False) or (os.path.getmtime(po_file) > os.path.getmtime(mo_file)):
            answer = input(f'Do you want to create/update "{mo_file}"? (y/n)')
            if answer == 'y':
                po = polib.pofile(po_file)
                po.save_as_mofile(mo_file)
                print(f"{mo_file} has been updated.")
            else:
                print(f'Skipping "{mo_file}".')

# Qt TRANSLATIONS

# .ts-files
ts_dir = os.path.join(script_dir, "qualcoder", 'GUI')
ts_files = []
for lang in language_list:
    ts_files.append(os.path.join(ts_dir, f'app_{lang}.ts'))

# .qm-files
qm_basedir = os.path.join(script_dir, "qualcoder", "locale")
qm_files = []
for lang in language_list:
    qm_files.append(os.path.join(qm_basedir, lang, f'app_{lang}.qm'))

for i in range(len(ts_files)):
    ts_file = ts_files[i]
    qm_file = qm_files[i]
    if os.path.exists(ts_file):
        # Check if ts-file has been updated and is newer than the corresponding qm-file
        if (os.path.exists(qm_file) == False) or (os.path.getmtime(ts_file) > os.path.getmtime(qm_file)):
            answer = input(f'Do you want to create/update "{qm_file}"? (y/n)')
            if answer == 'y':
                subprocess.run([lrelease_path, ts_file, "-qm", qm_file], check=True)
                print(f"{qm_file} has been updated.")
            else:
                print(f'Skipping "{qm_file}".')

# update base_64_lang_helper.py

answer = input(f'Do you want to update "base_64_lang_helper.py"? (y/n)')
if answer == 'y':
    os.chdir(os.path.join(script_dir, 'qualcoder', 'locale'))
    cmd = os.path.join(script_dir, 'qualcoder', 'locale', 'create_lang_script_base64.py')
    subprocess.call(cmd, shell=True)
    print('Updated base_64_lang_helper.py')
    
print("Finished")