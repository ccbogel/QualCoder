""" from setup example: https://github.com/pypa/sampleproject/blob/master/setup.py
"""

from setuptools import setup, find_packages
from os import path
here = path.abspath(path.dirname(__file__))
# Get the long description from the README file
with open(path.join(here, 'README.md'), encoding='utf-8') as f:
    long_description = f.read()

setup(
    name='qualcoder',
    version='1.8',
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
    packages=find_packages(where='qualcoder'),
    python_requires='>=3.5',
    install_requires=[
        'pyqt5',
        'lxml',
        'Pillow', 
        'ebooklib',
        'pdfminer.six',
        'ply',
        'chardet',
        'openpxyl'
    ],
    package_data={
        'qualcoder':['Codebook.xsd', 'Project-mrt2019.xsd',
        'GUI/*.html', 'GUI/NotoSans-hinted/*.ttf',
        'locale/de/app_de.qm', 'locale/de/LC_MESSAGES/de,mo',
        'locale/es/app_es.qm', 'locale/es/LC_MESSAGES/es,mo',
        'locale/de/app_fr.qm', 'locale/fr/LC_MESSAGES/fr,mo',
        'locale/en/LC_MESSAGES/en,mo',]
    },
    zip_safe=False,
)
