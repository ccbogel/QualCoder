"""
Using --update option: Updates translation placeholders in .po and Qt .ts files.
Using --compile option: Compiles .po to .mo files, and .ts to .qm files.
Using --lang option: Change only a specific language.
Using --status option: Check status of translation.
Using --zip option: Create zip for community languages.
Using --check option: Check translation files for errors.

Requires polib and PyQt5.

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

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
"""

from lxml import etree
import os
from pathlib import Path
import polib
import subprocess
import sys
import zipfile
from typing import Dict, Any, List, Optional, Tuple

# --- Constants ---
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
I18N_DIR = os.path.join(PROJECT_ROOT, "src", "qualcoder", "i18n")
OTHER_LANGS_DIR = os.path.join(PROJECT_ROOT, "other_languages")
GUI_DIR = os.path.join(PROJECT_ROOT, "src", "qualcoder", "GUI")
PROJECT_PRO_PATH = os.path.join(GUI_DIR, "project.pro")

# --- Utility Functions ---
def get_all_languages() -> List[str]:
    """Collect all 2-3 letter language codes from i18n and other_languages directories."""
    languages = []
    for directory in [I18N_DIR, OTHER_LANGS_DIR]:
        if not os.path.exists(directory):
            continue
        for root, _, files in os.walk(directory):
            for file in files:
                stem = Path(file).stem
                if len(stem) in (2, 3) and stem not in languages:
                    languages.append(stem)
    return languages

def filter_languages(lang: Optional[str], all_langs: List[str]) -> List[str]:
    """Return filtered list of languages based on `lang` argument."""
    return [lang] if lang and lang in all_langs else all_langs

def find_files(directory: str, extensions: Tuple[str, ...], lang: Optional[str] = None) -> List[str]:
    """Find files with given extensions in directory, optionally filtered by language."""
    files = []
    if not os.path.exists(directory):
        return files
    for root, _, filenames in os.walk(directory):
        for filename in filenames:
            if filename.endswith(extensions):
                if lang is None or Path(filename).stem == lang:
                    files.append(os.path.join(root, filename))
    return files

def run_subprocess(command: List[str], **kwargs) -> bool:
    """Run a subprocess command with error handling."""
    try:
        subprocess.run(command, check=True, **kwargs)
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error running command: {e}")
        return False

# --- Translation Placeholder Updates ---
def extract_pot_file(directory: str, pot_filename: str) -> None:
    """Extract strings from .py files into a .pot file using xgettext."""
    py_files = find_files(directory, (".py",))
    if not py_files:
        print("No Python files found to extract translatable strings from.")
        return

    run_subprocess(
        ["xgettext", "--language=Python", "--keyword=_", "--output", pot_filename] + py_files
    )
    print(f"Extracted POT file: {pot_filename}")

def update_po_files(directory: str, pot_filename: str, lang: Optional[str] = None) -> None:
    """Update .po files using msgmerge with the given .pot file."""
    for po_file in find_files(directory, (".po",), lang):
        run_subprocess(["msgmerge", "--update", po_file, pot_filename])
        print(f"Updated PO file: {po_file}")

        # Remove backup files created by msgmerge
        backup_file = po_file + "~"
        if os.path.exists(backup_file):
            try:
                os.remove(backup_file)
            except FileNotFoundError:
                pass

def delete_obsolete_ts(file_ts: str) -> None:
    """Remove obsolete entries from a .ts file."""
    parser = etree.XMLParser(remove_blank_text=True)
    tree = etree.parse(file_ts, parser)
    root = tree.getroot()
    for message in root.xpath('//message[translation[@type="obsolete"]]'):
        message.getparent().remove(message)
    tree.write(file_ts, encoding="utf-8", xml_declaration=True, pretty_print=True)

def build_pro_file(ts_files: List[str], ui_files: List[str]) -> None:
    """Create/overwrite project.pro for pylupdate5."""
    text = "SOURCES = \\\n" + " \\\n".join(ui_files) + "\n\n"
    text += "TRANSLATIONS = \\\n" + " \\\n".join(ts_files) + "\n\n"
    text += "CODECFORTR = ISO-8859-5\n"

    os.makedirs(os.path.dirname(PROJECT_PRO_PATH), exist_ok=True)
    with open(PROJECT_PRO_PATH, "w") as f:
        f.write(text)
    print("Created project.pro file")

