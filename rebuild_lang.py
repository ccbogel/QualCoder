"""
Using --update option
This script updates translation placeholders in .po and Qt .ts files.
Using --compile option
This script compiles .po to .mo files, and .ts to .qm files.
Requires polib and PyQt5

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
import sys
import polib


def extract_pot_file(directory, pot_filename):
    """ Called by: update_translation_placeholders """
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
    """ List all .po files within the specified directory.
    called by: update_translation_placeholders """
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


def update_qt_ts_files():
    """ Requires pyludate5
    pip install pyqt5-tools
    Run from QualCoder-master folder
    Warning: pylupdate6 overrides ,but does not update, existing ts files.
    CAlled by: update_translation_placeholders
    """

    translation_files = ["app_de.ts", "app_es.ts", "app_fr.ts", "app_it.ts", "app_ja.ts",
                         "app_pt.ts", "app_sv.ts", "app_zh.ts"]
    script_path = os.path.dirname(os.path.realpath(__file__))
    gui_directory = os.path.join(script_path, "src", "qualcoder", "GUI")
    print("GUI directory:", gui_directory)
    os.chdir(gui_directory)
    for translation in translation_files:
        cmd = "pylupdate5 "
        for file in os.listdir():
            if file.startswith("ui_"):
                cmd += f"{file} "
        cmd += f"-noobsolete -ts {translation}"
        print(f">>> {cmd}")
        subprocess.call(cmd, shell=True, cwd=gui_directory)


def update_translation_placeholders():
    """ Update po files, update GUI ts files """

    directory = os.path.join('src', 'qualcoder')
    pot_filename = os.path.join(directory, 'qualcoder.pot')
    extract_pot_file(directory, pot_filename)
    update_po_files(directory, pot_filename)
    update_qt_ts_files()


def recompile_translation():
    project_root = os.path.dirname(os.path.abspath(__file__))
    # lrelease_path = "C:\\Users\\kai\\anaconda3\\envs\\QualCOder\\Lib\\site-packages\\qt6_applications\\Qt\\bin\\lrelease.exe"
    # lrelease_path = "/usr/bin/lrelease"
    lrelease_path = 'lrelease'
    language_list = ['de', 'en', 'es', 'fr', 'it', 'ja', 'pt', 'sv', 'zh']

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
            if (os.path.exists(mo_file) is False) or (os.path.getmtime(po_file) > os.path.getmtime(mo_file)):
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
            if (os.path.exists(qm_file) is False) or (os.path.getmtime(ts_file) > os.path.getmtime(qm_file)):
                answer = input(f'Do you want to create/update "{qm_file}"? (y/n)')
                if answer == 'y':
                    subprocess.run([lrelease_path, ts_file, "-qm", qm_file], check=True)
                    print(f"{qm_file} has been updated.")
                else:
                    print(f'Skipping "{qm_file}".')

    # Update base_64_lang_helper.py
    answer = input(f'Do you want to update "base_64_lang_helper.py"? (y/n)')
    if answer == 'y':
        os.chdir(os.path.join(project_root, "src", 'qualcoder', 'locale'))
        cmd = os.path.join(project_root, "src", 'qualcoder', 'locale', 'create_lang_script_base64.py')
        subprocess.call(cmd, shell=True)
        print('Updated base_64_lang_helper.py')
    print("Finished")


def main():
    print("Run from the QualCoder-master folder")
    print("Choose option: --update --compile")
    print("--update updates language placeholders for ts and po files.")
    print("--compile compiles language files ts to qm files and po to mo files NOT TESTED YET")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        mode = sys.argv[1]
        if mode == "--update":
            update_translation_placeholders()
        elif mode == "--compile":
            recompile_translation()
        else:
            main()
    else:
        main()
