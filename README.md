# QualCoder
QualCoder is a qualitative data analysis application written in python3 and pyqt5.

QualCoder projects are stored in a Sqlite database. Text files can be typed in manually or loaded from txt, odt, docx and optionally ,and not ideally, pdf files. Codes can be assigned to text and to images and grouped into categories in hierarchical fashion similar to Nvivo. Various types of reports can be produced including visual coding graphs, coder comparisons and coding frequencies.

This project has been tested under Ubuntu/Linux Mint.
Instructions and other information are avaible here: https://qualcoder.wordpress.com/

## INSTALLATION
You will need to have a python3.x version installed.
You will also need to have pyqt5 and lxml to get text from docx files.

Linux:

Once python is installed run the install.sh script

The install.sh will run the following commands to install the pyqt5 and lxml modules:

sudo apt-get install python3-pyqt5

sudo apt-get install python3-lxml

sudo apt-get install python3-pil

Windows: 

python -m pip install pyqt5 

python -m pip install lxml
python -m pip install Pillow

If you are using Windows you can create a shortcut to the QualCoder.py file to start QualCoder.


This will install QualCoder in the /usr/share directory and create a launcher. Alternatively move to the qualcoder directory and run the qualcoder.py file in a terminal: python3 qualcoder.py

## Dependencies
Required

* Python 3.x version

* PyQt5

* lxml

* Pillow

## Issues
* Testing has only been performed on Ubuntu and Linux Mint. Some usage condcuted with Lubuntu. Some testing performed on Windows 10.

## Future plans
* Reports:
    * Word count report
    * possibly import audio and video files
    * possibly look at text mining

## License
QualCoder is distributed under the MIT LICENSE.