def update_qt_ts_files(lang: Optional[str] = None) -> None:
    """Update Qt .ts files using pylupdate5."""
    # Find all .ts files
    ts_files = []
    for directory in [I18N_DIR, OTHER_LANGS_DIR]:
        if os.path.exists(directory):
            for file in os.listdir(directory):
                if file.endswith(".ts"):
                    stem = Path(file).stem
                    if len(stem) in (2, 3) and file not in ts_files:
                        ts_files.append(file)

    if lang:
        ts_files = [f for f in ts_files if Path(f).stem == lang]

    # Find UI files
    ui_files = []
    if os.path.exists(GUI_DIR):
        for ui_file in os.listdir(GUI_DIR):
            if ui_file.startswith("ui_") and ui_file.endswith(".py"):
                rel_path = os.path.relpath(
                    os.path.join(GUI_DIR, ui_file), GUI_DIR
                ).replace(os.path.sep, "/")
                ui_files.append(rel_path)
        ui_files.sort()

    # Prepare .pro file entries
    pro_ts_files = []
    for ts_file in ts_files:
        for directory in [I18N_DIR, OTHER_LANGS_DIR]:
            if os.path.exists(os.path.join(directory, ts_file)):
                rel_dir = os.path.relpath(directory, GUI_DIR).replace(os.path.sep, "/")
                pro_ts_files.append(f"{rel_dir}/{ts_file}")
                break

    build_pro_file(pro_ts_files, ui_files)
    run_subprocess(['pylupdate5', PROJECT_PRO_PATH], cwd=GUI_DIR)
    print("Updated ts translation files")

    # Clean obsolete entries
    for ts_file in ts_files:
        for directory in [I18N_DIR, OTHER_LANGS_DIR]:
            ts_path = os.path.join(directory, ts_file)
            if os.path.exists(ts_path):
                delete_obsolete_ts(ts_path)
                print(f"Cleaned obsolete entries in {ts_file}")

def update_translation_placeholders(language: Optional[str] = None) -> None:
    """Update .pot, .po, and .ts files for all or a specific language."""
    pot_filename = os.path.join(PROJECT_ROOT, "src", "qualcoder", "qualcoder.pot")
    extract_pot_file(os.path.join(PROJECT_ROOT, "src", "qualcoder"), pot_filename)
    update_po_files(I18N_DIR, pot_filename, language)
    update_po_files(OTHER_LANGS_DIR, pot_filename, language)
    update_qt_ts_files(language)

# --- New Language Placeholders ---
def create_new_language_placeholders(language: str) -> None:
    """Create empty .po and .ts files for a new language in other_languages."""
    print(f"Creating placeholder files for language: {language}")
    os.makedirs(OTHER_LANGS_DIR, exist_ok=True)

    new_po_file = os.path.join(OTHER_LANGS_DIR, f"{language}.po")
    with open(new_po_file, "w", encoding="utf-8") as f:
        f.write('msgid ""\nmsgstr ""\n')
    print(f"Created .po file: {new_po_file}")
    new_ts_file = os.path.join(OTHER_LANGS_DIR, f"{language}.ts")
    if not os.path.exists(GUI_DIR):
        print(f"Error: {GUI_DIR} does not exist.")
        return

    rel_ts_path = os.path.relpath(OTHER_LANGS_DIR, GUI_DIR).replace(os.path.sep, "/")
    new_ts_entry = f"{rel_ts_path}/{language}.ts"

    pro_content = ""
    if os.path.exists(PROJECT_PRO_PATH):
        with open(PROJECT_PRO_PATH, "r", encoding="utf-8") as f:
            pro_content = f.read()
    if new_ts_entry not in pro_content:
        lines = pro_content.split("\n")
        new_lines = []
        in_translations = False
        added = False

        for line in lines:
            if line.startswith("TRANSLATIONS"):
                in_translations = True
                new_lines.append(line)
                continue
            if in_translations:
                if line.strip() and not line.strip().startswith("#"):
                    if line.strip().endswith(".ts") and not added:
                        if not line.rstrip().endswith("\\"):
                            new_lines.append(line + " \\")
                        else:
                            new_lines.append(line)
                        new_lines.append(f"    {new_ts_entry}")
                        added = True
                        in_translations = False
                    else:
                        new_lines.append(line)
                else:
                    new_lines.append(line)
            else:
                new_lines.append(line)

        if not added:
            new_lines.extend(["", "TRANSLATIONS = \\", f"    {new_ts_entry}"])

        with open(PROJECT_PRO_PATH, "w", encoding="utf-8") as f:
            f.write("\n".join(new_lines))
        print(f"Updated project.pro with: {new_ts_entry}")

    if not run_subprocess(["pylupdate5", PROJECT_PRO_PATH], cwd=GUI_DIR):
        print(f"Failed to run pylupdate5 for {language}.ts")
        return
    print(f"Created/updated .ts file: {new_ts_file}")

    update_translation_placeholders(language)
    print("New placeholder files created.")

