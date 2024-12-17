<img src="https://github.com/ccbogel/QualCoder/blob/master/qualcoder.png" width=200 height=200>

# QualCoder
QualCoder is a qualitative data analysis application written in Python.

Text files can be typed in manually or loaded from txt, odt, docx, html, htm, md, epub, and  PDF files. Images, video, and audio can also be imported for coding. Codes can be assigned to text, images, and a/v selections and grouped into categories in a hierarchical fashion. Various types of reports can be produced including visual coding graphs, coder comparisons, and coding frequencies. AI models like GPT-4 from OpenAI can be used to explore your data and analyze the results.  

This software has been used on MacOS and various Linux distros.
Instructions and other information are available here: https://qualcoder.wordpress.com/ and on the [Github Wiki](https://github.com/ccbogel/QualCoder/wiki).

It is best to download the Current Release from the Releases page: https://github.com/ccbogel/QualCoder/releases

If you like QualCoder please buy me a coffee ...

<a href="https://www.buymeacoffee.com/ccbogelB" target="_blank"><img src="https://cdn.buymeacoffee.com/buttons/default-orange.png" alt="Buy Me A Coffee" height="41" width="174"></a>

## INSTALLATION 

### Prerequisites
Optional: VLC for audio/video coding. 
Optional: ffmpeg installed for speech-to-text and waveform image see here to install ffmpeg on Windows:  https://phoenixnap.com/kb/ffmpeg-windows. 

For installing from source you will need to have Python 3.10 or a newer version installed.

