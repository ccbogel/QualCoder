""" from setup example: https://github.com/pypa/sampleproject/blob/master/setup.py
"""
import sys
from os import path

from setuptools import find_namespace_packages, setup

here = path.abspath(path.dirname(__file__))


def load_requirements(filename):
    """Return package requirements, skipping pip-only directives."""
    requirements = []
    with open(path.join(here, filename), encoding='utf-8') as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line or line.startswith('#'):
                continue
            if line.startswith((
                '-r', '--requirement',
                '-c', '--constraint',
                '-f', '--find-links',
                '--index-url', '--extra-index-url',
            )):
                continue
            # Keep URL fragments intact, but drop normal inline comments.
            if ' #' in line:
                line = line.split(' #', 1)[0].rstrip()
            requirements.append(line)
    return requirements


# Get the long description from the README file
with open(path.join(here, 'README.md'), encoding='utf-8') as f:
    long_description = f.read()

# Get requirements
required_modules = load_requirements('requirements.txt')

mainscript = 'src/qualcoder/__main__.py'
OPTIONS = {
    'argv_emulation': True,
    'iconfile': 'src/qualcoder/GUI/qualcoder.icns'
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
    version='4.0',
    url='http://github.com/ccbogel/QualCoder',
    author='Colin Curtain, Kai Dröge, Justin Missaghieh--Poncet, Lorenzo Salomón',
    author_email='ccbogel@hotmail.com',
    description='Qualitative data analysis',
    long_description=long_description,
    classifiers=[
        'License :: OSI Approved :: LGPL v3 License',
        'Programming Language :: Python :: 3',
        'Operating System :: OS Independent',
        'Development Status :: 3 - Alpha'
    ],
    keywords='qualitative data analysis',
    package_dir={'': 'src'},
    packages=find_namespace_packages(where='src', include=['qualcoder', 'qualcoder.*']),
    python_requires='>=3.10',
    install_requires=required_modules,
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