# --- Compilation ---
def recompile_translation(language: Optional[str] = None) -> None:
    """Compile .po to .mo and .ts to .qm files."""
    languages = filter_languages(language, get_all_languages())

    # GETTEXT: .po -> .mo
    for lang in languages:
        for directory in [I18N_DIR, OTHER_LANGS_DIR]:
            po_file = os.path.join(directory, f"{lang}.po")
            mo_file = os.path.join(directory, f"{lang}.mo")
            if os.path.exists(po_file):
                if not os.path.exists(mo_file) or (
                    os.path.getmtime(po_file) > os.path.getmtime(mo_file)
                ):
                    answer = input(f'Do you want to create/update "{mo_file}"? (y/n)')
                    if answer == "y":
                        polib.pofile(po_file).save_as_mofile(mo_file)
                        print(f"{mo_file} has been updated.")
                    else:
                        print(f'Skipping "{mo_file}".')

    # QT: .ts -> .qm
    for lang in languages:
        for directory in [I18N_DIR, OTHER_LANGS_DIR]:
            ts_file = os.path.join(directory, f"{lang}.ts")
            qm_file = os.path.join(directory, f"{lang}.qm")
            if os.path.exists(ts_file):
                if not os.path.exists(qm_file) or (
                    os.path.getmtime(ts_file) > os.path.getmtime(qm_file)
                ):
                    answer = input(f'Do you want to create/update "{qm_file}"? (y/n)')
                    if answer == "y":
                        run_subprocess(["lrelease", ts_file, "-qm", qm_file])
                        print(f"{qm_file} has been updated.")
                    else:
                        print(f'Skipping "{qm_file}".')

    # Cleanup .po~ files
    for directory in [I18N_DIR, OTHER_LANGS_DIR]:
        if os.path.exists(directory):
            for root, _, files in os.walk(directory):
                for file in files:
                    if file.endswith(".po~"):
                        try:
                            os.remove(os.path.join(root, file))
                            print(f"Deleted {file}")
                        except FileNotFoundError:
                            pass

# --- Translation Status Analysis ---
def generate_progress_bar(translated_percent: float, partial_percent: float) -> str:
    """Generate a 10-square progress bar."""
    total_squares = 10
    translated = min(total_squares, int(round(translated_percent / 10)))
    partial = min(total_squares - translated, int(round(partial_percent / 10)))
    untranslated = total_squares - translated - partial
    return "🟩" * translated + "🟨" * partial + "🟥" * untranslated

def analyze_translation_file(file_path: str, file_type: str) -> Dict[str, Any]:
    """Analyze a .po or .ts file and return translation statistics."""
    stats: Dict[str, Any] = {"error": None, "missing": False}
    if not os.path.exists(file_path):
        stats["missing"] = True
        return stats

    try:
        if file_type == "po":
            po = polib.pofile(file_path)
            total = len(po)
            stats.update({
                "total": total,
                "translated": sum(1 for entry in po if entry.translated()),
                "partial": sum(1 for entry in po if "fuzzy" in entry.flags),
                "untranslated": total - stats["translated"] - stats["partial"],
            })
        elif file_type == "ts":
            parser = etree.XMLParser(remove_blank_text=True)
            tree = etree.parse(file_path, parser)
            root = tree.getroot()
            messages = root.xpath("//message")
            stats.update({
                "total": len(messages),
                "translated": len(root.xpath(
                    '//message[translation and not(translation[@type="unfinished"]) and not(translation[@type="obsolete"])]'
                )),
                "partial": len(root.xpath('//message[translation[@type="obsolete"]]')),
                "untranslated": len(root.xpath(
                    '//message[not(translation) or translation[@type="unfinished"]]'
                )),
            })
    except Exception as e:
        stats["error"] = str(e)
    return stats

