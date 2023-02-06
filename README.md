<img src="https://github.com/ccbogel/QualCoder/blob/master/qualcoder.png" width=200 height=200>

# IMPORTANT  -do not download the latest code from green code button - until this warning is removed. I uploaded three erroneous older files. Should be resolved within 24 hours. (6 Feb 2022 AEST)

# QualCoder
QualCoder is a qualitative data analysis application written in python3 and Qt6.

Text files can be typed in manually or loaded from txt, odt, docx, html, htm, md, epub and  pdf files. Images, video and audio can also be imported for coding. Codes can be assigned to text, images and a/v selections and grouped into categories in hierarchical fashion. Various types of reports can be produced including visual coding graphs, coder comparisons and coding frequencies.

This project has been tested under Ubuntu 22.04 and Windows 10/11. It has been used on MacOS and various Linux distros.
Instructions and other information are available here: https://qualcoder.wordpress.com/ and on the [Github Wiki](https://github.com/ccbogel/QualCoder/wiki).

## INSTALLATION 

### Prerequisites
You will need to have a python3.7 or newer version installed. Optional: VLC for audio/video coding. ffmpeg installed for speech to text and waveform image see:  https://phoenixnap.com/kb/ffmpeg-windows. VLC is required, for QualCoder releases 3.1 and lower.

### Windows

**Use the exe**

Newer releases contain an exe file (created on Windows 10, 64 bit). Double-click to run. Look for the Releases link on the right hand side of this page. I have had feedback of one instance on Windows where an anti-virus affected the importing and moving of files by QualCoder (AVG). 
An online virus testing site www.virustotal.com indicated 2 vendors out of many detected a potential problem due to their detection methods (false positives), 5 March 2022. Always check the MD5 checksum on downloading the exe. I have not got the exe Microsoft certified (I am not sure of the processes or cost involved).
If you are uncomfortable with these warnings install from source as detailed next.

**Alternatively install from source:**

Seriously consider using a virtual environment (commands in point 6 below). Not using a virtual environment may affect other python software you may have installed.

1. Download and install the Python programming language. The minimum version for QualCoder is 3.7. I recommend 3.10 for now.  [Python3](https://www.python.org/downloads/). Download the file (at the bottom of the web site) "Windows installer (64-bit)"

IMPORTANT: in the first window of the installation mark the option "Add Python to PATH"

2.  Download the QualCoder software from: https://github.com/ccbogel/QualCoder from the Green Code button. This is the newest, but not yet officially released code.  Click the green button "Code", and then "Download ZIP". Alternatively, choose the most recent release zip, see right hand side of this page for the link to Releases.

3.    Unzip the folder to a location (e.g. downloads). (Tip, remove the doubled up folder extraction QualCoder-master\QualCoder-master when asked where to extract. Just QualCoder-master). 

4. Use the Windows command prompt. Type "cmd" in the Windows Start search engine, and click on the black software "cmd.exe" - the command console for Windows. In the console type or paste, using the right-click mouse copy and paste (ctrl+v does not work)

5. In the command prompt, move (using the `cd` command) into the QualCoder folder. You should be inside the QualCoder-master folder or if using a release (the Qualcoder-3.1 folder). e.g. 

`cd Downloads\QualCoder-master`

6. Install and activate the virtual environment. This step can be skipped, but I recommend you do not skip it.

`pip install virtualenv`

Create a virtual environment called env.

`virtualenv env`

Activate the virtual environment, this changes the command prompt display using (brackets): (env) 

`env\Scripts\activate.bat`

7. Install python modules. Type the following:

`py -m pip install --upgrade pip`

`py -m pip install wheel pyqt6 chardet ebooklib lxml openpyxl Pillow ply pdfminer.six pandas plotly pydub python-vlc rispy SpeechRecognition`

 Wait, until all modules are installed .
 
8. Install Qualcoder, from the downloaded folder type

`py -m pip install .`

The `py` command uses the most recent installed version of python. You can use a specific version on your Windows, if you have many python versions installed, e.g. `py -3.10`  See discussion here: [Difference between py and python](https://stackoverflow.com/questions/50896496/what-is-the-difference-between-py-and-python-in-the-terminal)

9. Run QualCoder from the command prompt

`py -m qualcoder`

10. If running QualCoder in a virtual environment, to exit the virtual environment type:

`deactivate`

The command prompt will then remomove the  *(env)* wording.

**To start QualCoder again**

If you are not using virtual environment, as long as you are in the same drive letter, eg C:

`py -m qualcoder`

If you are using a virtual environment:

`cd` to the Qualcoder-master (or Qualcoder release folder), then type:

`env\Scripts\activate.bat `

`py -m qualcoder`

Note: 8 Dec 2022 - lxml may not install on python version 3.11 until a bug in lxml is fixed. Ignore errors related to this. lxml is only used to validate REFI-QDA data files.

### Debian/Ubuntu Linux

It is best to run QualCoder inside a python virtual environment, so that the system installed python modules do not clash and cause problems.

1. Recommend that you install vlc (download from site) or:

`sudo apt install vlc`

2. Install pip

`sudo apt install python3-pip`

1. Install venv
I am using python3.10  you can choose another recent version if you prefer, and if more recent versions are in the Ubuntu repository.

`sudo apt install python3.10-venv`

3. Download and unzip the Qualcoder folder.

4. Open a terminal and move (cd) into that folder. 
You should be inside the QualCoder-master folder or if using a release, e.g. the Qualcoder-3.1 folder.
Inside the QualCoder-master folder:

`python3.10 -m venv qualcoder`

Activate venv, this changes the command prompt display using (brackets): (qualcoder) 
Note: To exit venv type `deactivate`

`source qualcoder/bin/activate`

5. Update pip so that it installs the most recent python packages.

`pip install --upgrade pip`

6. Install the needed python modules.

`pip install chardet ebooklib lxml ply openpyxl pandas pdfminer pyqt6 pillow pdfminer.six plotly pydub python-vlc rispy six SpeechRecognition`

7. Install QualCoder, type the following, the dot is important:

`python3 -m pip install .`

You may get a warning which can be ignored: WARNING: Building wheel for Qualcoder failed

8. To run type

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

`sudo python3 -m pip install ebooklib plotly pydub python-vlc rispy SpeechRecognition`

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

The instructions work on Mac Monterey. It is recommended to use a virtual environment, see: https://sourabhbajaj.com/mac-setup/Python/virtualenv.html The below instructions can be used inside a virtual environment folder instead of placing in Applications.

1) Install recent versions of [Python3](https://www.python.org/downloads/) and [VLC](https://www.videolan.org/vlc/).

2) Download the latest release "Source code" version in ZIP format, from the releases section of the project here on Github: https://github.com/ccbogel/QualCoder/releases/tag/3.1 and extract it into /Applications

3) Open the Terminal app (or any other command shell)

