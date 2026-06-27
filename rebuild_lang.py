"""
Using --update option
This script updates translation placeholders in .po and Qt .ts files.
Using --compile option
This script compiles .po to .mo files, and .ts to .qm files.
Using --lang option
Change only a specific language
Using --status option
Check status of translation
Using --zip option
Create zip for community languages

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
https://qualcoder.org/
https://
"""

from lxml import etree
import os
from pathlib import Path
import polib
import subprocess
import sys
import zipfile
from typing import Dict, Any, List

project_root = os.path.dirname(os.path.abspath(__file__))
i18n_directory = os.path.join(project_root, "src", "qualcoder", "i18n")
other_languages_directory = os.path.join(project_root, "other_languages")

# Collect languages from both i18n and other_languages directories
languages = []
for directory in [i18n_directory, other_languages_directory]:
    if os.path.exists(directory):
        for root, dirs, files in os.walk(directory):
            for file in files:
                stem = Path(file).stem
                if len(stem) in (2, 3) and stem not in languages:
                    languages.append(stem)

def extract_pot_file(directory: str, pot_filename: str):
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

def update_po_files(directory: str, pot_filename: str, lang_: str | None = None):
    """List all .po files within the specified directory and other_languages directory.
    called by: update_translation_placeholders"""

    directories_to_scan = [directory]
    if os.path.exists(other_languages_directory):
        directories_to_scan.append(other_languages_directory)

    for scan_dir in directories_to_scan:
        for root, dirs, files in os.walk(scan_dir):
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
                    if file.endswith('.po~'):
                        try:
                            os.remove(os.path.join(root, file))
                        except FileNotFoundError:
                            pass

def delete_obsolete_ts(file_ts):
    parser = etree.XMLParser(remove_blank_text=True)
    tree = etree.parse(file_ts, parser)
    root = tree.getroot()
    obsolete_messages = root.xpath('//message[translation[@type="obsolete"]]')
    for message in obsolete_messages:
        message.getparent().remove(message)
    tree.write(file_ts, encoding='utf-8', xml_declaration=True, pretty_print=True)

def update_qt_ts_files(lang_: str | None = None):
    """Requires pylupdate5
    pip install pyqt5-tools
    Run from QualCoder-master folder
    Warning: pylupdate6 overrides, but does not update, existing ts files.
    Called by: update_translation_placeholders
    Args:
        lang_: String es, fr, etc
    """

    # Collect all .ts files from i18n and other_languages
    translation_files = []
    for directory in [i18n_directory, other_languages_directory]:
        if os.path.exists(directory):
            for file in os.listdir(directory):
                if file.endswith('.ts'):
                    stem = Path(file).stem
                    if len(stem) in (2, 3) and f"{stem}.ts" not in translation_files:
                        translation_files.append(f"{stem}.ts")

    if lang_ is not None:
        translation_files = [f for f in translation_files if f.startswith(f"{lang_}")]
    script_path = os.path.dirname(os.path.realpath(__file__))
    gui_directory = os.path.join(script_path, "src", "qualcoder", "GUI")

    # Build a .pro file, which can then be used by pylupdate5 to create ts files
    def rel_for_pro(path):
        rel_path = os.path.relpath(path, gui_directory)
        return rel_path.replace(os.path.sep, "/")

    ui_files = []
    for ui_file in os.listdir(gui_directory):
        if ui_file.startswith("ui_") and ui_file.endswith(".py"):
            ui_files.append(rel_for_pro(os.path.join(gui_directory, ui_file)))
    ui_files.sort()

    ts_files = []
    for translation_file in translation_files:
        # Determine the directory for this ts file
        for directory in [i18n_directory, other_languages_directory]:
            if os.path.exists(os.path.join(directory, translation_file)):
                rel_path = os.path.relpath(directory, gui_directory)
                ts_files.append(rel_path.replace(os.path.sep, "/") + "/" + translation_file)
                break

    text = "SOURCES = \\\n"
    text += " \\\n".join(ui_files)
    text += "\n\nTRANSLATIONS = \\\n"
    text += " \\\n".join(ts_files)
    text += "\n\nCODECFORTR = ISO-8859-5\n"

    pro_file_path = os.path.join(gui_directory, "project.pro")
    with open(pro_file_path, 'w') as pro_file:
        pro_file.write(text)
    print("Created project.pro file")
    # Compile ts files
    subprocess.call(f'pylupdate5 "{pro_file_path}"', shell=True)
    print("Updated ts translation files")

    # Delete old .ts files
    for ts_file in translation_files:
        for directory in [i18n_directory, other_languages_directory]:
            ts_path = os.path.join(directory, ts_file)
            if os.path.exists(ts_path):
                delete_obsolete_ts(ts_path)
                print(f"Cleaned obsolete entries in {ts_file}")