def analyze_translation_status(language: Optional[str] = None) -> str:
    """Generate a LANGUAGES_REPORT.md with translation status."""
    language_names = {
        "de": "Deutsch", "en": "English", "es": "Español", "fr": "Français",
        "it": "Italiano", "ja": "日本語", "pt": "Português", "ro": "Română",
        "sv": "Svenska", "zh": "中文", "eu": "Euskara", "eo": "Esperanto", "oc": "Occitan", "fa": "فارسی",
    }

    # Collect languages
    all_languages = {}
    for directory, status in [(I18N_DIR, "officially maintained"), (OTHER_LANGS_DIR, "community maintained")]:
        if not os.path.exists(directory):
            continue
        for root, _, files in os.walk(directory):
            for file in files:
                stem = Path(file).stem
                if len(stem) in (2, 3) and stem not in all_languages:
                    all_languages[stem] = {"source": directory, "status": status}

    # Filter by language
    if language and language in all_languages:
        all_languages = {language: all_languages[language]}

    # Generate report
    markdown_lines = [
        "# Translation Status Report\n",
        "",
        "Legend:",
        "- 🟩: Fully translated",
        "- 🟨: Partially translated (fuzzy/obsolete)",
        "- 🟥: Untranslated",
        "- ❌: File missing or error",
        "",
        "| Language | Progress | Status |",
        "|----------|----------|--------|",
    ]

    for lang, lang_info in all_languages.items():
        source_dir = lang_info["source"]
        gettext_stats = analyze_translation_file(
            os.path.join(source_dir, f"{lang}.po"), "po"
        )
        qt_stats = analyze_translation_file(
            os.path.join(source_dir, f"{lang}.ts"), "ts"
        )
        status = lang_info["status"]

        if lang_info["status"] == "community maintained":
            lang_display = f"[{language_names.get(lang, lang)}](https://github.com/ccbogel/QualCoder/raw/refs/heads/master/other_languages//{lang}.zip) ({lang})"
        else:
            lang_display = f"{language_names.get(lang, lang)} ({lang})"

        # Handle Gettext
        if gettext_stats.get("missing"):
            gettext_str = "❌ Missing"
            gettext_total = gettext_translated = gettext_partial = 0
        elif gettext_stats.get("error"):
            gettext_str = f"❌ Error: {gettext_stats['error']}"
            gettext_total = gettext_translated = gettext_partial = 0
        else:
            gettext_total = gettext_stats["total"]
            gettext_translated = gettext_stats["translated"]
            gettext_partial = gettext_stats["partial"]
            gettext_str = f"{gettext_translated}/{gettext_total} ({gettext_partial} fuzzy)"

        # Handle Qt
        if qt_stats.get("missing"):
            qt_str = "❌ Missing"
            qt_total = qt_translated = qt_partial = 0
        elif qt_stats.get("error"):
            qt_str = f"❌ Error: {qt_stats['error']}"
            qt_total = qt_translated = qt_partial = 0
        else:
            qt_total = qt_stats["total"]
            qt_translated = qt_stats["translated"]
            qt_partial = qt_stats["partial"]
            qt_str = f"{qt_translated}/{qt_total} ({qt_partial} obsolete)"

        # Combined stats
        total_entries = gettext_total + qt_total
        total_translated = gettext_translated + qt_translated
        total_partial = gettext_partial + qt_partial
        percent_complete = (total_translated / total_entries * 100) if total_entries > 0 else 0
        percent_partial = (total_partial / total_entries * 100) if total_entries > 0 else 0

        progress_bar = generate_progress_bar(percent_complete, percent_partial)
        markdown_lines.append(
            f"| {lang_display} | {progress_bar} {percent_complete:.1f}% ({total_translated}/{total_entries}) | {status} |"
        )

    markdown_lines.extend(["", "---", "> **Note:** Run `--status` to update this report."])

    # Write report
    output_path = os.path.join(PROJECT_ROOT, "LANGUAGES_REPORT.md")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(markdown_lines))
    print(f"Translation status report generated: {output_path}")
    return output_path

