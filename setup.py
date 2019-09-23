from setuptools import setup, find_packages

def readme():
    with open('README') as f:
        return f.read()

setup(
    name='QualCoder',
    version='1.3',
    description='Qualitative data analysis',
    long_description=readme(),
    classifiers=[
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3',
        'Operating System :: OS Independent',
    ],
    entry_points = {
        'gui_scripts' : ['qualcoder = qualcoder.qualcoder:gui'],
        'console_scripts' : ['qualcoder-cli = qualcoder.qualcoder:cli'],
    },
    # data_files = [
        # ('share/applications/', ['qualcoder.desktop'])
    # ],
    packages=find_packages(),
    keywords='qualitative data analysis',
    url='http://github.com/ccbogel/QualCoder',
    author='Colin Curtain',
    author_email='ccbogel@hotmail.com',
    license='MIT',
    # install_requires=[
        # 'graphviz',
        # 'pyqt5',
        # 'lxml',
        # 'Pillow', 
        # 'pikepdf', 
        # 'six', 
        # 'ebooklib',
        # 'pdfminer.six',
        # 'ply',
        # 'chardet',
        # 'python-vlc',
        # 'click',
    # ],
    include_package_data=True,
    zip_safe=False,
)