def update_translation_placeholders(language: str | None = None):
    """ Update po files, update GUI ts files """

    directory = os.path.join('src', 'qualcoder')
    pot_filename = os.path.join(directory, 'qualcoder.pot')
    extract_pot_file(directory, pot_filename)
    update_po_files(i18n_directory, pot_filename, language)
    update_qt_ts_files(language)

def create_new_language_placeholders(language: str):
    """Create a new set of .po and .ts files for a new language in other_languages directory."""
 
    print(f"Creating placeholder files for language: {language}")

    # Create .po file in other_languages
    new_po_file = os.path.join(other_languages_directory, f'{language}.po')
    with open(new_po_file, 'w', encoding='utf-8') as po_file:
        po_file.write("")
    print(f"Created empty .po file: {new_po_file}")

    # Create .ts file using the existing project.pro
    new_ts_file = os.path.join(other_languages_directory, f'{language}.ts')
    gui_directory = os.path.join(project_root, "src", "qualcoder", "GUI")
    project_pro = os.path.join(gui_directory, "project.pro")

    # Check if project.pro exists
    if not os.path.exists(project_pro):
        print(f"Error: {project_pro} does not exist. Run --update first to create it.")
        return

    # Read the existing project.pro
    with open(project_pro, 'r', encoding='utf-8') as f:
        pro_content = f.read()

    # Add the new .ts file to TRANSLATIONS
    rel_ts_path = os.path.relpath(other_languages_directory, gui_directory)
    new_ts_entry = f"{rel_ts_path}/{language}.ts"

    # Check if the new .ts file is already in the project.pro
    if new_ts_entry in pro_content:
        print(f"Language {language} already in project.pro")
    else:
        # Find the TRANSLATIONS section and add the new entry
        lines = pro_content.split('\n')
        new_lines = []
        in_translations = False
        translations_added = False

        for line in lines:
            new_lines.append(line)
            if line.startswith("TRANSLATIONS"):
                in_translations = True
                continue
            if in_translations and line.strip() and not line.strip().startswith('#'):
                if line.strip().endswith('.ts') and not translations_added:
                    # Add the new entry after the last .ts file
                    new_lines.append(new_ts_entry)
                    translations_added = True
                    in_translations = False

        # If we didn't find a TRANSLATIONS section or any .ts files, add it at the end
        if not translations_added:
            new_lines.append("\nTRANSLATIONS = \\")
            new_lines.append(new_ts_entry)

        # Write the updated project.pro
        with open(project_pro, 'w', encoding='utf-8') as f:
            f.write('\n'.join(new_lines))

    # Run pylupdate5 to create/update the .ts file
    try:
        result = subprocess.run(
            ['pylupdate5', project_pro],
            check=True,
            cwd=gui_directory,
            capture_output=True,
            text=True
        )
        print(f"Created/updated .ts file: {new_ts_file}")
        if result.stdout:
            print(f"pylupdate5 output: {result.stdout}")
    except subprocess.CalledProcessError as e:
        print(f"Error creating .ts file: {e}")
        if e.stdout:
            print(f"pylupdate5 stdout: {e.stdout}")
        if e.stderr:
            print(f"pylupdate5 stderr: {e.stderr}")

    # Update the language placeholders
    update_translation_placeholders(language)
    print("New placeholder files created.")

