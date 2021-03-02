# QualCoder
QualCoder is a qualitative data analysis application written in python3 and pyqt5.

QualCoder projects are stored in a Sqlite database. Text files can be typed in manually or loaded from txt, odt, docx, html, htm, epub and  pdf files. Images, video and audio can also be imported for coding. Codes can be assigned to text, images and a/v selections and grouped into categories in hierarchical fashion. Various types of reports can be produced including visual coding graphs, coder comparisons and coding frequencies.

This project has been tested under Ubuntu 20.04, Linux Mint 18.04 Lubuntu 18.04, Windows 10. It has not been throughly tested on Mac OS.
Instructions and other information are available here: https://qualcoder.wordpress.com/ and on the Github Wiki.

## INSTALLATION 


### Linux

### Prerequisites
You will need to have a `python3.x` version installed.
You will also need to have a `vlc` player installed - for audio and video. 


#### Debian-based Linuxes:

You can install the latest debian package from https://github.com/ccbogel/QualCoder-Debians

You may need to add unstable repos as described at https://www.binarytides.com/enable-testing-repo-debian/

On some Linux versions you will need to install pip

`sudo apt install python3-pip`

You also need to run this command from the terminal for pdf importing:

`sudo python3 -m pip install pdfminer.six openpyxl`

If not using the debian package:

Make the install.sh executable and run the install.sh script from the terminal. Make sure the qualcoder folder is in the same directory as the install.sh script (i.e. as it appears when you download the QualCoder-master folder). 

#### Fedora/CentOS/RHEL Linuxes

Retrieve the current package code from this repository

`git clone https://github.com/ccbogel/QualCoder.git`

Install dependencies 

`sudo dnf install python3-pip python3-lxml python3-ply python3-six python3-chardet python3-qt5 python3-pillow`

QualCoder uses an Ebook library that you can currently install via a work-around, specified at https://github.com/ccbogel/QualCoder/issues/72#issuecomment-695962784

Except for install the debian-based installation of dependencies, the `install.sh` should run as expected.


### Linux Use 

`./install.sh`

The qualcoder folder should be in the same directory as the install.sh script.

This will install QualCoder in the /usr/share directory and create a launcher. Alternatively go to the qualcoder directory and run the qualcoder.py file in a terminal: `python3 qualcoder.py`


### Windows: 

Install [Python3](https://www.python.org/downloads/) and [VLC](https://www.videolan.org/vlc/download-windows.html) or from the Windows Store. On Windows, the bit version of VLC, 32 or 64 must match the bit version of python 3.

Install dependencies in the command prompt:

`python -m pip install pyqt5 lxml Pillow ebooklib ply chardet pdfminer.six openpyxl`

or:

`py -m pip install pyqt5 lxml Pillow ebooklib ply chardet pdfminer.six openpyxl`

To launch, you can create a shortcut to the qualcoder.py file to start QualCoder.

Alternatively move to the qualcoder directory and run the qualcoder.py file in from command prompt: 

`python qualcoder.py`  or `py qualcoder.py`

Sometimes there are problems recognising the audio/video VLC library file: libvlc.dll  
Some solutions are to add the path of the file here: [https://stackoverflow.com/questions/42045887/python-vlc-install-problems?noredirect=1](https://stackoverflow.com/questions/42045887/python-vlc-install-problems?noredirect=1)

The log file on Windows does not make use of the rotating file handler, so the log file may become large. If so, delete the log file. It will be re-created automatically.


### MacOS

Install [Python3](https://www.python.org/downloads/) and [VLC](https://www.videolan.org/vlc/).

Install the Python dependencies using `pip`:

`pip install pyqt5 lxml pillow six ebooklib ply chardet pdfminer.six openpyxl`

or 

`pip3 install pyqt5 lxml pillow six ebooklib ply chardet pdfminer.six openpyxl`

and

`brew install qpdf`

or

`sudo port install qpdf`

There is no desktop icon launch right now for QualCoder. Open a new Terminal window in the directory and launch with `python qualcoder.py`.

Another option is shown here [https://www.maketecheasier.com/run-python-script-in-mac/](https://www.maketecheasier.com/run-python-script-in-mac/). This means you can right-click on the qualcoder.py file and open with --> python launcher.
 You can make an alias to the file and place it on your desktop.
 
## Dependencies
Required:

* Python 3.x version

* PyQt5

* lxml

* Pillow

* six

* ebooklib

* ply

* chardet

* pdfminer.six

* openpyxl


## Future plans
* Improve packaging for easier installation: currently investigating use of pyinstaller - without success.
* Change from pdfminer.six to pdfminer3
* Look at RQDA Relation function and Profile matrix function.
* Possibly look at use with R.
* Reports:
        Word count report maybe
* Text mining - maybe 
    * word cloud, word visualisations - maybe
* General
    * Translations for GUI.

## License
QualCoder is distributed under the MIT LICENSE.

## Debian packages
See [https://github.com/ccbogel/QualCoder-Debians](https://github.com/ccbogel/QualCoder-Debians)

##  Citation APA style

Curtain, C. (2021) QualCoder 2.4 [Computer software]. Retrieved from
https://github.com/ccbogel/QualCoder/releases/tag/2.4

## Publications using QualCoder
Local–global linkages: Challenges in organizing functional communities for ecosocial justice. Joel Izlar, Journal of Community Practice 27(3-4) 2019

Barriers to Health: Understanding the Barriers Faced by Community Intervention Projects. Vera Landrum, The University of Southern Mississippi 2020, Available from: https://aquila.usm.edu/cgi/viewcontent.cgi?article=1772&context=masters_theses

Framing food geographies. S Ramsay, Masters Thesis, Stockholms Universitet 2020

