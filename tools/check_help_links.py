#!/usr/bin/env python3
"""Check the context help links against a checkout of the documentation site.

Every page and anchor in src/qualcoder/context_help.py must exist in the English
docs. In a translation a missing page is fine (the app falls back to English),
but a page without the anchor opens at the top instead of the section.

Usage:
    python tools/check_help_links.py path/to/qualcoder-org.github.io
    python tools/check_help_links.py path/to/qualcoder-org.github.io es fr
Exit code is 1 if English is missing a page or an anchor, or a translated page
is missing an anchor.
"""

import re
import runpy
import sys
from pathlib import Path

CONTEXT_HELP = Path(__file__).resolve().parent.parent / "src" / "qualcoder" / "context_help.py"
ANCHOR_RE = re.compile(r"\{[^}]*#([\w-]+)[^}]*}\s*$", re.MULTILINE)


def help_links():
    """(name, page, anchor) for every link in context_help.py."""

    data = runpy.run_path(str(CONTEXT_HELP))
    links = [(name, *link.partition("#")[::2]) for name, link in data["MODULE_HELP_PAGES"].items()]
    for name, tabs in data["INNER_TAB_HELP_PAGES"].items():
        for index, link in tabs.items():
            links.append((f"{name} tab {index}", *link.partition("#")[::2]))
    return links


def check_language(doc_dir, lang, links):
    """Lists of missing pages and missing anchors for one language."""

    missing_pages, missing_anchors = [], []
    for name, page, anchor in links:
        md_file = doc_dir / lang / (page.rstrip("/") + ".md")
        if not md_file.exists():
            missing_pages.append(f"{name}: {page}")
            continue
        if anchor and anchor not in ANCHOR_RE.findall(md_file.read_text(encoding="utf-8")):
            missing_anchors.append(f"{name}: {page}#{anchor}")
    return missing_pages, missing_anchors


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    doc_dir = Path(argv[1]) / "docs" / "doc"
    langs = argv[2:] or sorted(d.name for d in doc_dir.iterdir() if d.is_dir())
    if "en" not in langs:
        langs.insert(0, "en")
    links = help_links()
    failed = False
    for lang in langs:
        missing_pages, missing_anchors = check_language(doc_dir, lang, links)
        if lang == "en" and missing_pages:
            failed = True
            print("error: en, missing pages:")
            print("\n".join(f"  {item}" for item in missing_pages))
        elif missing_pages:
            print(f"info: {lang}, {len(missing_pages)} links go to pages not translated yet, English is shown instead")
        if missing_anchors:
            failed = True
            print(f"error: {lang}, pages without the anchor (open at the top):")
            print("\n".join(f"  {item}" for item in missing_anchors))
        if not missing_pages and not missing_anchors:
            print(f"ok: {lang}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
