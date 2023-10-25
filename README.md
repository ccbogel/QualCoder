<img src="https://github.com/ccbogel/QualCoder/blob/master/qualcoder.png" width=200 height=200>

# QualCoder
QualCoder is a qualitative data analysis application written in python3 and Qt6.

Text files can be typed in manually or loaded from txt, odt, docx, html, htm, md, epub and  pdf files. Images, video and audio can also be imported for coding. Codes can be assigned to text, images and a/v selections and grouped into categories in hierarchical fashion. Various types of reports can be produced including visual coding graphs, word clouds, coder comparisons and coding frequencies.

This project has been tested under Ubuntu 22.04 and Windows 10/11. It has been used on MacOS and various Linux distros.
Instructions and other information are available here: https://qualcoder.wordpress.com/ and on the [Github Wiki](https://github.com/ccbogel/QualCoder/wiki).

It is best to download the Current Release from the Releases page, see the Releases link in the right hand column on this page.

If you like QualCoder please buy me a coffee ...

<a href="https://www.buymeacoffee.com/ccbogelB" target="_blank"><img src="https://cdn.buymeacoffee.com/buttons/default-orange.png" alt="Buy Me A Coffee" height="41" width="174"></a>


## INSTALLATION 

### Prerequisites
Optional: VLC for audio/video coding. 
Optional: ffmpeg installed for speech to text and waveform image see here to install ffmpeg on Windows:  https://phoenixnap.com/kb/ffmpeg-windows. 

For installing from source you will need to have python 3.8 or a newer version installed.

### Windows

**Use the exe**

Newer releases contain an exe file (created on Windows 10, 64 bit). Double-click to run. Look for the Releases link on the right hand side of this page. I have had feedback of one instance on Windows where an anti-virus affected the importing and moving of files by QualCoder (AVG). 
An online virus testing site www.virustotal.com indicated 2 vendors out of many detected a potential problem due to their detection methods (false positives), 5 March 2022. Always check the MD5 checksum on downloading the exe. I have not got the exe Microsoft certified (I am not sure of the processes or cost involved).
If you are uncomfortable with these warnings install from source as detailed next.

**Alternatively install from source:**

Seriously consider using a virtual environment (commands in point 6 below). Not using a virtual environment may affect other python software you may have installed.

