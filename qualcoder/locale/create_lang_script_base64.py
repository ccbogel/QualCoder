#!/usr/bin/python
# -*- coding: utf-8 -*-

"""
This file is part of QualCoder.

QualCoder is free software: you can redistribute it and/or modify it under the
terms of the GNU Lesser General Public License as published by the Free Software
Foundation, either version 3 of the License, or (at your option) any later version.

QualCoder is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY;
without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
See the GNU General Public License for more details.

You should have received a copy of the GNU Lesser General Public License along with QualCoder.
If not, see <https://www.gnu.org/licenses/>.

Author: Colin Curtain (ccbogel)
https://github.com/ccbogel/QualCoder
https://qualcoder.wordpress.com/
"""

import base64

languages = ['de', 'es', 'fr', 'it', 'ja', 'pt', 'sv', 'zh']


class CreateHelperFile:
    """ Create an output python file with converted languages into base64
    The output file is used as a helper file in QualCoder
    This helps to get around translation data failing to load depending on where QualCoder
    is called from. Important for use with pyinstaller as accessing data files does not work well.
    """

    def __init__(self):

        header = '#!/usr/bin/python\n# -*- coding: utf-8 -*-\n\
        \n"""\nThis file is part of QualCoder.\n\
        QualCoder is free software: you can redistribute it and/or modify it under the\n\
        terms of the GNU Lesser General Public License as published by the Free Software\n\
        Foundation, either version 3 of the License, or (at your option) any later version.\n\n\
        QualCoder is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY;\n\
        without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.\n\
        See the GNU General Public License for more details.\n\n\
        You should have received a copy of the GNU Lesser General Public License along with QualCoder.\n\
        If not, see <https://www.gnu.org/licenses/>.\n\n\
        Author: Colin Curtain (ccbogel)\n\
        https://github.com/ccbogel/QualCoder\n\
        https://qualcoder.wordpress.com/\n\n\
        Generated base64 helper file\n"""\n\n'

        text = header
        # Create directory path Strings
        files = []
        for lang in languages:
            files.append(lang + "/" + "app_" + lang + ".qm")
            files.append(lang + "/LC_MESSAGES/" + lang + ".mo")

        # Convert each binary lang .mo or lang.qm to base64
        for f in files:
            text += "\n"
            name = f[:2] + "_" + f[-2:]
            text += name + " = b'"
            src = self.encode_base64(f)
            text += src.decode('utf-8')
            text += "'\n"

        # Write the generated file
        filename = "base64_lang_helper.py"
        base64file = open(filename, 'w', encoding='utf-8-sig')
        base64file.write(text)
        base64file.close()
        print("FINISHED CREATING BASE64 HELPER FILE")

    @staticmethod
    def encode_base64(file_path):
        """ Save the file in the .qualcoder/locale directory. """

        with open(file_path, "rb") as image_file:
            base64_string = base64.b64encode(image_file.read())
        return base64_string


if __name__ == '__main__':
    CreateHelperFile()