def recompile_translation(language: str | None = None):
    """Make sure lrelease.exe is in path.
    e.g. C:/Users/cc/AppData/Local/Python/pythoncore-3.14-64/Scripts
    This is a user path environment variable"""

    language_list = languages
    if language in language_list:
        language_list = [language]

    # GETTEXT TRANSLATION
    # .po-files and .mo-files
    for lang_ in language_list:
        # Check in both i18n and other_languages directories
        for directory in [i18n_directory, other_languages_directory]:
            po_file = os.path.join(directory, f'{lang_}.po')
            mo_file = os.path.join(directory, f'{lang_}.mo')

            if os.path.exists(po_file):
                # Check if po-file has been updated and is newer than the corresponding mo-file
                if (not os.path.exists(mo_file)) or (os.path.getmtime(po_file) > os.path.getmtime(mo_file)):
                    answer = input(f'Do you want to create/update "{mo_file}"? (y/n)')
                    if answer == 'y':
                        po = polib.pofile(po_file)
                        po.save_as_mofile(mo_file)
                        print(f"{mo_file} has been updated.")
                    else:
                        print(f'Skipping "{mo_file}".')

    # Qt TRANSLATIONS
    # .ts-files and .qm-files
    for lang_ in language_list:
        # Check in both i18n and other_languages directories
        for directory in [i18n_directory, other_languages_directory]:
            ts_file = os.path.join(directory, f'{lang_}.ts')
            qm_file = os.path.join(directory, f'{lang_}.qm')

            if os.path.exists(ts_file):
                # Check if ts-file has been updated and is newer than the corresponding qm-file
                if not os.path.exists(qm_file) or (os.path.getmtime(ts_file) > os.path.getmtime(qm_file)):
                    answer = input(f'Do you want to create/update "{qm_file}"? (y/n)')
                    if answer == 'y':
                        subprocess.run(['lrelease', ts_file, "-qm", qm_file], check=True)
                        print(f"{qm_file} has been updated.")
                    else:
                        print(f'Skipping "{qm_file}".')
    print("Finished")

def generate_progress_bar(translated_percent: float, partial_percent: float) -> str:
    """Generate a 10-square progress bar using 🟩 (translated), 🟨 (partial), 🟥 (untranslated)."""
    total_squares = 10
    translated = min(total_squares, int(round(translated_percent / 10)))
    partial = min(total_squares - translated, int(round(partial_percent / 10)))
    untranslated = total_squares - translated - partial
    return "🟩" * translated + "🟨" * partial + "🟥" * untranslated

def analyze_translation_file(file_path: str, file_type: str) -> Dict[str, Any]:
    """Analyze a single translation file (.po or .ts) and return its statistics."""
    stats: Dict[str, Any] = {"error": None, "missing": False}

    if not os.path.exists(file_path):
        stats["missing"] = True
        return stats

    try:
        if file_type == "po":
            po = polib.pofile(file_path)
            total = len(po)
            translated = sum(1 for entry in po if entry.translated())
            fuzzy = sum(1 for entry in po if "fuzzy" in entry.flags)
            stats.update({
                "total": total,
                "translated": translated,
                "partial": fuzzy,
                "untranslated": total - translated - fuzzy,
            })

        elif file_type == "ts":
            parser = etree.XMLParser(remove_blank_text=True)
            tree = etree.parse(file_path, parser)
            root = tree.getroot()
            messages = root.xpath("//message")
            total = len(messages)
            translated = len(root.xpath(
                '//message[translation and not(translation[@type="unfinished"]) and not(translation[@type="obsolete"])]'
            ))
            obsolete = len(root.xpath('//message[translation[@type="obsolete"]]'))
            untranslated = len(root.xpath('//message[not(translation) or translation[@type="unfinished"]]'))
            stats.update({
                "total": total,
                "translated": translated,
                "partial": obsolete,
                "untranslated": untranslated,
            })
    except Exception as e:
        stats["error"] = str(e)
    return stats