1. Download and install the Python programming language. The minimum version for QualCoder is 3.8. I recommend 3.10 for now.  [Python3](https://www.python.org/downloads/). Download the file (at the bottom of the website) "Windows installer (64-bit)"

IMPORTANT: in the first window of the installation mark the option "Add Python to PATH"

2.  Download the QualCoder software from: https://github.com/ccbogel/QualCoder from the Green Code button. This is the newest, but not yet officially released code (occasionally coding errors creep in).  Click the green button "Code", and then "Download ZIP". **Alternatively**, choose the most recent release zip, see right hand side of this page for the link to Releases.

3.    Unzip the folder to a location (e.g. downloads). (Tip, remove the doubled up folder extraction QualCoder-master\QualCoder-master when asked where to extract. Just QualCoder-master). 

4. Use the Windows command prompt. Type "cmd" in the Windows Start search engine, and click on the black software "cmd.exe" - the command console for Windows. In the console type or paste, using the right-click mouse copy and paste (ctrl+v does not work)

5. In the command prompt, move (using the `cd` command) into the QualCoder folder. You should be inside the QualCoder-master folder or if using a release (the Qualcoder-3.3 folder). e.g. 

```bash
cd Downloads\QualCoder-master
```

6. Install and activate the virtual environment. This step can be skipped, but I recommend you do not skip it.

When not using a docker container, we recommend using a virtual environment to install packages. This will ensure that the dependencies for QualCoder are isolated from the rest of your system.

```bash
py -m venv env
env\Scripts\activate
```


7. Install python modules. Type the following:

```bash
py -m pip install --upgrade pip
```

```bash
py -m pip install wheel pyqt6 chardet ebooklib openpyxl Pillow ply pdfminer.six pandas plotly pydub python-vlc rispy SpeechRecognition wordcloud xmlschema
```

 Wait, until all modules are installed.

 Note: on some Windows computers, you may have to type `python3` instead of `py` as `py` may not be recognised.
 
8. Install Qualcoder, from the downloaded folder type

```bash
py -m pip install .
```

The `py` command uses the most recent installed version of python. You can use a specific version on your Windows, if you have many python versions installed, e.g. `py -3.10`  See discussion here: [Difference between py and python](https://stackoverflow.com/questions/50896496/what-is-the-difference-between-py-and-python-in-the-terminal)

9. Run QualCoder from the command prompt

```bash
py -m qualcoder
```

10. If running QualCoder in a virtual environment, to exit the virtual environment type:

`deactivate`

The command prompt will then remove the  *(env)* wording.

**To start QualCoder again**

If you are not using virtual environment, as long as you are in the same drive letter, eg C:

`py -m qualcoder`

If you are using a virtual environment:

`cd` to the Qualcoder-master (or Qualcoder release folder), then type:

`env\Scripts\activate.bat `

`py -m qualcoder`

### Debian/Ubuntu Linux

It is best to run QualCoder inside a python virtual environment, so that the system installed python modules do not clash and cause problems. If you are using the alternative Ubuntu Desktop manager **Xfce** you may need to run this: `sudo apt install libxcb-cursor0`

1. Recommend that you install vlc (download from site) or:

`sudo apt install vlc`

2. Install pip

`sudo apt install python3-pip`

1. Install venv
I am using python3.10  you can choose another recent version if you prefer, and if more recent versions are in the Ubuntu repository.

`sudo apt install python3.10-venv`

3. Download and unzip the Qualcoder folder.

4. Open a terminal and move (cd) into that folder. 
You should be inside the QualCoder-master folder or if using a release, e.g. the Qualcoder-3.4 folder.
Inside the QualCoder-master folder:

`python3.10 -m venv qualcoder`

Activate venv, this changes the command prompt display using (brackets): (qualcoder) 
Note: To exit venv type `deactivate`

`source qualcoder/bin/activate`

5. Update pip so that it installs the most recent python packages.

`pip install --upgrade pip`

6. Install the needed python modules.

`pip install chardet ebooklib ply openpyxl pandas pdfminer pyqt6 pillow pdfminer.six plotly pydub python-vlc rispy six SpeechRecognition wordcloud xmlschema`

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

`sudo pacman -S python python-chardet python-openpyxl python-pdfminer python-pandas python-pillow python-ply python-pyqt6 python-pip`

2. Install additional python modules

`sudo python3 -m pip install ebooklib plotly pydub python-vlc rispy SpeechRecognition wordcloud xmlschema`

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

1. Open your preferred shell (terminal).
2. Navigate to your preferred code directory.
3. There, run: `git clone https://github.com/ccbogel/QualCoder.git` and
4. enter the directory with `cd QualCoder`
5. Make `install_fedora.sh` executable (`chmod +x install_fedora.sh`) and
6. run the `./install_fedora.sh` script from the terminal. The script is for python version 3.11.

Then start QualCoder as any other app on your system.

Note 1_ This script installs the dependencies using dnf and the ebook libraries with a work-around, specified at https://github.com/ccbogel/QualCoder/issues/72#issuecomment-695962784.

Note 2: Fedora uses wayland with does not work well with the Qt graphical interface (for now). I suggest you also install xwayland.

### MacOS

The instructions work on Mac Monterey. It is recommended to use a virtual environment, see: https://sourabhbajaj.com/mac-setup/Python/virtualenv.html The below instructions can be used inside a virtual environment folder instead of placed in Applications.

You will need to install developer tools for macOS. [See https://www.cnet.com/tech/computing/install-command-line-developer-tools-in-os-x/](https://www.cnet.com/tech/computing/install-command-line-developer-tools-in-os-x/)

1) Install recent versions of [Python3](https://www.python.org/downloads/) and [VLC](https://www.videolan.org/vlc/).

2) Download the latest release "Source code" version in ZIP format, from the releases section of the project here on Github: https://github.com/ccbogel/QualCoder/releases/tag/3.4 and extract it into /Applications

3) Open the Terminal app (or any other command shell)

4) Install PIP using these commands (if not already installed). Check pip is installed: try typing `pip3 --version` and hit ENTER) 