# --- Translation Checks ---
def check_translations(language: Optional[str] = None) -> str:
    """Check .po and .ts files for errors and generate a report."""
    print("\n--- Starting translation check ---")
    issues = []
    languages_to_check = filter_languages(language, get_all_languages())

    # Check .po files
    for directory in [I18N_DIR, OTHER_LANGS_DIR]:
        if not os.path.exists(directory):
            continue
        for po_file in find_files(directory, (".po",)):
            lang = Path(po_file).stem
            if lang not in languages_to_check:
                continue
            try:
                po = polib.pofile(po_file)
                for entry in po:
                    if not entry.translated():
                        issues.append(f"[PO] {lang}: Untranslated entry -> '{entry.msgid}'")
                    if entry.msgstr == "":
                        issues.append(f"[PO] {lang}: Empty translation for -> '{entry.msgid}'")
                    if "fuzzy" in entry.flags:
                        issues.append(f"[PO] {lang}: Fuzzy entry -> '{entry.msgid}'")
            except Exception as e:
                issues.append(f"[PO] {lang}: Error reading file -> {str(e)}")

    # Check .ts files
    for directory in [I18N_DIR, OTHER_LANGS_DIR]:
        if not os.path.exists(directory):
            continue
        for ts_file in find_files(directory, (".ts",)):
            lang = Path(ts_file).stem
            if lang not in languages_to_check:
                continue
            try:
                parser = etree.XMLParser(remove_blank_text=True)
                tree = etree.parse(ts_file, parser)
                root = tree.getroot()
                for message in root.xpath("//message"):
                    source = message.find("source")
                    translation = message.find("translation")
                    if source is not None and translation is None:
                        issues.append(f"[TS] {lang}: Missing translation for -> '{source.text}'")
                    elif translation is not None:
                        if not translation.text or not translation.text.strip():
                            issues.append(f"[TS] {lang}: Empty translation for -> '{source.text}'")
                        if translation.get("type") == "unfinished":
                            issues.append(f"[TS] {lang}: Unfinished translation for -> '{source.text}'")
            except Exception as e:
                issues.append(f"[TS] {lang}: Error reading file -> {str(e)}")

    if not issues:
        print("✅ No issues detected in translation files.")
        return ""

    print("\n--- Detected Issues ---")
    for issue in issues:
        print(f"❌ {issue}")

    report_path = os.path.join(PROJECT_ROOT, "TRANSLATION_CHECK_REPORT.txt")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(issues))
    print(f"\n📄 Report saved to: {report_path}")
    return report_path

# --- Zip Creation ---
def zip_language_files(language: Optional[str] = None) -> None:
    """Zip .mo, .qm, and .txt files for languages in other_languages."""
    if not os.path.exists(OTHER_LANGS_DIR):
        print(f"Directory {OTHER_LANGS_DIR} does not exist.")
        return

    languages = []
    for file in os.listdir(OTHER_LANGS_DIR):
        stem = Path(file).stem
        if len(stem) in (2, 3) and stem not in languages:
            languages.append(stem)

    if language:
        if language in languages:
            languages = [language]
        else:
            print(f"Language {language} not found in {OTHER_LANGS_DIR}")
            return

    for lang in languages:
        files_to_zip = [
            f for f in os.listdir(OTHER_LANGS_DIR)
            if f.startswith(f"{lang}.") and f.endswith((".mo", ".qm", ".txt"))
        ]
        if not files_to_zip:
            print(f"No files found for language {lang}")
            continue

        zip_path = os.path.join(OTHER_LANGS_DIR, f"{lang}.zip")
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
            for file in files_to_zip:
                file_path = os.path.join(OTHER_LANGS_DIR, file)
                zipf.write(file_path, file)
                print(f"Added {file} to {zip_path}")
        print(f"Created zip file: {zip_path}")

# --- CLI and Main ---
def print_usage() -> None:
    """Print script usage instructions."""
    print("Run from the QualCoder-master folder")
    print("Choose option: --update --compile --zip --status --check --create")
    print("--update: Update language placeholders for .po and .ts files (i18n and other_languages).")
    print("--compile: Compile .po to .mo and .ts to .qm files (i18n and other_languages).")
    print("--zip: Zip .mo, .qm, and .txt files in other_languages directory.")
    print("--status: Generate LANGUAGES_REPORT.md with translation status.")
    print("--check: Check translation files for errors.")
    print("--create: Create placeholder files for a new language (use 2-3 letter ISO639 codes).")
    print("--lang LANG: Specify a language code (e.g., 'fr', 'es').")
    print("Examples:")
    print("  python script.py --update --lang fr")
    print("  python script.py --check --lang ro")

def main() -> None:
    if len(sys.argv) < 2:
        print_usage()
        return

    lang = None
    if "--lang" in sys.argv:
        lang_index = sys.argv.index("--lang") + 1
        if lang_index < len(sys.argv):
            lang = sys.argv[lang_index]

    if "--create" in sys.argv:
        if lang:
            create_new_language_placeholders(lang)
        else:
            print("Error: --create requires --lang LANG")
    elif "--update" in sys.argv:
        update_translation_placeholders(lang)
    elif "--compile" in sys.argv:
        recompile_translation(lang)
        zip_language_files(lang)  # Auto-zip after compile
    elif "--status" in sys.argv:
        analyze_translation_status(lang)
    elif "--zip" in sys.argv:
        zip_language_files(lang)
    elif "--check" in sys.argv:
        check_translations(lang)
    else:
        print_usage()

if __name__ == "__main__":
    main()
