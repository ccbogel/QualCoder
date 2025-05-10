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
Optional: ffmpeg installed for waveform image see here to install ffmpeg on Windows:  https://phoenixnap.com/kb/ffmpeg-windows. 

On the first start of QualCoder, you may want to [setup the AI enhanced features](#setup-of-the-ai-features) as described below.

### Windows

You have two options, see Releases link on the right-hand side of this page:
- Newer releases contain an **exe file** created on Windows 11. Double-click to run, it takes up to 20 seconds to start.
- Since version 3.6, there will also be a **Windows installer** available at the release page. 

On first use of the exe, Windows may ask you to allow to run QualCoder. This is because it is from an unknown publisher. It costs a lot of money to get a trusted publisher certificate - so that will not be possible for the foreseeable future. If you are uncomfortable with these warnings install from the source as detailed next.

**Alternatively, install from source:**

Use a virtual environment (commands in point 6 below). Not using a virtual environment may affect other Python software you may have installed.

1. Download and install the Python programming language. Please use Python 3.10, 3.11 or 3.12 on Windows, other versions may cause issues  [Python3](https://www.python.org/downloads/). Download the file (at the bottom of the website) "Windows installer (64-bit)"

IMPORTANT: in the first window of the installation mark the option "Add Python to PATH"

2.  Download the QualCoder software from: https://github.com/ccbogel/QualCoder from the Green Code button. This is the newest, but not yet officially released code (occasionally coding errors creep in).  Click the green button "Code", and then "Download ZIP". **Alternatively**, choose the most recent release zip, see the right-hand side of this page for the link to Releases.

3.    Unzip the folder to a location (e.g. downloads). (Tip, remove the doubled-up folder extraction QualCoder-master\QualCoder-master when asked where to extract. Just QualCoder-master). 

4. Use the Windows command prompt. Type "cmd" in the Windows Start search engine, and click on the black software "cmd.exe" - the command console for Windows. In the console type or paste, using the right-click mouse copy and paste (ctrl+v does not work)

5. In the command prompt, move (using the `cd` command) into the QualCoder folder. You should be inside the QualCoder-master folder or if using a release (the Qualcoder-3.6 folder). e.g. 

```bash
cd Downloads\QualCoder-master
```

6. Install the virtual environment and required python modules. 

The `py` command uses the most recent installed version of Python the `py` command does not work on all Windows OS, you may instead replace `py` with `python3` You can use a specific version on your Windows if you have many Python versions installed, e.g. `py -3.10`  See discussion here: [Difference between py and python](https://stackoverflow.com/questions/50896496/what-is-the-difference-between-py-and-python-in-the-terminal)

The install may take up to 10 minutes. On some Windows OS you may need to replace the _py_ command with _python3_ below: 

```bash
py -m venv env
env\Scripts\activate
py -m pip install --upgrade pip
py -m pip install -r requirements.txt
```

7. Run QualCoder from the command prompt

```bash
py -m qualcoder
```

8. If running QualCoder in a virtual environment, to exit the virtual environment type:

`deactivate`

The command prompt will then remove the  *(env)* wording.

**To start QualCoder again**

If you are not using a virtual environment, as long as you are in the same drive letter, eg C:

`py -m qualcoder`

If you are using a virtual environment:

`cd` to the Qualcoder-master (or Qualcoder release folder), then type:

`env\Scripts\activate `

`py -m qualcoder`

## MacOS

Attached to the current release linked at the right side of this page, you will find two options ('X' representing the current version):
- **QualCoder_X_arm64.dmg**: App bundle for newer Macs with Apple Silicon (M1 ... M4 processors)
- **QualCoder_X_x86_64.dmg**: App bundle for the older Macs with Intel processor (core i5, i7, etc).

The app bundles are compiled on macOS Sequoia. They might also work on Sonoma and Ventura. If you are on an older version, consider updating your OS or install QualCoder from source as described below.

Note: We are currently not able to sign the app bundles, so you will get a warning that QualCoder is from an unregistered developer. You have to manually allow the app to be executed, if your Gatekeeper is active. Follow these steps:
- Double-click the downloaded dmg-file.
- Drag QualCoder into the link to your applications (ignore the `__main__` folder also in the window).
- Start QualCoder by double-clicking the app within your applications folder. You will get an error that QualCoder is from an unregistered developer. The app will not start.
- Go to Settings -> Privacy and Security -> Scroll down until you see a message stating QualCoder was prevented from starting. Click on "open anyway".
- From now on, QualCoder should start without issues.

If these app bundles do not work for you and you want to **run QualCoder from source,** follow these steps: 

It is recommended to use a virtual environment, see: https://sourabhbajaj.com/mac-setup/Python/virtualenv.html The below instructions can be used inside a virtual environment folder instead of placed in Applications.

You will need to install developer tools for macOS. [See https://www.cnet.com/tech/computing/install-command-line-developer-tools-in-os-x/](https://www.cnet.com/tech/computing/install-command-line-developer-tools-in-os-x/)  If you do not have the developer code, just start the installation process below and you will be prompted to install the developer code. This may be easier than figuring out if you have it or how to get it. Expect this process to take a long time.

1) Install a recent version of [Python3](https://www.python.org/downloads/) e.g. 3.10, 3.11 or 3.12, (Note: Python 3.13 is not supported yet) and [VLC](https://www.videolan.org/vlc/).

2)  Download the QualCoder software from: https://github.com/ccbogel/QualCoder from the Green Code button. This is the newest, but not yet officially released code (occasionally coding errors creep in).  Click the green button "Code", and then "Download ZIP". **Alternatively**, choose the most recent release zip (e.g. source QualCoder-3.6.zip release), see the right-hand side of this page for the link to Releases. If you want to use this version, follow the installation instructions in the Readme.md included in the downloaded zip. Unzip it into the /Applications directory.

3) Open the Terminal app (or any other command shell). Install PIP using these commands (if not already installed). Check pip is installed: try typing `pip3 --version` and hit ENTER) 

```sh
curl https://bootstrap.pypa.io/get-pip.py -o get-pip.py

python3 get-pip.py
```

You should now be able to run `pip3` as above.

4) In the terminal or command line move to the QualCoder directory. Be sure that you are in the QualCoder-Master directory. Or with a release, the Qualcode-3.6 directory, for example. An alternative way to open Terminal in the correct location is to do this: Open Finder, open Applications, and right click on the QualCoder-master folder and select "New Terminal at Folder"

   To move to the directory, run the script below.

   `cd /Applications/QualCoder-master`

   Or with a release

  `cd /Applications/QualCoder-3.6`

