"""
Using --update option
This script updates translation placeholders in .po and Qt .ts files.
Using --compile option
This script compiles .po to .mo files, and .ts to .qm files.
Using --lang option
Change only a specific language

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
https://qualcoder-org.github.io/
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


def update_po_files(directory, pot_filename, lang_=None):
    """ List all .po files within the specified directory.
    called by: update_translation_placeholders """
    for root, dirs, files in os.walk(directory):
        for file in files:
            if lang_ is None or file.startswith(lang_):
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


def update_qt_ts_files(lang_=None):
    """ Requires pyludate5
    pip install pyqt5-tools
    Run from QualCoder-master folder
    Warning: pylupdate6 overrides ,but does not update, existing ts files.
    CAlled by: update_translation_placeholders
    """

    translation_files = ["app_de.ts", "app_es.ts", "app_fr.ts", "app_it.ts", "app_ja.ts",
                         "app_pt.ts", "app_sv.ts", "app_zh.ts"]
    if lang_ is not None:
        translation_files = [f for f in translation_files if f.startswith(f"app_{lang_}")]

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


def update_translation_placeholders(language=None):
    """ Update po files, update GUI ts files """

    directory = os.path.join('src', 'qualcoder')
    pot_filename = os.path.join(directory, 'qualcoder.pot')
    extract_pot_file(directory, pot_filename)
    update_po_files(directory, pot_filename, language)
    update_qt_ts_files(language)


def recompile_translation(language=None):
    """ Make sure lrelease.exe is in path.
     Colin - I put mine in C:/Users/cc/AppData/Local/Python/pythoncore-3.14-64/Scripts
     This is a user path environment variable """

    project_root = os.path.dirname(os.path.abspath(__file__))

    language_list = ['de', 'en', 'es', 'fr', 'it', 'ja', 'pt', 'sv', 'zh']
    if language in language_list:
        language_list = [language]

    # GETTEXT TRANSLATION
    # .po-files
    po_dir = os.path.join(project_root, "src", "qualcoder")
    po_files = [os.path.join(po_dir, f'{lang_}.po') for lang_ in language_list]

    # .mo-files
    mo_basedir = os.path.join(project_root, "src", "qualcoder", "locale")
    mo_files = [os.path.join(mo_basedir, lang_, 'LC_MESSAGES', f'{lang_}.mo') for lang_ in language_list]

    for po_file, mo_file in zip(po_files, mo_files):
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
    ts_files = [os.path.join(ts_dir, f'app_{lang_}.ts') for lang_ in language_list]

    # .qm-files
    qm_basedir = os.path.join(project_root, "src", "qualcoder", "locale")
    qm_files = [os.path.join(qm_basedir, lang_, f'app_{lang_}.qm') for lang_ in language_list]

    for ts_file, qm_file in zip(ts_files, qm_files):
        if os.path.exists(ts_file):
            # Check if ts-file has been updated and is newer than the corresponding qm-file
            if not os.path.exists(qm_file) or (os.path.getmtime(ts_file) > os.path.getmtime(qm_file)):
                answer = input(f'Do you want to create/update "{qm_file}"? (y/n)')
                if answer == 'y':
                    subprocess.run(['lrelease', ts_file, "-qm", qm_file], check=True)
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
    print("--compile compiles language files ts to qm files and po to mo files")
    print("--lang LANG: specify a language code (e.g., 'fr', 'es') to update/compile only that language.")
    print("e.g. --update --lang fr")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        mode = sys.argv[1]
        lang = None
        if "--lang" in sys.argv:
            lang_index = sys.argv.index("--lang") + 1
            if lang_index < len(sys.argv):
                lang = sys.argv[lang_index]
        if mode == "--update":
            update_translation_placeholders(lang)
        elif mode == "--compile":
            recompile_translation(lang)
        else:
            main()
    else:
        main()
