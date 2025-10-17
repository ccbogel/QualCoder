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
- Newer releases contain an **exe file** created on Windows 11. Double-click to run, it takes 20 seconds to start.
- Since version 3.6, there are **Windows installers** available on the release page. 

On first use of the exe, Windows may ask you to allow to run QualCoder. This is because it is from an unknown publisher. It costs a lot of money to get a trusted publisher certificate - so that will not be possible for the foreseeable future. If you are uncomfortable with these warnings install from the source as detailed next.

**Alternatively, install from source:**

Use a virtual environment (commands in point 6 below). Not using a virtual environment may affect other Python software you may have installed.

1. Download and install the Python programming language. Please use Python 3.10, 3.11 or 3.12 on Windows, other versions may cause issues  [Python3](https://www.python.org/downloads/). Download the latest "Windows installer (64-bit)" (or the one matching your architecture) for one of the above mentioned Python versions.

IMPORTANT: in the first window of the installation mark the option "Add Python to PATH"

2. Download the QualCoder software from: https://github.com/ccbogel/QualCoder from the Green Code button. This is the newest, but not yet officially released code (occasionally coding errors creep in).  Click the green button "Code", and then "Download ZIP". **Alternatively**, choose the most recent release zip, see the right-hand side of this page for the link to Releases.

3. Unzip the folder to a location (e.g. downloads). (Tip, remove the doubled-up folder extraction QualCoder-master\QualCoder-master when asked where to extract. Just QualCoder-master). 

4. Use the Windows command prompt. Type "cmd" in the Windows Start search engine, and click on the black software "cmd.exe" - the command console for Windows. In the console type or paste, using the right-click mouse copy and paste (ctrl+v does not work)

5. In the command prompt, move (using the `cd` command) into the QualCoder folder. You should be inside the QualCoder-master folder or if using a release (the Qualcoder-3.6 folder). e.g. 

```bash
cd Downloads\QualCoder-master
```

6. Install the virtual environment and required python modules. 

The `py` command uses the most recent installed version of Python. The `py` command does not work on all Windows OS, you may instead replace `py` with `python3`. You can use a specific version on your Windows if you have many Python versions installed, e.g. `py -3.10`. See discussion here: [Difference between py and python](https://stackoverflow.com/questions/50896496/what-is-the-difference-between-py-and-python-in-the-terminal)

The install may take up to 10 minutes. On some Windows OS you may need to replace the _py_ command with _python3_ below: 

```bash
py -m venv env
env\Scripts\activate
py -m pip install --upgrade pip
py -m pip install -r requirements.txt
```

7. Run QualCoder from the command prompt, versions up to 3.6

```bash
py -m qualcoder
```

Latest code, version 3.7 and up, cd to the inner src folder first:

```bash
cd src
py -m qualcoder
```

8. If running QualCoder in a virtual environment, to exit the virtual environment type:

`deactivate`

The command prompt will then remove the  *(env)* wording.

**To start QualCoder again**

If you are not using a virtual environment, as long as you are in the same drive letter, eg C:

`py -m qualcoder`

If you are using a virtual environment:

`cd` to the Qualcoder-master (or Qualcoder release folder) for versions up to 3.6:

```
env\Scripts\activate 
py -m qualcoder
```

`cd` to the Qualcoder-master (or Qualcoder release folder) for versions 3.7and up:. 

```
env\Scripts\activate
cd src
py -m qualcoder
```

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

**Alternatively, install from source:**

Use a virtual environment (commands in point 6 below). Not using a virtual environment may affect other Python software you may have installed.

1. Download and install the Python programming language. Please use Python 3.10, 3.11 or 3.12 on Windows, other versions may cause issues  [Python3](https://www.python.org/downloads/macos/). Download the latest "macOS 64-bit universal2 installer" for one of the above mentioned Python versions and open it to install Python.

2. Download the QualCoder software from: https://github.com/ccbogel/QualCoder from the Green Code button. This is the newest, but not yet officially released code (occasionally coding errors creep in).  Click the green button "Code", and then "Download ZIP". **Alternatively**, choose the most recent release zip, see the right-hand side of this page for the link to Releases.

3. Unzip the folder to a location (e.g. downloads) by double-clicking it. 

4. Use the Terminal app (`Applications -> Utilities -> Terminal`).

5. In the terminal, move (using the `cd` command) into the QualCoder folder. You should be inside the QualCoder-master folder or if using a release (the Qualcoder-3.6 folder). e.g. 

```bash
cd Downloads/QualCoder-master
```

6. Install the virtual environment and required python modules. 

The `python3` command uses the most recent installed version of Python. You can use a specific version on your macOS, if you have many Python versions installed, e.g. `python3.10`. To verify you are using the correct Python version type `which python3`, which should output: `/Library/Frameworks/Python.framework/Versions/3.<version>/bin/python3`. If the output is `/usr/bin/python3`, don't continue, since this is your system's Python and it is discouraged to use.

The install may take up to 10 minutes. 

```bash
python3 -m venv env # this creates the virtual environment with the name "env" in your current directory
source env/bin/activate # this activates the virtual environment "env", (env) should appear in front of your prompt
pip3 install --upgrade pip # optionally; pip and pip3 are equivalent withing a virtual environment
pip3 install -r requirements.txt
```

7. Run QualCoder from the command prompt

```bash
cd src # only for version 3.7 and newer
python3 -m qualcoder # python and python3 are equivalent withing a virtual environment
```

8. If running QualCoder in a virtual environment (which you should), to exit the virtual environment type:

```bash
deactivate
```

The command prompt will then remove the *(env)* wording.

**To start QualCoder again**

If you are not using a virtual environment:

```bash
cd Downloads/QualCoder-master
cd src # only for version 3.7 and newer
python3 -m qualcoder
```

If you are using a virtual environment:

```bash
cd Downloads/QualCoder-master
source env/bin/activate
cd src # only for version 3.7 and newer
python3 -m qualcoder
```

## Linux

### Ubuntu Linux

There is a link to an executable file (double-click to run) for Ubuntu in the 3.6 release. 

To install from source code below, inside a virtual environment. If you are using the alternative Ubuntu Desktop manager **Xfce** you may need to run this: `sudo apt install libxcb-cursor0`

1. If you are using audio or video, install vlc (download from site) or: `sudo apt install vlc`

2. Install pip and venv

`sudo apt install python3-pip python3.12-venv`

3. Download and unzip the Qualcoder folder. Then `cd` to the QualCoder folder.

4. Set up virtual environment and install python modules. The virtual environment will be in its own folder called env. Installing required modules takes a while.

For example you might be in this folder, where you unzipped Qualcoder: 

yourcomputer:~Downloads/QualCoder-3.7

```
python3.12 -m venv env
source env/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

5. Latest code, version 3.7 and up, cd to the inner src folder first:

```
cd src
python3 -m qualcoder
```

6. After using QualCoder deactivate the virtual environment.

`deactivate`

**Usage any time after the install, move to the QualCoder folder then:**

```
source env/bin/activate
cd src
python3 -m qualcoder
```

To exit the environment:

`deactivate`

You can also make a .desktop file for launching QualCoder:

Create a .Desktop file for launch, enter this command (adapt it according to the location of the source code folder):

bash -c 'cd ~/.local/share/qualcoder/src/ && ~/.local/share/qualcoder/env/bin/python3.12 -m qualcoder'


### Fedora 42

These instructions download the current source code directly from GitHub. Note: Fedora uses Wayland which may not work well with the Qt graphical interface. It is suggested you also install Xwayland.
Audio and video coding - the software crashes and for now a solution has not been found.

`sudo dnf install python3.12`

```
virtualenv env
source env/bin/activate
python3.12 -m ensurepip
python3.12 -m pip install --upgrade pip
git clone https://github.com/ccbogel/QualCoder.git
cd QualCoder
python3.12 -m pip install -r requirements.txt
```
To run QualCoder 3.6:
```
python3.12 -m qualcoder
```

Latest code, version 3.7 and up, cd to the inner src folder first:

```
cd src
python3.12 -m qualcoder
```

To deactivate the virtual environment:

`deactivate` 

**Usage:**

At any time `cd` to the Qualcoder folder (if running QualCoder 3.7+ then cd to the inner src folder cd src`) and enter the following commands: 

```
cd QualCoder
source env/bin/activate
python3.12 -m qualcoder
```

On finishing type `deactivate` to exit the virtual environment.

Note re Fedora. This is an issue with coding audio / video. The software crashes, and unable to find a solution to this for now.

### Arch/Manjaro Linux

If you are using audio or video, install VLC (download from site) or: `sudo pacman -S vlc`

Install pip and venv:

`sudo pacman -S python python-pip python-virtualenv`

Download and unzip the Qualcoder folder. Then `cd` to the QualCoder folder.
Set up virtual environment and install python modules. The virtual environment will be in its own folder called env. Installing required modules takes a while.

```
python3 -m venv env
source env/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

Now, the command to start QualCoder, for versions up to 3.6:

`python3 -m qualcoder`

Latest code, version 3.7 and up, cd to the inner src folder first:

```
cd src
python -m qualcoder
```

After using QualCoder deactiatve the virtual environment.

`deactivate`

Usage any time after the install, move to the folder (then to inner src folder if using 3.7 and up), then:

```
cd QualCoder
source env/bin/activate
python3 -m qualcoder
```

To exit the environment:

`deactivate`
 
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

Curtain, C. Dröge, K. (2025) QualCoder 3.7 [Computer software]. Retrieved from
https://github.com/ccbogel/QualCoder/releases/tag/3.7

## Creator

**Dr. Colin Curtain** BPharm GradDipComp PhD Pharmacy lecturer at the University of Tasmania. I obtained a Graduate Diploma in Computing in 2011. I have developed my Python programming skills from this time onwards. The QualCoder project originated from my use of RQDA during my PhD - *Evaluation of clinical decision support provided by medication review software*. My original and now completely deprecated PyQDA software on PyPI was my first attempt at creating qualitative software. The reason for creating the software was that during my PhD RQDA did not always install or work well for me, but I did realise that I could use the same SQLite database and access it with Python. The current database is different from the older RQDA version. This is an ongoing hobby project, perhaps a labour of love, which I utilise with some Masters's and Ph.D. students whom I supervise.

https://www.utas.edu.au/profiles/staff/umore/colin-curtain

https://scholar.google.com/citations?user=KTMRMWoAAAAJ&hl=en

**Artificial intelligence features and more:** 

**Dr. rer. soc. Kai Dröge,** [University for Applied Science](https://www.hslu.ch/de-ch/hochschule-luzern/ueber-uns/personensuche/profile/?pid=823), Lucerne, Switzerland and [Institute for Social Research](https://www.ifs.uni-frankfurt.de/personendetails/kai-droege.html) Frankfurt, Germany. Kai is an experienced researcher and teacher of qualitative methods. His research interests are wide-ranging and include the sociology of emotions and intimate relationships, digital life and new media, and questions of economic and labor sociology. Recently, he has focused on the methodological challenges and opportunities of integrating AI into qualitative research. He is also the creator of [noScribe](https://github.com/kaixxx/noScribe#readme), a popular open-source transcription tool aimed especially at qualitative interviews.

## Leave a review

If you like QualCoder and find it useful for your work. Please leave a review on these sites:

https://www.saashub.com/qualcoder-alternatives

https://alternativeto.net/software/qualcoder

Also, if you like Qualcoder a lot and want to advertise interest in its use, please write an article about your experience using QualCoder.

## Warnings about other sources of information about QualCoder 

A book _Qualitative Data Analysis With Chatgpt And Qualcoder_. We have been advised the book may contain some incorrect information about QualCoder.

Downloads of executables from other web sites. We do not endorse downloading of executables from anywhere other than the GitHub QualCoder releases page.

