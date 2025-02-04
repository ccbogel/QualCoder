# Extracts all the translatable strings from all python files in the 
# qualcoder subdirectory, then integrates new strings into the 
# existing ".po" files, ready to be translated.
# Written by Kai Dröge (and ChatGPT)

import os
import subprocess

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

def main():
    directory = 'qualcoder'
    pot_filename = os.path.join(directory, 'qualcoder.pot')

    extract_pot_file(directory, pot_filename)
    update_po_files(directory, pot_filename)

if __name__ == '__main__':
    main()