5) Install Python dependency modules using `pip`, from the QualCoder-master directory. Or from the release directort QualCoder-3.6 directory:

```sh
pip3 install -r requirements.txt
```
If you are on an older, Intel-based Mac, you must perform the following step after installing all the other requirements:
```
pip install "numpy<2" # Don't forget the quotation marks
```

6) From the QualCoder-Master directory (or the QualCode-3.6 release directory) run the setup script:

`python3 -m pip install .`


7) Run QualCoder. You can now run with the below commands (if you used a release, replace QualCoder-master with QuyalCoder-3.6 or other release number):

```
python3 /applications/QualCoder-master/qualcoder/__main__.py
```

Alternative suggested commands to run QualCoder:

From any directory:

`qualcoder`

From the QualCoder-Master directory:

`python3 -m qualcoder`

or

`python3 qualcoder/__main__.py`

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

Install Wine for macOS and run a QualCoder exe, e.g. QualCoder-3.6.exe - see the [releases page](https://github.com/ccbogel/QualCoder/releases).

Wine is available through: https://www.winehq.org/

## Linux

Hopefully an easy way to run QualCoder on the following Linux distributions is to use Wine, https://www.winehq.org/.
There are binary Wine packages for Ubuntu, Debian, Fedora, SUSE, Slackware FreeBSD.
Once installed, run a Windows QualCoder exe file, e.g. QualCoder-3.6.exe - see the [releases page](https://github.com/ccbogel/QualCoder/releases).

### Ubuntu Linux

There is a link to an executable file (double-click to run) for Ubuntu in the 3.6 release. 

To install from source code below, inside a virtual environment. If you are using the alternative Ubuntu Desktop manager **Xfce** you may need to run this: `sudo apt install libxcb-cursor0`

1. If you are using audio or video, install vlc (download from site) or: `sudo apt install vlc`

2. Install pip and venv

`sudo apt install python3-pip python3.12-venv`

3. Download and unzip the Qualcoder folder. Then `cd` to the QualCoder folder.

4. Set up virtual environment and install python modules. The virtual environment will be in its own folder called env_qc. Installing required modules takes a while.

```python3.12 -m venv env
source env/bin/activate
pip3 install -–upgrade pip
pip install -r requirements.txt
```

5. Now, the command to start QualCoder:

`python3.12 -m qualcoder`

6. After using QualCoder deactiatve the virtual environment.

`deactivate`

**Usage:**

`cd QualCoder`

```source env/bin/activate
python3 -m qualcoder```

`deactivate`


**Usage:**

At any time `cd` to the Qualcoder folder and enter the following commands. On finishing type `deactivate` to exit the virtual environment.

`source env_qc/bin/activate`

`qualcoder`

### Fedora 41

The instructions below are to run from source code inside a virtual environment. These instructions download the current source code directly from GitHub. Note: Fedora uses Wayland which may not work well with the Qt graphical interface. It is suggested you also install Xwayland.

`sudo dnf install python3.12`

`virtualenv env_qc`

`source env_qc/bin/activate `

`pip3 install -–upgrade pip`

`git clone https://github.com/ccbogel/QualCoder.git`

`cd QualCoder`

`python3.12 -m pip install -r requirements.txt`

`python3.12 -m qualcoder`

`deactivate` 

**Usage:**

At any time `cd` to the Qualcoder folder and enter the following commands. On finishing type `deactivate` to exit the virtual environment.

`source env_qc/bin/activate`

`python3.12 -m qualcoder`

### Arch/Manjaro Linux

The best approach may be to run the Windows exe with Wine.
 
## Setup AI features
If you want to use the AI-enhaced features in QualCoder, additional setup is needed. When you start the app for the first time, a wizard will lead you through the setup process. You can also start this later via the menu by clicking on AI > Setup Wizard. These are the main steps:
1) You will have to enable the AI and select which model you want to use. 
- If you opt for one of the variants of GPT-4 (recommended), you'll need an API key from OpenAI. Go to https://platform.openai.com/ and create an account. Then go to your personal dashboard, click on 'API keys' in the menu on the left, create a key and enter it in the setting dialog of QualCoder. To use these models, you'll also need to purchase 'credits' from OpenAI. $5 seems to be the minimal amount you can pay, which will go a long way. The cost of a single request to the AI is usually in the order of a few cents only.  
- You can also use ["Blablador"](https://helmholtz-blablador.fz-juelich.de), a free service offered by the German academic research agency Helmholtz Society. This service runs open-source models (Mixtral 8x7b being the largest at the moment) and is very privacy-friendly, storing no data at all. The quality of the output is usable for simple questions, but not yet on par with GPT-4 from OpenAI. If you want to use Blablador, you'll need an API-key from the Helmholtz Society. You can sign up with you university account or Github, Google, ORCID. Follow the instructions here: (https://sdlaml.pages.jsc.fz-juelich.de/ai/guides/blablador_api_access/)[https://sdlaml.pages.jsc.fz-juelich.de/ai/guides/blablador_api_access/].
- You can switch between the different models at any time by using the Settings menu (AI > Settings).
2) On the first start of the AI, QualCoder will automatically download some additional components which are needed to analyze your documents locally (this model: https://huggingface.co/intfloat/multilingual-e5-large). This will take a while, please be patient.
- If you want to enable/disable the AI functionality later or change settings, click on AI > Settings.

## License
QualCoder is distributed under the LGPLv3 LICENSE.

##  Citation APA style

Curtain, C. Dröge, K. (2025) QualCoder 3.6 [Computer software]. Retrieved from
https://github.com/ccbogel/QualCoder/releases/tag/3.6

## Creator

Dr. Colin Curtain BPharm GradDipComp PhD Pharmacy lecturer at the University of Tasmania. I obtained a Graduate Diploma in Computing in 2011. I have developed my Python programming skills from this time onwards. The QualCoder project originated from my use of RQDA during my PhD - *Evaluation of clinical decision support provided by medication review software*. My original and now completely deprecated PyQDA software on PyPI was my first attempt at creating qualitative software. The reason for creating the software was that during my PhD RQDA did not always install or work well for me, but I did realise that I could use the same SQLite database and access it with Python. The current database is different from the older RQDA version. This is an ongoing hobby project, perhaps a labour of love, which I utilise with some Masters's and Ph.D. students whom I supervise.

https://www.utas.edu.au/profiles/staff/umore/colin-curtain

https://scholar.google.com/citations?user=KTMRMWoAAAAJ&hl=en

**Artificial intelligence features and more:** Dr. Kai Dröge, Institut für Sozialforschung, Frankfurt, Deutschland. https://www.ifs.uni-frankfurt.de/personendetails/kai-droege.html

## Leave a review
If you like QualCoder and find it useful for your work. Please leave a review on these sites:

https://www.saashub.com/qualcoder-alternatives

https://alternativeto.net/software/qualcoder

Also, if you like Qualcoder a lot and want to advertise interest in its use, please write an article about your experience using QualCoder.

## Warnings about other sources of information about QualCoder 

There is a book published called _Qualitative Data Analysis With Chatgpt And Qualcoder_ Pease be aware this book is not endorsed by the developers of QualCoder. The book contains some incorrect information about QualCoder.

Downloads of executables from other web sites. We do not endorse downloading of executables from anywhere other than the GitHub QualCoder releases page.