4) Install PIP usingthese commands (if not yet installed, try typing `pip3 --version` and hit ENTER) 

```sh
curl https://bootstrap.pypa.io/get-pip.py -o get-pip.py


python3 get-pip.py
```

-> You should now be able to run `pip3` as above.

5) Install Python dependency modules using `pip`:

(you might already have them, don't do this again if you just update QualCoder to a newer version)

```sh
pip3 install chardet ebooklib lxml openpyxl pandas pillow ply pdfminer.six plotly pydub pyqt6 python-vlc rispy six SpeechRecognition
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


Assuming you downloaded the 3.1 version. You can now run with:

```
python3 /applications/QualCoder-3.1/qualcoder/__main__.py
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

1) Install Python dependency modules using `pip3`:

`pip3 install chardet ebooklib ffmpeg-python lxml pyqt6 pillow ply pdfminer.six openpyxl pandas plotly pydub python-vlc rispy six SpeechRecognition PyInstaller`

2) Create the Application. You will find it in the 'dist' folder and drag it to 'Applications'.
`pyinstaller qualcoder.spec`

 
## Dependencies
Required:

Python 3.7+ version, pyqt6, lxml, Pillow, six  (Mac OS), ebooklib, ply, chardet, pdfminer.six, openpyxl, pandas, plotly, pydub, python-vlc, rispy, SpeechRecognition, qpdf  (Linux for programatically applying pdf decryption for pdfs with blank password)

## License
QualCoder is distributed under the MIT LICENSE.

##  Citation APA style

Curtain, C. (2022) QualCoder 3.2 [Computer software]. Retrieved from
https://github.com/ccbogel/QualCoder/releases/tag/3.1


## Leave a review
If you like QualCoder and found it useful for your work. Please leave a review on these sites:

https://www.saashub.com/qualcoder-alternatives

https://alternativeto.net/software/qualcoder

Also, if you like Qualcoder a lot and want to advertise interst in it's use, please write an article about your experience using QualCoder.

## FaceBook group:
To allow everyone to discuss all things QualCoder.

FaceBook page:
[https://www.facebook.com/qualcoder](https://www.facebook.com/qualcoder)

FaceBook group:
[https://www.facebook.com/groups/1251478525589873](https://www.facebook.com/groups/1251478525589873)

