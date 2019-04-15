# QualCoder
QualCoder is a qualitative data analysis application written in python3 and pyqt5.

QualCoder projects are stored in a Sqlite database. Text files can be typed in manually or loaded from txt, odt, docx, epub and  pdf files. Codes can be assigned to text and to images and grouped into categories in hierarchical fashion similar to Nvivo. Various types of reports can be produced including visual coding graphs, coder comparisons and coding frequencies.

This project has been tested under Ubuntu, Linux Mint 18 and Windows 10, partly tested on Lubuntu 16, Windows 10. It has not been throughly tested on Mac OS.
Instructions and other information are available here: https://qualcoder.wordpress.com/ and on the Github Wiki.

## INSTALLATION
You will need to have a python3.x version installed.
You will also need to have pyqt5 and lxml to get text from docx files.
You will also need to have a vlc player installed - for audio and video.

### Linux:

I have created a .deb package for QualCoder which can be installed into Debian/Ubuntu systems. This will install the QualCoder software by double-clicking on the .deb package. It is not a perfect package so you might have to re-install it to get it to install correctly.

### Manual install on Linux:

Once a python 3.x is installed, make the install.sh executable and run the install.sh script from the terminal: 

./install.sh

The qualcoder folder should be in te same directory as the install.sh script.

This will install QualCoder in the /usr/share directory and create a launcher. Alternatively move to the qualcoder directory and run the qualcoder.py file in a terminal: python3 qualcoder.py

### Windows: 

Install [Python3](https://www.python.org/downloads/) and [VLC](https://www.videolan.org/vlc/download-windows.html) or from the Windows Store.

Install dependencies in the command prompt:

python -m pip install pyqt5, lxml, Pillow

To launch, you can create a shortcut to the qualcoder.py file to start QualCoder.

Alternatively move to the qualcoder directory and run the qualcoder.py file in a terminal: python3 qualcoder.py

### MacOS

Install [Python3](https://www.python.org/downloads/) and [VLC](https://www.videolan.org/vlc/).

Install the Python dependencies using `pip`:

`pip install pyqt5 lxml pillow six`

There is no desktop icon launch right now for QualCoder. Open a new Terminal window in the directory and launch with `python qualcoder.py`.

## Dependencies
Required

* Python 3.x version

* PyQt5

* lxml

* Pillow

* vlc

## Issues
* Testing has only been performed on Ubuntu and Linux Mint and for a large part on Windows 10. Some usage conducted with Lubuntu. No testing has been performed on Apple MacOSX.

## Future plans
* Reports:
    * Word count report
    * Possibly look at text mining
    * HTML report output to include A/V segments
* Text mining
    * word cloud, word visualisations
* General
    * Translations for GUI

## License
QualCoder is distributed under the MIT LICENSE.
