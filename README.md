<img src="https://github.com/ccbogel/QualCoder/blob/master/qualcoder.png" width=200 height=200>

# QualCoder
QualCoder is a qualitative data analysis application written in python3 (python 3.6 or newer versions) and Qt6.

Text files can be typed in manually or loaded from txt, odt, docx, html, htm, epub and  pdf files. Images, video and audio can also be imported for coding. Codes can be assigned to text, images and a/v selections and grouped into categories in hierarchical fashion. Various types of reports can be produced including visual coding graphs, coder comparisons and coding frequencies.

This project has been tested under Ubuntu 20.04 and Windows 10. It has been used on MacOS and various Linux distros.
Instructions and other information are available here: https://qualcoder.wordpress.com/ and on the [Github Wiki](https://github.com/ccbogel/QualCoder/wiki).

_NOTE_ Transcriptions created with QualCoder 2.8 and newer will have a .txt file ending. These transcription files will not be recoginsed in older QualCoder versions. You will have to change the transcription name ending from '.txt' to '.transcribed' before opening any audio/video files to view or code if opening the project in older versions. In Sql Statements run this to have older versions recognise transcriptions (replace video.mp4 with the actual filename you have): `update source set name='video.mp4.transcribed' where name='video.mp4.txt'`

**MAJOR CHANGE (8 APRIL 2022) QUALCODER NOW USES THE Qt6 GRAPHICAL FRAMEWORK. I HAVE DONE A LOT OF TESTING TO TRACK DOWN ANY ISSUES IN THIS UPDATE. I MIGHT HAVE MISSED SOME, SO PLEASE POST ANY ERROR ISSUES. I WILL WAIT A MONTH AND THEN PUT THIS OUT AS A 3.0 RELEASE.**

## INSTALLATION 

### Prerequisites
You will need to have a python3.6 or newer version installed and a 64 bit VLC player installed. Optional: ffmpeg installed for speech to text and waveform image.

### Windows