def analyze_translation_status(language: str | None = None) -> str:
    """Analyze translation status for .po and .ts files and generate a LANGUAGES.md report.
    Includes languages from both i18n (officially maintained) and other_languages (community maintained)."""

    # Mapping language code with language name
    language_names = {
        "de": "Deutsch",
        "en": "English",
        "es": "Español",
        "fr": "Français",
        "it": "Italiano",
        "ja": "日本語",
        "pt": "Português",
        "ro": "Română",
        "sv": "Svenska",
        "zh": "中文",
        "eu": "Euskara",
        "eo": "Esperanto",
        "fa": "فارسی"
        # Add new language here
    }

    # Collect all languages from i18n and other_languages
    all_languages = {}

    # Add languages from i18n directory (officially maintained)
    for root, dirs, files in os.walk(i18n_directory):
        for file in files:
            stem = Path(file).stem
            if len(stem) in (2, 3) and stem not in all_languages:
                all_languages[stem] = {"source": "i18n", "status": "officially maintained"}

    # Add languages from other_languages directory (community maintained)
    if os.path.exists(other_languages_directory):
        for file in os.listdir(other_languages_directory):
            stem = Path(file).stem
            if len(stem) in (2, 3) and stem not in all_languages:
                all_languages[stem] = {"source": "other_languages", "status": "community maintained"}

    # Filter by language if specified
    if language:
        if language in all_languages:
            all_languages = {language: all_languages[language]}
        else:
            print(f"Language {language} not found.")
            return ""

    # Collect data for all languages
    report_data: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for lang, lang_info in all_languages.items():
        source_dir = i18n_directory if lang_info["source"] == "i18n" else other_languages_directory
        report_data[lang] = {
            "gettext": analyze_translation_file(
                os.path.join(source_dir, f"{lang}.po"),
                "po",
            ),
            "qt": analyze_translation_file(
                os.path.join(source_dir, f"{lang}.ts"),
                "ts",
            ),
            "status": lang_info["status"],
        }

    # Generate markdown lines
    markdown_lines: List[str] = [
        "# Translation Status Report\n",
        "",
        "Legend",
        "- 🟩: Fully translated",
        "- 🟨: Partially translated (fuzzy/obsolete)",
        "- 🟥: Untranslated",
        "- ❌: File missing or error",
        "",
        "| Language | Progress | Status |",
        "|----------|----------|--------|",
    ]

    for lang, lang_data in report_data.items():
        gettext_stats = lang_data["gettext"]
        qt_stats = lang_data["qt"]
        status = lang_data["status"]

        # Get the full language name or use the code if not found
        lang_display_name = language_names.get(lang, lang)
        lang_display = f"{lang_display_name} ({lang})"

        # Handle Gettext data
        if gettext_stats.get("missing"):
            gettext_total = 0
            gettext_translated = 0
            gettext_partial = 0
            gettext_str = "❌ Missing"
        elif gettext_stats.get("error"):
            gettext_total = 0
            gettext_translated = 0
            gettext_partial = 0
            gettext_str = f"❌ Error: {gettext_stats['error']}"
        else:
            gettext_total = gettext_stats["total"]
            gettext_translated = gettext_stats["translated"]
            gettext_partial = gettext_stats["partial"]
            gettext_str = f"{gettext_translated}/{gettext_total} ({gettext_partial} fuzzy)"

        # Handle Qt data
        if qt_stats.get("missing"):
            qt_total = 0
            qt_translated = 0
            qt_partial = 0
            qt_str = "❌ Missing"
        elif qt_stats.get("error"):
            qt_total = 0
            qt_translated = 0
            qt_partial = 0
            qt_str = f"❌ Error: {qt_stats['error']}"
        else:
            qt_total = qt_stats["total"]
            qt_translated = qt_stats["translated"]
            qt_partial = qt_stats["partial"]
            qt_str = f"{qt_translated}/{qt_total} ({qt_partial} obsolete)"

        # Combined totals
        total_entries = gettext_total + qt_total
        total_translated = gettext_translated + qt_translated
        total_partial = gettext_partial + qt_partial
        percent_complete = (total_translated / total_entries * 100) if total_entries > 0 else 0
        percent_partial = (total_partial / total_entries * 100) if total_entries > 0 else 0

        # Generate combined progress bar
        progress_bar = generate_progress_bar(percent_complete, percent_partial)
        markdown_lines.append(
            f"| {lang_display} | {progress_bar} {percent_complete:.1f}% ({total_translated} / {total_entries}) | {status} |"
        )
    markdown_lines.extend(
        ["", "---", "> **Note:** This report is automatically generated. Run `--status` to update it."]
    )

    # Write to LANGUAGES.md
    output_path = os.path.join(project_root, "LANGUAGES_REPORT.md")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(markdown_lines))
    print(f"Translation status report generated: {output_path}")
    return output_path

