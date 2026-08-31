#!/usr/bin/env python3
"""
Script to detect embedded _() translation calls inside f-strings in Python files.

This script scans Python files in the src/qualcoder directory and identifies
lines where the _() function is used inside f-strings, which is problematic for
gettext extraction (especially with gettext versions < 0.23).

Usage:
    Run this script from the tests/ directory or provide the src/qualcoder path.
"""

import os
import re
import sys
from pathlib import Path

def find_embedded_gettext_in_fstrings(file_path: str) -> list[tuple[int, str]]:
    """
    Scan a Python file and return lines where _() is used inside f-strings.

    Args:
        file_path: Path to the Python file to scan.

    Returns:
        List of tuples (line_number, line_content) where issues are found.
    """
    issues = []
    # Pattern to match f-strings containing _() calls, e.g., f"{_('text')}"
    pattern = re.compile(r'f[\'"].*\{\s*_\(.*\)\s*\}.*[\'"]')

    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            for line_number, line in enumerate(file, start=1):
                if pattern.search(line):
                    issues.append((line_number, line.strip()))
    except UnicodeDecodeError:
        # Skip files that cannot be read as UTF-8
        pass

    return issues

def scan_qualcoder_directory() -> dict[str, list[tuple[int, str]]]:
    """
    Scan the src/qualcoder directory for Python files and detect embedded _() in f-strings.

    Returns:
        Dictionary mapping file paths to lists of (line_number, line_content) tuples.
    """
    results = {}
    base_dir = os.path.join(os.path.dirname(__file__), "..", "src", "qualcoder")

    if not os.path.isdir(base_dir):
        print(f"Error: Directory '{base_dir}' does not exist.")
        sys.exit(1)

    for root, _, files in os.walk(base_dir):
        for file in files:
            if file.endswith('.py'):
                file_path = os.path.join(root, file)
                issues = find_embedded_gettext_in_fstrings(file_path)
                if issues:
                    results[file_path] = issues

    return results

def main():
    results = scan_qualcoder_directory()

    if not results:
        print("No issues found: No embedded _() calls inside f-strings detected in src/qualcoder.")
        return

    print("Detected embedded _() calls inside f-strings in src/qualcoder:")
    print("=" * 70)
    for file_path, issues in results.items():
        print(f"\nFile: {file_path}")
        for line_number, line_content in issues:
            print(f"  Line {line_number}: {line_content}")

    total_issues = sum(len(issues) for issues in results.values())
    print(f"\nTotal issues found: {total_issues}")

if __name__ == "__main__":
    main()