Install  [VLC](https://www.videolan.org/vlc/download-windows.html) or from the Windows Store. 

Newer releases contain an exe file (created on Windows 10, 64 bit).Double-click to run. I have had feedback of one instance on Windows where an anti-virus affected the importing and moving of files by QualCoder (AVG). 
An online virus testing site www.virustotal.com indicated 2 vendors out of many detected a potential problem due to their detection methods (5 March 2022). Always check the MD5 checksum on downloading the exe. I have not got the exe Microsoft certified (I am not sure of the processes or cost involved).
If you are uncomfortable with these warnings install from source as detailed next.

**Alternatively install from source:**

Consider using a virtual environment, I have not tested using venv on a Windows intallation yet. Not using a virtual environment may affect other python software you may has installed.

1. Download the QualCoder software from: https://github.com/ccbogel/QualCoder from the Green Code button. This is the newest, but not yet officially released code. Alternatively, choose the most recent release. Click the green button "Code", and then "Download ZIP". Then, unpack the file in a selected place (e.g. desktop).

2. Download and install the Python programming language. The minimum version for QualCoder is 3.6.  [Python3](https://www.python.org/downloads/). Download the file (at the bottom of the web site) "Windows installer (64-bit)"
IMPORTANT: in the first window of the installation mark the option "Add Python to PATH"

3. Install python modules from command. Type "cmd" in the Windows Start search engine, and click on the black software "cmd.exe" - the command console for Windows. In the console type or paste, using the right-click context menu (ctrl+v does not work) the following:

`py -m pip install wheel pyqt6 lxml Pillow ebooklib ply chardet pdfminer.six openpyxl pandas plotly pydub SpeechRecognition`

 Wait, until all modules are installed .
 
4. Build and install Qualcoder, from the downloaded folder type

`py setup.py install`

The `py` command uses the most recent installed version of python. You can use a specific version on your Windows, if you have many python versions installed, e.g. `py -3.9`  See discussion here: [Difference between py and python](https://stackoverflow.com/questions/50896496/what-is-the-difference-between-py-and-python-in-the-terminal)

5. Run QualCoder from cmd.exe
Move to the QualCoder-master folder, then type 

`py -m qualcoder`

Alternately, run by double-click. Open the QualCoder-master\qualcoder folder. Double-click the __main__.py file to run. You can make a shortcut to this file and keep the shortcut on the desktop.

### Debian/Ubuntu Linux

It is best to run QualCoder inside a python virtual environment, so that the system installed python modules do not clash and cause problems.

1. Install venv
I am using python3.9  you can choose another recent version if you prefer, and if more recent versions are in the Ubuntu repository.

`sudo apt install python3.9-venv`

2. Download and unzip the Qualcoder folder.

3. Open a terminal and move (cd) into that folder. 
You should be inside the QualCoder-master folder or if using a release, e.g. the Qualcoder-2.9 folder.
Inside the QualCoder-master folder:

`python3.9 -m venv qualcoder`

Activate venv, this changes the command prompt display using (brackets): (qualcoder) 
Note: To exit venv type `deactivate`

`source qualcoder/bin/activate`

4. Update pip so that it installs the most recent python packages.

`pip install --upgrade pip`

5. Install the needed python modules.

`pip install lxml ply six pdfminer chardet pyqt6 pillow pdfminer.six openpyxl ebooklib pandas plotly pydub SpeechRecognition`

6. Install QualCoder, type the following, the dot is important:

`python3 -m pip install .`

You may get a warning which can be ignored: WARNING: Building wheel for Qualcoder failed

7. To run type

`qualcoder`

After all this is done, you can `deactivate` to exit the virtual environment.
At any time to start QualCoder in the virtual environment, cd to the Qualcoder-master (or Qualcoder release folder), then type:
`source qualcoder/bin/activate`
Then type
`qualcoder`



### Arch/Manjaro Linux

Not tested, but please see the above instructions to build QualCoder inside a virtual environment. The below installation instructions may affect system installed python modules.

1. Install modules from the command line

`sudo pacman -S python python-chardet python-lxml python-openpyxl python-pdfminer python-pandas python-pillow python-ply python-pyqt6 python-pip`

2. Install additional python modules

`sudo python3 -m pip install ebooklib plotly pydub SpeechRecognition`

If success, all requirements are satisfied.

3. Build and install QualCoder, from the downloaded folder type

`sudo python setup.py install`

4. To run type:

`qualcoder`

Or install from AUR as follows:

`yay -S qualcoder`

### Fedora/CentOS/RHEL linux

Not tested, but please see the above instructions to build QualCoder inside a virtual environment. The below installation instructions may affect system installed python modules.

Retrieve the current package code from this repository

`git clone https://github.com/ccbogel/QualCoder.git`

Make `install_fedora.sh` executable (`chmod +x install_fedora.sh`) and run the `./install_fedora.sh` script from the terminal. Make sure the qualcoder folder is in the same directory as the install.sh script (i.e. as it appears when you download the QualCoder-master folder). The script is for python version 3.10.

This script installs the dependencies using dnf and the ebook libraries with a work-around, specified at https://github.com/ccbogel/QualCoder/issues/72#issuecomment-695962784.

Fedora uses wayland with does not work well with the Qt graphical interface (for now). I suggest you also install xwayland.

### MacOS

1) Install recent versions of [Python3](https://www.python.org/downloads/) and [VLC](https://www.videolan.org/vlc/).

2) Download the latest release "Source code" version in ZIP format, from the releases section of the project here on Github: https://github.com/ccbogel/QualCoder/releases/tag/2.8 and extract it into /Applications

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
pip install pyqt6 lxml pillow six ebooklib ply chardet pdfminer.six openpyxl pandas plotly pydub SpeechRecognition
```

6) Install system dependencies using Homebrew (aka `brew`) 

6.1) Install `brew` if do not already have it (try typing `brew` and hit ENTER):

* Follow instructions here about installing Homebrew on your macOS: https://brew.sh/

6.2) Install QPDF package (needed to deal with PDF files) using Homebrew package manager:

```sh
brew install qpdf
```

From the QualCoder-Master directory run the setup script:

`python3 setup.py install`


Assuming you downloaded the 3.0 version. You can now run with:

```
python3 /applications/QualCoder-3.0/qualcoder/__main__.py
```

Alternative commands to run QualCoder (Suggestions):

From any directory:

`qualcoder`

From the QualCoder-Master directory:

`python -m qualcoder`

or

`python qualcoder/__main__.py`

You can install QualCoder anywhere you want, so the path above depends on where you extracted the archive.

Another option to run Qualcoder is shown here: [https://www.maketecheasier.com/run-python-script-in-mac/](https://www.maketecheasier.com/run-python-script-in-mac/). This means you can right-click on the qualcoder.py file and open with --> python launcher. 
You can make an alias to the file and place it on your desktop.

**Another option to install on Mac:**

Open the Terminal App and move to the unzipped Qualcoder-Master directory, then run the following commands:

`pip install -U py2app`  or for a system installation of python `sudo pip install -U py2app`

`python3 setup.py py2app` 
 
## Dependencies
Required:

Python 3.6+ version, pyqt6, lxml, Pillow, six  (Mac OS), ebooklib, ply, chardet, pdfminer.six, openpyxl, pandas, plotly, pydub,  SpeechRecognition, qpdf  (Linux for programatically applying pdf decryption for pdfs with blank password)

## License
QualCoder is distributed under the MIT LICENSE.

##  Citation APA style

Curtain, C. (2021) QualCoder 3.0 [Computer software]. Retrieved from
https://github.com/ccbogel/QualCoder/releases/tag/3.0


## Leave a review
If you like QualCoder and found it useful for your work. Please leave a review on these sites:

https://www.saashub.com/qualcoder-alternatives

https://alternativeto.net/software/qualcoder