def zip_language_files(language: str | None = None):
    """ Zip .mo, .qm and .txt files for each language in other_languages directory.

    Args:
        language: Optional language code to zip only that language. If None, zips all languages.
    """
    if not os.path.exists(other_languages_directory):
        print(f"Directory {other_languages_directory} does not exist.")
        return

    # Get all language codes from files in other_languages directory
    other_languages = []
    for file in os.listdir(other_languages_directory):
        stem = Path(file).stem
        if len(stem) in (2, 3) and stem not in other_languages:
            other_languages.append(stem)

    if language is not None:
        if language in other_languages:
            other_languages = [language]
        else:
            print(f"Language {language} not found in {other_languages_directory}")
            return

    for lang in other_languages:
        # Find all files with this language code
        files_to_zip = []
        for file in os.listdir(other_languages_directory):
            if file.startswith(f"{lang}.") and file.endswith(('.mo', '.qm', '.txt')):
                files_to_zip.append(file)

        if not files_to_zip:
            print(f"No files found for language {lang}")
            continue

        # Create zip file
        zip_filename = os.path.join(other_languages_directory, f"{lang}.zip")
        with zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for file in files_to_zip:
                file_path = os.path.join(other_languages_directory, file)
                zipf.write(file_path, file)
                print(f"Added {file} to {zip_filename}")

        print(f"Created zip file: {zip_filename}")

def main():
    print("Run from the QualCoder-master folder")
    print("Choose option: --update --compile --zip --status")
    print("--update updates language placeholders for ts and po files (i18n and other_languages).")
    print("--compile compiles language files ts to qm files and po to mo files (i18n and other_languages)")
    print("--zip zips .mo, .qm and .txt files in other_languages directory")
    print("--lang LANG: specify a language code (e.g., 'fr', 'es') to update/compile/zip only that language.")
    print("e.g. --update --lang fr")
    print("e.g. --zip --lang ro")
    print("--status makes LANGUAGES_REPORT.md file which shows translation status of files (i18n and other_languages).")
    print("--create Creates placeholder files po (NOT YET) ts for a new language. use 2 or 3 letter ISO639 codes.")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        mode = sys.argv[1]
        lang = None
        if "--lang" in sys.argv:
            lang_index = sys.argv.index("--lang") + 1
            if lang_index < len(sys.argv):
                lang = sys.argv[lang_index]
        if "--create" in sys.argv:
            create_new_language_placeholders(lang)
        elif mode == "--update":
            update_translation_placeholders(lang)
        elif mode == "--compile":
            recompile_translation(lang)
        elif mode == "--status":
            analyze_translation_status(lang)
        elif mode == "--zip":
            zip_language_files(lang)
        else:
            main()
    else:
        main()
