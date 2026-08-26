#!/usr/bin/env python3
"""Strip Qt rich text markup from .ui string properties for screen reader accessibility.

Only the text inside <string> nodes is rewritten, byte for byte everywhere else.
Placeholder conventions like <select available model> are left untouched because
they are not markup. Run with --check to report without writing.
"""

import argparse
import csv
import html
import os
import re
import sys
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape

# Tag names treated as markup; anything else inside angle brackets is literal text
TAGS = (r"!DOCTYPE|html|head|body|meta|style|p|div|span|b|strong|i|em|u|s|a|br|hr|"
        r"font|center|nobr|pre|code|sub|sup|img|ul|ol|li|table|tbody|thead|tr|td|th|h[1-6]")
MARKUP_RE = re.compile(r"</?(?:" + TAGS + r")(?:\s[^>]*)?/?>", re.I)
STRING_RE = re.compile(r"(<string(?:\s[^>]*)?>)([^<]*)(</string>)")

# QLabel headings that get their weight from <b> in the text, with a font block just above
BOLD_LABEL_RE = re.compile(
    r"(<property name=\"font\">\s*<font>\s*)<weight>50</weight>(\s*)<bold>false</bold>"
    r"(\s*</font>\s*</property>\s*<property name=\"text\">\s*<string(?:\s[^>]*)?>)"
    r"&lt;b&gt;(.*?)&lt;/b&gt;(</string>)",
    re.S)

# QTextEdit/QTextBrowser initial content stored as a full HTML document
HTML_PROP_RE = re.compile(
    r"<property name=\"html\">(\s*<string(?:\s[^>]*)?>)([^<]*)(</string>\s*)</property>")

# Markup that renders no text at all, e.g. an empty paragraph left by Designer
EMPTY_TIP_RE = re.compile(
    r"[ \t]*<property name=\"(?:toolTip|whatsThis|statusTip)\">\s*"
    r"<string(?:\s[^>]*)?>([^<]*)</string>\s*</property>\n?")


def to_plain(markup):
    """Return the readable text of a Qt rich text fragment."""
    text = re.sub(r"<!DOCTYPE[^>]*>", "", markup, flags=re.I)
    text = re.sub(r"<head\b.*?</head>", "", text, flags=re.I | re.S)
    text = re.sub(r"<style\b.*?</style>", "", text, flags=re.I | re.S)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"<li\b[^>]*>", "- ", text, flags=re.I)
    text = re.sub(r"</(?:p|div|li|tr|h[1-6])>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    lines = [re.sub(r"[ \t\u00a0]+", " ", ln).strip() for ln in text.split("\n")]
    out = []
    for line in lines:
        if not line and (not out or not out[-1]):
            continue
        out.append(line)
    return "\n".join(out).strip()


def process(source):
    """Return (new_source, changes) for one .ui file."""
    changes = []

    def bold_label(match):
        plain = to_plain(html.unescape(match.group(4)))
        changes.append(("text (bold heading)", "<b>" + match.group(4) + "</b>", plain))
        return (match.group(1) + "<weight>75</weight>" + match.group(2) + "<bold>true</bold>"
                + match.group(3) + escape(plain) + match.group(5))

    def html_prop(match):
        plain = to_plain(html.unescape(match.group(2)))
        changes.append(("html -> plainText", html.unescape(match.group(2)), plain))
        return ("<property name=\"plainText\">" + match.group(1) + escape(plain)
                + match.group(3) + "</property>")

    def string_node(match):
        raw = html.unescape(match.group(2))
        if not MARKUP_RE.search(raw):
            return match.group(0)
        plain = to_plain(raw)
        changes.append(("string", raw, plain))
        return match.group(1) + escape(plain) + match.group(3)

    def empty_tip(match):
        raw = html.unescape(match.group(1))
        if not MARKUP_RE.search(raw) or to_plain(raw):
            return match.group(0)
        changes.append(("empty tooltip removed", raw, ""))
        return ""

    result = BOLD_LABEL_RE.sub(bold_label, source)
    result = EMPTY_TIP_RE.sub(empty_tip, result)
    result = HTML_PROP_RE.sub(html_prop, result)
    result = STRING_RE.sub(string_node, result)
    return result, changes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", nargs="?", default=".")
    parser.add_argument("-o", "--output", help="write cleaned files here (default: in place)")
    parser.add_argument("--check", action="store_true", help="report only, write nothing")
    parser.add_argument("--report", default="ui_html_report.csv")
    args = parser.parse_args()

    rows = [("file", "kind", "before", "after")]
    total, touched = 0, 0
    for name in sorted(os.listdir(args.folder)):
        if not name.endswith(".ui"):
            continue
        total += 1
        path = os.path.join(args.folder, name)
        with open(path, encoding="utf-8", newline="") as handle:
            source = handle.read()
        result, changes = process(source)
        if not changes:
            continue
        try:
            ET.fromstring(result)
        except ET.ParseError as err:
            print("[ERROR] %s not written, XML would be invalid: %s" % (name, err))
            continue
        touched += 1
        for kind, before, after in changes:
            rows.append((name, kind, before, after))
        print("[%s] %s  (%d strings)" % ("check" if args.check else " ok  ", name, len(changes)))
        if args.check:
            continue
        dest = os.path.join(args.output, name) if args.output else path
        os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
        with open(dest, "w", encoding="utf-8", newline="") as handle:
            handle.write(result)

    with open(args.report, "w", encoding="utf-8-sig", newline="") as handle:
        csv.writer(handle).writerows(rows)
    print("\n%d/%d files with markup, %d strings rewritten" % (touched, total, len(rows) - 1))
    print("report: %s" % args.report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
