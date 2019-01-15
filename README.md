# QualCoder
QualCoder is a qualitative data analysis application written in python3 and pyqt5.

QualCoder projects are stored in a Sqlite database. Text files can be typed in manually or loaded from txt, odt, docx and optionally ,and not ideally, pdf files. Codes can be assigned to text and to images and grouped into categories in hierarchical fashion similar to Nvivo. Various types of reports can be produced including visual coding graphs, coder comparisons and coding frequencies.

This project has been tested under Ubuntu/Linux Mint.

## INSTALLATION
You will need to have a python3.x version installed.
You will also need to have pyqt5 installed.
Once python is installed install pyqt5 via these commands:
sudo pip3 install pyqt5  # on Linux
pip install pyqt5  # on Windows

If you are using Windows you can create a shortcut to the QualCoder.py file to start QualCoder.
On Linux - run the install.sh script
This will install QualCoder in the /usr/share directory and create a launcher. Alternatively move to the qualcoder directory and run the qualcoder.py file in a terminal: python3 qualcoder.py

## Dependencies
Required

* Python 3.x version

* PyQt5

Optional

* PyPdf to allow importing of pdf text

## Issues
* Testing has only been performed on Ubuntu and Linux Mint.

* Text loaded with PyPdf is not formatted at all. This includes no paragraph separations.
## Future plans
* Manage cases: When viewing a case, also show the images linked to the case.
* Manage files: view file - make modal so multiple files can be viewed

* Reports:
    * add functionality to add reports on images
    * add functionality to incoporate attributes in reports
    * word count/complexity
    * Matrix coding: categories by case

## License
QualCoder is distributed under the MIT LICENSE.