On the first start of QualCoder, you may want to [setup the AI enhanced features](#setup-of-the-ai-features) as described below.

### Windows

**Use the exe**

Newer releases contain an exe file (created on Windows 10, 64-bit). Double-click to run, it takes up to 20 seconds to start. Look for the Releases link on the right-hand side of this page. I have had feedback on one instance on Windows where an anti-virus affected the importing and moving of files by QualCoder (AVG). 
An online virus testing site www.virustotal.com indicated 2 vendors out of many detected a potential problem due to their detection methods (false positives), 5 March 2022. Always check the MD5 checksum on downloading the exe. I have not got the exe Microsoft certified (I am not sure of the processes or cost involved).
If you are uncomfortable with these warnings install from the source as detailed next.

**Alternatively, install from source:**


Seriously consider using a virtual environment (commands in point 6 below). Not using a virtual environment may affect other Python software you may have installed.

1. Download and install the Python programming language. Please use Python 3.10 on Windows, older or newer versions may cause issues  [Python3](https://www.python.org/downloads/). Download the file (at the bottom of the website) "Windows installer (64-bit)"

IMPORTANT: in the first window of the installation mark the option "Add Python to PATH"

2.  Download the QualCoder software from: https://github.com/ccbogel/QualCoder from the Green Code button. This is the newest, but not yet officially released code (occasionally coding errors creep in).  Click the green button "Code", and then "Download ZIP". **Alternatively**, choose the most recent release zip, see the right-hand side of this page for the link to Releases.

3.    Unzip the folder to a location (e.g. downloads). (Tip, remove the doubled-up folder extraction QualCoder-master\QualCoder-master when asked where to extract. Just QualCoder-master). 

4. Use the Windows command prompt. Type "cmd" in the Windows Start search engine, and click on the black software "cmd.exe" - the command console for Windows. In the console type or paste, using the right-click mouse copy and paste (ctrl+v does not work)

5. In the command prompt, move (using the `cd` command) into the QualCoder folder. You should be inside the QualCoder-master folder or if using a release (the Qualcoder-3.5 folder). e.g. 

```bash
cd Downloads\QualCoder-master
```

6. Install and activate the virtual environment. This step can be skipped, but I recommend you do not skip it.

The `py` command uses the most recent installed version of Python the `py` command does not work on all Windows OS, you may instead replace `py` with `python3` You can use a specific version on your Windows if you have many Python versions installed, e.g. `py -3.10`  See discussion here: [Difference between py and python](https://stackoverflow.com/questions/50896496/what-is-the-difference-between-py-and-python-in-the-terminal)

We recommend using a virtual environment to install packages. This will ensure that the dependencies for QualCoder are isolated from the rest of your system. On some Windows OS you may need to replace the _py_ command with _python3_ below: 

```bash
py -m venv env
env\Scripts\activate
```


7. Install python modules. Type the following to upgrade all python modules before importing:

```bash
py -m pip install --upgrade pip
```

Type the following to install the required modules (it will take a minute or two):

```bash
py -m pip install -r requirements.txt
```

 Wait, until all modules are installed.

 Note: on some Windows computers, you may have to type `python3` instead of `py` as `py` may not be recognised.

8. Run QualCoder from the command prompt

```bash
py -m qualcoder
```

9. If running QualCoder in a virtual environment, to exit the virtual environment type:

`deactivate`

The command prompt will then remove the  *(env)* wording.

**To start QualCoder again**

If you are not using a virtual environment, as long as you are in the same drive letter, eg C:

`py -m qualcoder`

If you are using a virtual environment:

`cd` to the Qualcoder-master (or Qualcoder release folder), then type:

`env\Scripts\activate.bat `

`py -m qualcoder`

## Linux

Hopefully an easy way to run QualCoder on the following Linux distributions is to use Wine, https://www.winehq.org/.
There are binary packages for Ubuntu, Debian, Fedora, SUSE, Slackware FreeBSD.
Once installed, run a QualCoder exe file, e.g. QualCoder-3.5.exe - see the [releases page](https://github.com/ccbogel/QualCoder/releases).

### Debian/Ubuntu Linux

There is an executable file (double-click to run) for Ubuntu 22 in the 3.5 release. Alternatively, install from source code below.
It is best to run QualCoder inside a Python virtual environment so that the system-installed python modules do not clash and cause problems. If you are using the alternative Ubuntu Desktop manager **Xfce** you may need to run this: `sudo apt install libxcb-cursor0`

1. Recommend that you install vlc (download from site) or:

`sudo apt install vlc`

2. Install pip

`sudo apt install python3-pip`

1. Install venv
I am using python3.10  you can choose another recent version if you prefer, and if more recent versions are in the Ubuntu repository.

`sudo apt install python3.10-venv`

3. Download and unzip the Qualcoder folder.

4. Open a terminal and move (cd) into that folder. 
You should be inside the QualCoder-master folder or if using a release, e.g. the Qualcoder-3.5 folder.
Inside the QualCoder-master folder:

`python3.10 -m venv qualcoder`

Activate venv, this changes the command prompt display using (brackets): (qualcoder) 
Note: To exit venv type `deactivate`

`source qualcoder/bin/activate`

5. Update pip so that it installs the most recent Python packages.

`pip install --upgrade pip`

6. You must be in the QualCoder-master folder (Or the main release folder if using a release. e.g. QualCoder-3.5 folder). Install QualCoder, and type the following, the dot is important:

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

It has not been tested, but please see the above instructions to build QualCoder inside a virtual environment. The below installation instructions may affect system-installed python modules.

1. Install modules from the command line

`sudo pacman -S python python-chardet python-openpyxl python-pdfminer python-pandas python-pillow python-ply python-pyqt6 python-pip`

2. Install additional python modules

`sudo py -m pip install -r requirements.txt`

If successful, all requirements are satisfied.

3. Build and install QualCoder, from the downloaded folder type

`sudo python setup.py install`

4. To run type:

`qualcoder`

Or install from AUR as follows:

`yay -S qualcoder`

### Fedora/CentOS/RHEL linux

It has not been tested, but please see the above instructions to build QualCoder inside a virtual environment. The below installation instructions may affect system-installed Python modules.

Retrieve the current package code from this repository

1. Open your preferred shell (terminal).
2. Navigate to your preferred code directory.
3. There, run: `git clone https://github.com/ccbogel/QualCoder.git` and
4. enter the directory with `cd QualCoder`
5. Make `install_fedora.sh` executable (`chmod +x install_fedora.sh`)  ! Note 13 Oct 2024: The shell script needs updating for the additonal AI modules!
6. Finally, run the `./install_fedora.sh` script from the terminal. The script is for Python version 3.11.

Then start QualCoder as any other app on your system.

Note 1_ This script installs the dependencies using dnf and the ebook libraries with a work-around, specified at https://github.com/ccbogel/QualCoder/issues/72#issuecomment-695962784.

Note 2: Fedora uses Wayland which does not work well with the Qt graphical interface (for now). I suggest you also install Xwayland.

### MacOS

The instructions work on Mac Monterey. It is recommended to use a virtual environment, see: https://sourabhbajaj.com/mac-setup/Python/virtualenv.html The below instructions can be used inside a virtual environment folder instead of placed in Applications.

You will need to install developer tools for macOS. [See https://www.cnet.com/tech/computing/install-command-line-developer-tools-in-os-x/](https://www.cnet.com/tech/computing/install-command-line-developer-tools-in-os-x/)

1) Install a recent version of [Python3](https://www.python.org/downloads/) e.g. 3.10, 3.11 or 3.12, (Note: Python 3.13 is not supported yet) and [VLC](https://www.videolan.org/vlc/).

2)  Download the QualCoder software from: https://github.com/ccbogel/QualCoder from the Green Code button. This is the newest, but not yet officially released code (occasionally coding errors creep in).  Click the green button "Code", and then "Download ZIP". **Alternatively**, choose the most recent release zip, see the right-hand side of this page for the link to Releases. If you want to use this version, follow the installation instructions in the Readme.md included in the downloaded zip.

3) Open the Terminal app (or any other command shell)

4) Install PIP using these commands (if not already installed). Check pip is installed: try typing `pip3 --version` and hit ENTER) 

```sh
curl https://bootstrap.pypa.io/get-pip.py -o get-pip.py


python3 get-pip.py
```

-> You should now be able to run `pip3` as above.

5) Install Python dependency modules using `pip`:

