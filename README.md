# QualCoder
QualCoder is a qualitative data analysis application written in python3 and pyqt5.

QualCoder projects are stored in a Sqlite database. Text files can be typed in manually or loaded from txt, odt, docx and pdf files. Codes can be assigned to text (and to images) and grouped into categories in hierarchical fashion. Various types of reports can be produced including network graphs, coding frequencies and several ways to query the database.

This project has been tested under Ubuntu/Linux Mint.

## INSTALLATION
You will need to have a python3.x version installed.
You will also need to have pyqt5 installed.
Once python is installed install pyqt5 via these commands:
sudo pip3 install pyqt5  # on Linux
pip install pyqt5  # on Windows

If you are using Windows you can create a shortcut to the QualCoder.py file to start QualCoder.
On Linux - run the install.sh script
This will install QualCoder in the /usr/share directory and create a launcher.

## Dependencies
Required

* Python 3.x version

* PyQt5

Optional

* PyPdf to allow importing of pdf text

## Issues
* Testing has only been performed on Ubuntu and Linux Mint.

* Text loaded with PyPdf is not formatted at all. This includes no paragraph separations.


## License
QualCoder is distributed under the MIT LICENSE.
