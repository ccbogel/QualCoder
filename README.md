# QualCoder
QualCoder is a qualitative data analysis application written in python3 (python 3.6 or newer versions) and pyqt5.

Text files can be typed in manually or loaded from txt, odt, docx, html, htm, epub and  pdf files. Images, video and audio can also be imported for coding. Codes can be assigned to text, images and a/v selections and grouped into categories in hierarchical fashion. Various types of reports can be produced including visual coding graphs, coder comparisons and coding frequencies.

This project has been tested under Ubuntu 20.04 and Windows 10. It has been used on Linux Mint 18.04 Lubuntu 18.04, Mac OS.
Instructions and other information are available here: https://qualcoder.wordpress.com/ and on the [Github Wiki](https://github.com/ccbogel/QualCoder/wiki).

## INSTALLATION 

### Linux

### Prerequisites
You will need to have a `python3.6` or newer version installed.
You will also need to have a `vlc` player installed - for audio and video. 


#### Debian-based Linuxes:

You can install the latest debian package from https://github.com/ccbogel/QualCoder-Debians

You may need to add unstable repos as described at https://www.binarytides.com/enable-testing-repo-debian/

Install these modules from the command line

`sudo apt install python3-lxml python3-ply python3-six python3-pdfminer python3-chardet python3-qt5 python3-pillow`

On some Linux versions you will need to install pip

`sudo apt install python3-pip`

You also need to run this command from the terminal for pdf importing:

`sudo python3 -m pip install pdfminer.six openpyxl ebooklib`

If your are not using the debian package:

Make the install.sh executable and run the install.sh script from the terminal. Make sure the qualcoder folder is in the same directory as the install.sh script (i.e. as it appears when you download the QualCoder-master folder). 

#### Fedora/CentOS/RHEL Linuxes

Retrieve the current package code from this repository

`git clone https://github.com/ccbogel/QualCoder.git`

Make `install_fedora.sh` executable (`chmod +x install_fedora.sh`) and run the `./install_fedora.sh` script from the terminal. Make sure the qualcoder folder is in the same directory as the install.sh script (i.e. as it appears when you download the QualCoder-master folder). The script is for python version 3.9.

This script installs the dependencies using dnf and the ebook libraries with a work-around, specified at https://github.com/ccbogel/QualCoder/issues/72#issuecomment-695962784.

Fedora uses wayland with does not work well with the Qt graphical interface (for now). I suggest you also install xwayland.


### Linux Use 

`./install.sh`

The qualcoder folder should be in the same directory as the install.sh script.

This will install QualCoder in the /usr/share directory and create a launcher. 

Alternatively go to the qualcoder directory and run in a terminal: `python3 __main__.py`


### Windows: 

Install  [VLC](https://www.videolan.org/vlc/download-windows.html) or from the Windows Store. 

Download the QualCoder software from: https://github.com/ccbogel/QualCoder. This is the newest, but not yet officially released, version of code. Alternatively, choose the most recent release. Click the green button "Code", and then "Download ZIP". Then, unpack the file in a selected place (e.g. desktop).

Open the unpacked folder "QualCoder-master", then open the folder "qualcoder" and make a shortcut of the file "__main__.py" on the desktop - for easier access. This file is the starting file for running software.
    
The software is written in Python and does not have an exe file for Windows. Download and install the Python programming language. The minimum version that works for QualCoder is 3.6.  [Python3](https://www.python.org/downloads/). Download the file (at the bottom of the web site) "Windows installer (64-bit)" (or 32-bit if you have an older system) and install Python.

IMORTANT: in the first window of the installation mark the option "Add Python to PATH" - it makes the last step easier.

The final step, install extra modules to Python. Type the letters "cmd" in the Windows Start searching engine, and click on the black software "cmd.exe" - this is the command console for Windows. In the console paste, using the right-click context menu (ctrl+v does not work) the following:

`py -m pip install pyqt5 lxml Pillow ebooklib ply chardet pdfminer.six openpyxl py2exe`

You can skip the py2exe instruction above, as of 30 June 2021. It is not actively used right now, but will be used in the future.

Then click enter. Wait, until all modules are installed (the command phrase should be again visible: "C:\Users[Your Windows account name]> or similar).

Now, you should be able to run QualCoder by double-clicking the desktop shortcut.

The `py` command uses the most recent installed versionof python. You can use a specific version on your Windows, if you have many pythons installed, e.g. `py -3.8`  See discussion here: [Difference between py and python](https://stackoverflow.com/questions/50896496/what-is-the-difference-between-py-and-python-in-the-terminal)
You can run the cmd.exe as described above, and type `py` and Enter. The first line will tell you which version of python that command runs. To exit, press Ctrl Z.

Run QualCoder from cmd.exe
Move to the correct Drive.  e.g. C:  or P: or whatever the letter for the drive where qualcoder is stored.
Then type `py -m qualcoder`


### MacOS

1) Install recent versions of [Python3](https://www.python.org/downloads/) and [VLC](https://www.videolan.org/vlc/).

2) Download the latest release "Source code" version in ZIP format, from the releases section of the project here on Github: https://github.com/ccbogel/QualCoder/releasesDownload and extract it into /Applications

3) Open the Terminal app (or any other command shell)

4) Install PIP (if not yet installed, try typing `pip3 --version` and hit ENTER) 

```sh
curl https://bootstrap.pypa.io/get-pip.py -o get-pip.py
python3 get-pip.py
```

-> You should now be able to run `pip3` as above.

5) Install Python dependency modules using `pip`:

(you might already have them, don't do this again if you just update QualCoder to a newer version)

```sh
pip install pyqt5 lxml pillow six ebooklib ply chardet pdfminer.six openpyxl
```

6) Install system dependencies using Homebrew (aka `brew`) 

6.1) Install `brew` if do not already have it (try typing `brew` and hit ENTER):

* Follow instructions here about installing Homebrew on your macOS: https://brew.sh/

6.2) Install QPDF package (needed to deal with PDF files) using Homebrew package manager:

```sh
brew install qpdf
```


Assuming you downloaded the 2.5 version. You can now run with:

```
python3 /applications/QualCoder-2.5/qualcoder/__main__.py
```

You can install QualCoder anywhere you want, so the path above depends on where you extracted the archive.

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

Curtain, C. (2021) QualCoder 2.5 [Computer software]. Retrieved from
https://github.com/ccbogel/QualCoder/releases/tag/2.5


## Leave a review
If you like QualCoder and found it useful for your work. Please leave a review on these sites:

https://www.saashub.com/qualcoder-alternatives

https://alternativeto.net/software/qualcoder