```sh
pip3 install -r requirements.txt
```

Be sure that you are in the QualCoder-Master directory before doing Step 6.

To change the directory, enter or copy and run the script below.

`cd /Applications/QualCoder-master`

6) From the QualCoder-Master directory run the setup script:

`python3 -m pip install .`


Assuming you downloaded the Qualcoder-master version. You can now run with:

```
python3 /applications/QualCoder-master/qualcoder/__main__.py
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

**Second option to install on macOS:**

Open the Terminal App and move to the unzipped Qualcoder-Master directory, then run the following commands:

1) Install Python dependency modules using `pip3`:

`pip3 install chardet ebooklib ffmpeg-python pyqt6 pillow ply pdfminer.six openpyxl pandas plotly python-vlc rispy six pydub SpeechRecognition`

Note: For 3.6 and up do not install pydub or SpeechRecognition. This function has been removed, as there were errors with the pydub module.

2) Open the Terminal App and move to the unzipped Qualcoder-Master directory, then run the following commands:

`pip3 install -U py2app` or for a system installation of python `sudo pip3 install -U py2app`

`python3 setup.py py2app`

**Third option to run on macOS:**

Install Wine for macOS and run a QualCoder exe, e.g. QualCoder-3.5.exe - see the [releases page](https://github.com/ccbogel/QualCoder/releases).

Wine is available through: https://www.winehq.org/
 
## Dependencies
See requirements.txt file

## Setup of the AI features
If you want to use the AI-enhaced features in QualCoder, additional setup is needed. When you start the app for the first time, a wizard will lead you through the setup process. You can also start this later via the menu by clicking on AI > Setup Wizard. These are the main steps:
1) You will have to enable the AI and select which model you want to use. 
- If you opt for one of the variants of GPT-4 (recommended), you'll need an API key from OpenAI. Go to https://platform.openai.com/ and create an account. Then go to your personal dashboard, click on 'API keys' in the menu on the left, create a key and enter it in the setting dialog of QualCoder. To use these models, you'll also need to purchase 'credits' from OpenAI. $5 seems to be the minimal amount you can pay, which will go a long way. The cost of a single request to the AI is usually in the order of a few cents only.  
- You can also use ["Blablador"](https://helmholtz-blablador.fz-juelich.de), a free service offered by the German academic research agency Helmholtz Society. This service runs open-source models (Mixtral 8x7b being the largest at the moment) and is very privacy-friendly, storing no data at all. The quality of the output is usable for simple questions, but not yet on par with GPT-4 from OpenAI. If you want to use Blablador, you'll need an API-key from the Helmholtz Society. You can sign up with you university account or Github, Google, ORCID. Follow the instructions here: (https://sdlaml.pages.jsc.fz-juelich.de/ai/guides/blablador_api_access/)[https://sdlaml.pages.jsc.fz-juelich.de/ai/guides/blablador_api_access/].
- You can switch between the different models at any time by using the Settings menu (AI > Settings).
2) On the first start of the AI, QualCoder will automatically download some additional components which are needed to analyze your documents locally (this model: https://huggingface.co/intfloat/multilingual-e5-large). This will take a while, please be patient.
- If you want to enable/disable the AI functionality later or change settings, click on AI > Settings.

## License
QualCoder is distributed under the MIT LICENSE.

##  Citation APA style

Curtain, C. (2023) QualCoder 3.6 [Computer software]. Retrieved from
https://github.com/ccbogel/QualCoder/releases/tag/3.6

## Creator

Dr. Colin Curtain BPharm GradDipComp Ph.D. Pharmacy lecturer at the University of Tasmania. I obtained a Graduate Diploma in Computing in 2011. I have developed my Python programming skills from this time onwards. The QualCoder project originated from my use of RQDA during my PhD - *Evaluation of clinical decision support provided by medication review software*. My original and now completely deprecated PyQDA software on PyPI was my first attempt at creating qualitative software. The reason for creating the software was that during my PhD RQDA did not always install or work well for me, but I did realise that I could use the same SQLite database and access it with Python. The current database is different from the older RQDA version. This is an ongoing hobby project, perhaps a labour of love, which I utilize with some of the Masters's and Ph.D. students I supervise. I do most of my programming on Ubuntu using the PyCharm editor, and I do a small amount of testing on Windows. I do not have a Mac or other operating system to check how well the software works regards installation and usage.

https://www.utas.edu.au/profiles/staff/umore/colin-curtain

https://scholar.google.com/citations?user=KTMRMWoAAAAJ&hl=en

**Artificial intelligence features and more:** Dr. Kai Dröge, Institut für Sozialforschung, Frankfurt, Deutschland. https://www.ifs.uni-frankfurt.de/personendetails/kai-droege.html

## Leave a review
If you like QualCoder and find it useful for your work. Please leave a review on these sites:

https://www.saashub.com/qualcoder-alternatives

https://alternativeto.net/software/qualcoder

Also, if you like Qualcoder a lot and want to advertise interest in its use, please write an article about your experience using QualCoder.

