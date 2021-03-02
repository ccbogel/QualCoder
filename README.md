# QualCoder
QualCoder is a qualitative data analysis application written in python3 (python 3.6 or newer versions) and pyqt5.

QualCoder projects are stored in a Sqlite database. Text files can be typed in manually or loaded from txt, odt, docx, html, htm, epub and  pdf files. Images, video and audio can also be imported for coding. Codes can be assigned to text, images and a/v selections and grouped into categories in hierarchical fashion. Various types of reports can be produced including visual coding graphs, coder comparisons and coding frequencies.

This project has been tested under Ubuntu 20.04 and Windows 10. It has been used on Linux Mint 18.04 Lubuntu 18.04, Mac OS.
Instructions and other information are available here: https://qualcoder.wordpress.com/ and on the Github Wiki.

## INSTALLATION 


### Linux

### Prerequisites
You will need to have a `python3.6` or newer version installed.
You will also need to have a `vlc` player installed - for audio and video. 


#### Debian-based Linuxes:

You can install the latest debian package from https://github.com/ccbogel/QualCoder-Debians

You may need to add unstable repos as described at https://www.binarytides.com/enable-testing-repo-debian/

Install these modules from the command line

`sudo apt install python3-lxml python3-ply python3-six python3-chardet python3-qt5 python3-pillow`

On some Linux versions you will need to install pip

`sudo apt install python3-pip`

You also need to run this command from the terminal for pdf importing:

`sudo python3 -m pip install pdfminer.six openpyxl ebooklib`

If not using the debian package:

Make the install.sh executable and run the install.sh script from the terminal. Make sure the qualcoder folder is in the same directory as the install.sh script (i.e. as it appears when you download the QualCoder-master folder). 

#### Fedora/CentOS/RHEL Linuxes

Retrieve the current package code from this repository

`git clone https://github.com/ccbogel/QualCoder.git`

Install dependencies 

`sudo dnf install python3-pip python3-lxml python3-ply python3-six python3-chardet python3-qt5 python3-pillow`

QualCoder uses an Ebook library that you can currently install via a work-around, specified at https://github.com/ccbogel/QualCoder/issues/72#issuecomment-695962784
The UNTESTED `install_fedora.sh` should install the dependencies fand a desktop start icon for Fedora. The script is for python verrsion 3.8.


### Linux Use 

`./install.sh`

The qualcoder folder should be in the same directory as the install.sh script.

This will install QualCoder in the /usr/share directory and create a launcher. Alternatively go to the qualcoder directory and run the qualcoder.py file in a terminal: `python3 qualcoder.py`


### Windows: 

Install [Python3](https://www.python.org/downloads/) and [VLC](https://www.videolan.org/vlc/download-windows.html) or from the Windows Store. On Windows, the bit version of VLC, 32 or 64 must match the bit version of python 3. Minumum version python 3.6.

Install dependencies in the command prompt:

`python -m pip install pyqt5 lxml Pillow ebooklib ply chardet pdfminer.six openpyxl`

or:

`py -m pip install pyqt5 lxml Pillow ebooklib ply chardet pdfminer.six openpyxl`

To launch, you can create a shortcut to the qualcoder.py file to start QualCoder.

Alternatively move to the qualcoder directory and run the qualcoder.py file in from command prompt: 

`python qualcoder.py`  or `py qualcoder.py`

you might need to install modules and run the program by typing python3 rather than python or py, it seems different on different Winows versions.

Run QualCoder and hide the black DOS box:

`C:\Windows\pyw.exe "C:\the location of your Qualcoder folder\QualCoder-master\qualcoder\qualcoder.py"`

Sometimes there are problems recognising the audio/video VLC library file: libvlc.dll  
Some solutions are to add the path of the file here: [https://stackoverflow.com/questions/42045887/python-vlc-install-problems?noredirect=1](https://stackoverflow.com/questions/42045887/python-vlc-install-problems?noredirect=1)

The log file on Windows does not make use of the rotating file handler, so the log file may become large. If so, delete the log file. It will be re-created automatically.


### MacOS

Install python3 and VLC:
Install [Python3](https://www.python.org/downloads/) and [VLC](https://www.videolan.org/vlc/).

Download Qualcoder-master Zip file and copy it into /Applications

1) Open the Terminal app (or any other command shell)

2) Install PIP (if not yet installed, try typing `pip3 --version` and hit ENTER) 

```sh
curl https://bootstrap.pypa.io/get-pip.py -o get-pip.py
python3 get-pip.py
```

-> You should now be able to run `pip3` as above.

3) Install Python dependency modules using `pip`:

