""" from setup example: https://github.com/pypa/sampleproject/blob/master/setup.py
"""
import sys
from setuptools import setup, find_namespace_packages
from os import path
here = path.abspath(path.dirname(__file__))
# Get the long description from the README file
with open(path.join(here, 'README.md'), encoding='utf-8') as f:
    long_description = f.read()

mainscript = 'qualcoder/__main__.py'
OPTIONS = {
    'argv_emulation': True,
    'iconfile': 'qualcoder/GUI/qualcoder.icns'
}

if sys.platform == 'darwin':
     extra_options = dict(
         setup_requires=['py2app'],
         app=[mainscript],
         # Cross-platform applications generally expect sys.argv to
         # be used for opening files.
         options={'py2app': OPTIONS},
     )
elif sys.platform == 'win32':
     extra_options = dict(
         setup_requires=['py2exe'],
         options = {'py2exe': {'bundle_files': 1, 'compressed': True}},
         windows = [{'script': mainscript}],
     )
# older code above the bracket:  app=[mainscript],
else:
     extra_options = dict(
         # Normally unix-like platforms will use "setup.py install"
         # and install the main script as such
         entry_points={
            'console_scripts': ['qualcoder=qualcoder.__main__:gui']
         },
     )


setup(
    name='Qualcoder',
    version='3.6',
    url='http://github.com/ccbogel/QualCoder',
    author='Colin Curtain',
    author_email='ccbogel@hotmail.com',
    description='Qualitative data analysis',
    long_description=long_description,
    classifiers=[
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3',
        'Operating System :: OS Independent',
        'Development Status :: 3 - Alpha'
    ],
    keywords='qualitative data analysis',
    packages=find_namespace_packages(include=['qualcoder','qualcoder.*']),
    python_requires='>=3.7',
    install_requires=[
        'pyqt6',
        'Pillow', 
        'ebooklib',
        'pdfminer.six',
        'ply',
        'chardet',
        'openpyxl',
        'pandas',
        'plotly',
        'pydub',
        'rispy',
        'SpeechRecognition'
    ],
    package_data={
        'qualcoder':['Codebook.xsd', 'Project-mrt2019.xsd',
        'GUI/*.html', 'GUI/NotoSans-hinted/*.ttf',
        'locale/de/app_de.qm', 'locale/de/LC_MESSAGES/de,mo',
        'locale/es/app_es.qm', 'locale/es/LC_MESSAGES/es,mo',
        'locale/fr/app_fr.qm', 'locale/fr/LC_MESSAGES/fr.mo',
        'locale/it/app_it.qm', 'locale/it/LC_MESSAGES/it.mo',
        'locale/pt/app_pt.qm', 'locale/pt/LC_MESSAGES/pt,mo',
        'locale/en/LC_MESSAGES/en,mo',]
    },
    zip_safe=False,
    include_package_data=True,
    **extra_options
)
