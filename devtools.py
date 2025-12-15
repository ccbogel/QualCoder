# Extracts all the translatable strings from all python files in the 
# qualcoder subdirectory, then integrates new strings into the 
# existing ".po" files, ready to be translated.
# Written by Kai Dröge (and ChatGPT)

import os
import subprocess
import sys
from PyQt5.QtCore import QLibraryInfo
import polib

def extract_pot_file(directory, pot_filename):
    # List all .py files within the specified directory
    py_files = []
    for root, dirs, files in os.walk(directory):
        for file in files:
            if file.endswith('.py'):
                py_files.append(os.path.join(root, file))

    # Run xgettext to create the .pot file
    if py_files:
        try:
            subprocess.run(
                ['xgettext', '--language=Python', '--keyword=_',
                 '--output', pot_filename] + py_files,
                check=True
            )
            print(f"Extracted POT file: {pot_filename}")
        except subprocess.CalledProcessError as exc:
            print(f"Error creating POT file: {exc}")
    else:
        print("No Python files found to extract translatable strings from.")

def update_po_files(directory, pot_filename):
    # List all .po files within the specified directory
    for root, dirs, files in os.walk(directory):
        for file in files:
            if file.endswith('.po'):
                po_file = os.path.join(root, file)
                try:
                    # Update each .po file using msgmerge
                    subprocess.run(
                        ['msgmerge', '--update', po_file, pot_filename],
                        check=True
                    )
                    print(f"Updated PO file: {po_file}")
                except subprocess.CalledProcessError as exc:
                    print(f"Error updating PO file {po_file}: {exc}")

def update_qt_ts_files(directory):
    pylupdate_path = os.path.join(QLibraryInfo.location(QLibraryInfo.BinariesPath), "pylupdate5")
    translation_files = ["app_de.ts", "app_es.ts", "app_fr.ts", "app_it.ts", "app_ja.ts",
                     "app_pt.ts", "app_sv.ts", "app_zh.ts"]
    os.chdir(directory)
    for translation in translation_files:
        ui_files = [f for f in os.listdir(directory) if f.startswith("ui_")]
        cmd = [pylupdate_path, "-noobsolete", "-ts", translation] + ui_files
        print(f">>> {' '.join(cmd)}")
        subprocess.call(cmd)

def update_translation():
    directory = os.path.join('src', 'qualcoder')
    pot_filename = os.path.join(directory, 'qualcoder.pot')
    extract_pot_file(directory, pot_filename)
    update_po_files(directory, pot_filename)
    update_qt_ts_files(os.path.join('src', 'qualcoder', 'GUI'))

def rebuild_ui():
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

def recompile_translation():
    project_root = os.path.dirname(os.path.abspath(__file__))
    lrelease_path = "C:\\Users\\kai\\anaconda3\\envs\\QualCOder\\Lib\\site-packages\\qt6_applications\\Qt\\bin\\lrelease.exe"

    language_list = ['de', 'en', 'es', 'fr', 'it', 'pt']

    # GETTEXT TRANSLATION

    # .po-files
    po_dir = os.path.join(project_root, "src", "qualcoder")
    po_files = []
    for lang in language_list:
        po_files.append(os.path.join(po_dir, f'{lang}.po'))

    # .mo-files
    mo_basedir = os.path.join(project_root, "src", "qualcoder", "locale")
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
    ts_dir = os.path.join(project_root, "src", "qualcoder", 'GUI')
    ts_files = []
    for lang in language_list:
        ts_files.append(os.path.join(ts_dir, f'app_{lang}.ts'))

    # .qm-files
    qm_basedir = os.path.join(project_root, "src", "qualcoder", "locale")
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
        os.chdir(os.path.join(project_root, "src", 'qualcoder', 'locale'))
        cmd = os.path.join(project_root, "src", 'qualcoder', 'locale', 'create_lang_script_base64.py')
        subprocess.call(cmd, shell=True)
        print('Updated base_64_lang_helper.py')
        
    print("Finished")
 
def main():
    print("Please choose option")
    
if __name__ == "__main__":
    if len(sys.argv) > 1:
        mode = sys.argv[1]
        if mode == "--update-translation":
           update_translation()
         elif mode == "--compilation-translation":
            recompile_translation()
        elif mode == "--rebuild-ui":
            rebuild_ui()
        else:
            main()
    else:
        main()