(you might already have them, don't do this again if you just update QualCoder to a newer version)

```sh
pip install pyqt5 lxml pillow six ebooklib ply chardet pdfminer.six openpyxl
```

4) Install system dependencies using Homebrew (aka `brew`) 

4.1) Install `brew` if do not already have it (try typing `brew` and hit ENTER):

* Follow instructions here about installing Homebrew on your macOS: https://brew.sh/

4.2) Install QPDF package (needed to deal with PDF files) using Homebrew package manager:

```sh
brew install qpdf
```

5) Finally, install QualCoder, anywhere you want on your system, most likely somewhere in your user home directory.

5.1) Download the latest "Source code" version in TAR/GZIP format, from the releases section of the project here on Github: https://github.com/ccbogel/QualCoder/releases

Assuming here after, you saved the archive of version 2.2 in your "Downloads" folder, and we would install directly in your "home" (`/Users/YourName/` or `~` for shortcut).

For example:

```sh
cd ~
tar -xzvf ~/Downloads/QualCoder-2.2.tar.gz
```

The last should have extracted all the archive into `~/QualCoder-2.2`. 

You can now run with:

```
python3 ~/QualCoder-2.2/qualcoder/qualcoder.py
```

Remember: You can install it anywhere you want, so the path above depends on where you extracted the archive before ;)

Another option to run Qualcoder is shown here: [https://www.maketecheasier.com/run-python-script-in-mac/](https://www.maketecheasier.com/run-python-script-in-mac/). This means you can right-click on the qualcoder.py file and open with --> python launcher. 
You can make an alias to the file and place it on your desktop.

**Another option to install on Mac:**

Open the Terminal App and move to the unzipped Qualcoder-Master directory, then run the following commands:

`pip install -U py2app`  or for a system installation of python `sudo pip install -U py2app`

`python3 setup.py py2app` 
 
## Dependencies
Required:

* Python 3.x version

* PyQt5

* lxml

* Pillow

* six  (Mac OS)

* ebooklib

* ply

* chardet

* pdfminer.six

* openpyxl

* qpdf  (Linux for programatically applying pdf decryption for pdfs with blank password)


## Future plans
* Improve packaging for easier installation: currently investigating use of pyinstaller - without success so far.
* Change from pdfminer.six to pdfminer3
* Possibly look at use with R.
* Reports:
        Word count report maybe
* Text mining - maybe 
    * word cloud, word visualisations - maybe
* General
    * Translations for GUI.

## License
QualCoder is distributed under the MIT LICENSE.

##  Citation APA style

Curtain, C. (2021) QualCoder 2.4 [Computer software]. Retrieved from
https://github.com/ccbogel/QualCoder/releases/tag/2.4


## Leave a review
If you like QualCoder and found it useful for your work. Please leave a review on these sites:

https://www.saashub.com/qualcoder-alternatives

https://alternativeto.net/software/qualcoder


## Publications using QualCoder
Local–global linkages: Challenges in organizing functional communities for ecosocial justice. Joel Izlar, Journal of Community Practice 27(3-4) 2019

Barriers to Health: Understanding the Barriers Faced by Community Intervention Projects. Vera Landrum, The University of Southern Mississippi 2020, Available from: https://aquila.usm.edu/cgi/viewcontent.cgi?article=1772&context=masters_theses

Framing food geographies. S Ramsay, Masters Thesis, Stockholms Universitet 2020

Seeking research software. A qualitative study of humanities scholars' information practices. Ronny Gey, Masters Thesis, Humboldt University of Berlin 2020

Traditional and biomedical care pathways for mental well‐being in rural Nepal. T Pham, R Koirala, B Kohrt, International Journal of Mental Health Systems volume 15 2021