```sh
curl https://bootstrap.pypa.io/get-pip.py -o get-pip.py


python3 get-pip.py
```

-> You should now be able to run `pip3` as above.

5) Install Python dependency modules using `pip`:

```sh
pip3 install chardet ebooklib openpyxl pandas pillow ply pdfminer.six plotly pydub pyqt6 python-vlc rispy six SpeechRecognition wordcloud xmlschema
```

Be sure that you are in the QualCoder-Master directory before doing Step 6.

To change the directory, enter or copy and run the script below.

`cd /Applications/QualCoder-3.4`

6) From the QualCoder-Master directory run the setup script:

`python3 -m pip install.`


Assuming you downloaded the 3.4 version. You can now run with:

```
python3 /applications/QualCoder-3.4/qualcoder/__main__.py
```

Alternative commands to run QualCoder (Suggestions):

From any directory:

`qualcoder`

From the QualCoder-Master directory:

`python3 -m qualcoder`

or

`python3 qualcoder/__main__.py`

You can install QualCoder anywhere you want, so the path above depends on where you extracted the archive.

Another option to run Qualcoder is shown here: [https://www.maketecheasier.com/run-python-script-in-mac/](https://www.maketecheasier.com/run-python-script-in-mac/). This means you can right-click on the qualcoder.py file and open with --> python launcher. 
You can make an alias to the file and place it on your desktop.

**Another option to install on Mac:**

Open the Terminal App and move to the unzipped Qualcoder-Master directory, then run the following commands:

1) Install Python dependency modules using `pip3`:

`pip3 install chardet ebooklib ffmpeg-python pyqt6 pillow ply pdfminer.six openpyxl pandas plotly pydub python-vlc rispy six SpeechRecognition wordcloud xmlschema`

2) Open the Terminal App and move to the unzipped Qualcoder-Master directory, then run the following commands:

`pip3 install -U py2app` or for a system installation of python `sudo pip3 install -U py2app`

`python3 setup.py py2app`

 
## Dependencies
Required:

Python 3.8+ version, pyqt6, Pillow, six  (Mac OS), ebooklib, ply, chardet, pdfminer.six, openpyxl, pandas, plotly, pydub, python-vlc, rispy, SpeechRecognition, wordcloud, XML schema

## License
QualCoder is distributed under the MIT LICENSE.

##  Citation APA style

Curtain, C. (2023) QualCoder 3.4 [Computer software]. Retrieved from
https://github.com/ccbogel/QualCoder/releases/tag/3.4

## Creator

Dr Colin Curtain BPharm GradDipComp Ph.D. Pharmacy lecturer at the University of Tasmania. I obtained a Graduate Diploma in Computing in 2011. I have developed my python programming skills from this time onwards. The QualCoder project originated from my use of RQDA during my Ph.D. - *Evaluation of clinical decision support provided by medication review software*. My original and now completely deprecated PyQDA software on PyPI was my first attempt at creating qualitative software. The reason for creating the software was that during my PhD RQDA did not always install or work well for me, but I did realise that I could use the same sqlite database and access it with python. The current database is different to the older RQDA version. This is an ongoing hobby project, perhaps a labour of love, which I do utilize with some of the Masters and Ph.D. students I supervise. I do most of my programming on Ubuntu using the PyCharm editor, and I do a small amount of testing on Windows. I do not have a mac or other operating system to check how well the software works regards installation and usage.

https://www.utas.edu.au/profiles/staff/umore/colin-curtain

https://scholar.google.com/citations?user=KTMRMWoAAAAJ&hl=en


## Leave a review
If you like QualCoder and found it useful for your work. Please leave a review on these sites:

https://www.saashub.com/qualcoder-alternatives

https://alternativeto.net/software/qualcoder

Also, if you like Qualcoder a lot and want to advertise interest in it's use, please write an article about your experience using QualCoder.

## FaceBook group:
To allow everyone to discuss all things QualCoder.

FaceBook page:
[https://www.facebook.com/qualcoder](https://www.facebook.com/qualcoder)

FaceBook group:
[https://www.facebook.com/groups/1251478525589873](https://www.facebook.com/groups/1251478525589873)

