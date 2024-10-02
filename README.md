<img src="https://github.com/ccbogel/QualCoder/blob/master/qualcoder.png" width=200 height=200>

# QualCoder AI (beta)

Note: This is an experimental version of QualCoder with AI-enhanced functionality.

**Version 3.6.1 beta (July 2024)** is a major rework with the following new features:
- **AI Chat:** Let the AI analyze codings or any other topic in your data and discuss the results (with exact sources, of course)
- **Prompt Editing:** You can now view and edit all the prompts that QualCoder uses under the hood to instruct the AI on how to analyze your data. You can also define your own prompts, targeted at your particular methods and research questions. This returns methodological control back to us as researchers.
- **Alternative AI models:** QualCoder can now use other AI models besides the ones from OpenAI. In particular, we gained access to a free service called ["Blablador"](https://helmholtz-blablador.fz-juelich.de), offered by the German academic research agency Helmholtz Society. This service runs open-source models (Mixtral 8x7b being the largest at the moment) and is very privacy-friendly, storing no data at all. The quality of the output is usable for simple questions, but not yet on par with GPT-4 from OpenAI.
- The **AI Search** (see video below for a demonstration) has been greatly improved. It now also allows selecting between different prompts/different types of search.

This AI enhanced version was created by [Kai Dröge](https://www.hslu.ch/de-ch/hochschule-luzern/ueber-uns/personensuche/profile/?pid=823), based on QualCoder 3.5

It is planned to integrate my additions into the main version of QualCoder soon. Until then, you can use the AI-enhanced version alongside the regular QualCoder. Both apps will not interfere with each other.

Special thanks to these people for their feedback and support in improving the first version of QualCoder AI:<br />
> Tom Meyer (Univ. of Bochum), Merle Koch, Ole Deitmer & Wenzel Urban (Univ. of Jena), Andrzej Strzałkowski (Polish Academy of Sciences), Isabel Steinhardt (Univ. of Paderborn), Christian Schneijderberg (Univ. of Kassel), Yves Jeanrenaud (Univ. of Munich) as well as Alexandre Strube (Forschungszentrum Jülich), the developer behind Blablador, and Colin Curtain (Univ. of Tasmania), the developer of QualCoder. 

### Functionality

Watch my [video on YouTube](https://www.youtube.com/watch?v=FrQyTOTJhCc):</br>
[![Horizontal Coding: AI-Based Qualitative Data Analysis in QualCoder, Free & Open Source](https://img.youtube.com/vi/FrQyTOTJhCc/hqdefault.jpg)](https://www.youtube.com/watch?v=FrQyTOTJhCc)

In addition to what's shown in the video, QualCoder AI now also includes an **AI Chat**, offering three forms of dicussions with the AI:
- **Code Chat:** Let the AI analyze the data in the codings for a particular code and chat about the results. You can choose between different prompts or define your own. The sources from your empirical data are referenced in the text.
- **Topic Chat:** Let the AI analyze any topic in you empirical data (independent of previous coding). Again, several prompts are available, the sources are referenced, and you can discuss the results with the AI.
- **General Chat:** Ask the AI anything, not related to your data. Basically a build-in ChatGPT.   

### Installation

**Windows:**
- Download "QualCoderAI_3_6_2_setup.exe" from here: https://drive.switch.ch/index.php/s/oiy17P7wTDkDFak. Switch drive is a secure data sharing platform for Swiss universities.
- If you get a warning that "Windows protected your PC" and the app comes from an "Unknown publisher", you have to trust us and click "Run anyway"

**MacOS:**
- Installer made by [gernophil](https://github.com/gernophil), thank you very much!
- If you have trouble getting QualCoder to run, you might need to update your operating system to the latest available version.   
- *Installation on M1/M2/M3-based Macs:*
    - Download "Qualcoder_MAC_3_6_1b_arm64.dmg" from here: https://drive.switch.ch/index.php/s/Piozbkwkx90uxkK (switch drive is a secure data sharing platform for Swiss universities)
    - Double-click on the dmg-file, then drag QualCoder AI into the link to your applications folder.
    - Start QualCoder AI by double-clicking the app within your applications folder.
- *Installation on Intel-based Macs:*</br>
Note: Unfortunately, we are having trouble to sign the x86_64 package correctly, so you might get a warning that QualCoder AI is from an unregistered developer. You have to manually allow QualCoder AI to be executed, if your Gatekeeper is active. Follow these steps:
    - Download "Qualcoder_MAC_3_6_1b_x86_64.dmg" from here: https://drive.switch.ch/index.php/s/Piozbkwkx90uxkK (switch drive is a secure data sharing platform for Swiss universities)
    - Double-click the dmg-file.
    - Drag QualCoder AI into the link to your applications folder
    - Start QualCoder AI by double-clicking the app within your applications folder.
    - If you get an error that QualCoder AI is from an unregistered developer, go to Settings -> Privacy and Security -> Scroll down until you see a message stating QualCoder AI was prevented from starting and click "open anyway".
    - From now on, the program should start without issues.

**Linux:**
- Follow the [installation instructions below](#installation-1) (untested)

### Setup:
- QualCoder AI needs some additional setup to run it's AI-enhanced functions. When you start the app for the first time, a wizard will pop up and lead you through the setup process. You can aslo start this later via the menu by clicking on AI > Setup Wizard. These are the main steps:
  1) You'll have to enable the AI and select which model you want to use. 
    - If you opt for one of the variants of GPT-4, you'll need an API key from OpenAI. Go to https://platform.openai.com/ and create an account. Then go to your personal dashboard, click on 'API keys' in the menu on the left, create a key and enter it in the setting dialog of QualCoder. In order to use these models, you'll also need to purchase 'credits' from OpenAI. 5$ seems to be the minimal amount you can pay, which will go a long way. The cost of a single request to the AI is usually in the order of a few cents only.  
    - If you want to use Blablador, you'll need an API-key from the Helmholtz Society. Blablador is free to use. You can sign up with you university account or Github, Google, ORCID. Follow the instructions here: (https://sdlaml.pages.jsc.fz-juelich.de/ai/guides/blablador_api_access/)[https://sdlaml.pages.jsc.fz-juelich.de/ai/guides/blablador_api_access/].
    - You can switch between the different models at any time by using the Settings menu (AI > Settings).
  2) On the first start of the AI, QualCoder will automatically download some additional components which are needed to analyze your documents locally (this model: https://huggingface.co/intfloat/multilingual-e5-large). This will take a while, please be patient.
- If you want to enable/disable the AI functionality later or change settings, click on AI > Settings.

### Usage:
- You can download an example project here: https://drive.switch.ch/index.php/s/cYJKPA3JV3fJqDc?path=%2Fexample_project. This is the same data that I show in the video – a collection of interviews with Irish women about their experiences during the Second World War. It was created by Mary Muldowney and thankfully published under a creative commons license: https://repository.dri.ie/catalog/j38607880
- If you want to use your own data instead, go to Project > Create New Project and select a filename. Then go to Manage > Manage files and click on the second button from the left in the toolbar (arrow with document) to add a new document. 
- It is highly recommended to add a project memo with a short summary about your research topic, the questions and objectives, the methodology as well as the participants of your study and the types of data collected. This will give the AI helpful context information for the analysis. Go to Project > Project Memo to enter this information.
- The AI-based functionality in QualCoder is multilingual and supports up to 100 languages. The user interface, however, is only available in English, French, German, Italian, Portuguese and Spanish. 
- Once you added a new empirical document to you project, a local AI will read it in the background and memorize the contents in it's database. This happens only on your machine; no data is send to the cloud at this point. The memorization may take a few minutes, depending on the length of the document. You cannot use the AI-based functionality until the memorization of all documents is completed. (See the tab "Action Log" for progress messages.)
- Once the AI is ready, you can discuss your data in the "AI Chat" window. Click on "New" in the bottom left corner and select one of the three types of chat.
- To start the AI based search and coding, go to Coding > Code text, select the tab "AI Search" and click on "<Start AI Search>". If you haven't defined any codes yet, you can use the "Free search".
- Search tips: 
  - Don’t use too generic codes or search texts (like "gender” or "work") since this will lead to very generic results.
  - You can also use a memo attached to the code to define your code a little better and explain it to the AI. Make sure to also select the option “Send memo to AI” in the AI Search window.
 

**For general information about the usage of QualCoder visit the official Wiki: https://github.com/ccbogel/QualCoder/wiki**

---

**The rest of this document is from the regular version of QualCoder (with some small updates regarding the AI-based version).**

QualCoder is a qualitative data analysis application written in Python.

Text files can be typed in manually or loaded from txt, odt, docx, html, htm, md, epub, and  PDF files. Images, video, and audio can also be imported for coding. Codes can be assigned to text, images, and a/v selections and grouped into categories in a hierarchical fashion. Various types of reports can be produced including visual coding graphs, coder comparisons, and coding frequencies.

This software has been used on MacOS and various Linux distros.
Instructions and other information are available here: https://qualcoder.wordpress.com/ and on the [Github Wiki](https://github.com/ccbogel/QualCoder/wiki).

If you like QualCoder please buy me a coffee ...

<a href="https://www.buymeacoffee.com/ccbogelB" target="_blank"><img src="https://cdn.buymeacoffee.com/buttons/default-orange.png" alt="Buy Me A Coffee" height="41" width="174"></a>


## INSTALLATION 

Note: You should be able to run the AI-based version alongside the regular one. 

### Prerequisites
Optional: VLC for audio/video coding. 
Optional: ffmpeg installed for speech-to-text and waveform image see here to install ffmpeg on Windows:  https://phoenixnap.com/kb/ffmpeg-windows. 

For installing from source you will need to have Python 3.8 or a newer version installed.

### Windows

**Install from source:**

Seriously consider using a virtual environment (commands in point 6 below). Not using a virtual environment may affect other Python software you may have installed.

1. Download and install the Python programming language. The minimum version for QualCoder is 3.8. I recommend 3.10 for now.  [Python3](https://www.python.org/downloads/). Download the file (at the bottom of the website) "Windows installer (64-bit)"

IMPORTANT: in the first window of the installation mark the option "Add Python to PATH"

2.  Download the QualCoder software from: https://github.com/kaixxx/QualCoder/tree/ai_integration_rework (green 'Code' button > Download ZIP) or use git to clone the repo (make sure to use the 'ai_integration' branch)

3.    Unzip the folder to a location (e.g. downloads). 

4. Use the Windows command prompt. Type "cmd" in the Windows Start search engine, and click on the black software "cmd.exe" - the command console for Windows. In the console type or paste, using the right-click mouse copy and paste (ctrl+v does not work)

5. In the command prompt, move (using the `cd` command) into the QualCoder folder. You should be inside the QualCoder-ai_integration folder. e.g. 

```bash
cd Downloads\QualCoder-ai_integration
```

6. Install and activate the virtual environment. This step can be skipped, but I recommend you do not skip it.

When not using a docker container, we recommend using a virtual environment to install packages. This will ensure that the dependencies for QualCoder are isolated from the rest of your system. On some Windows OS you may need to replace the _py_ command with _python3_ below: 

```bash
py -m venv env
env\Scripts\activate
```


7. Install python modules. Type the following:

```bash
py -m pip install --upgrade pip
```

Type the following to install the required modules:

```bash
py -m pip install wheel pyqt6 chardet ebooklib openpyxl Pillow ply pdfminer.six pandas plotly pydub python-vlc rispy SpeechRecognition wordcloud xmlschema
```

For the AI-integration:

```bash
py -m pip install langchain langchain-community langchain-core langchain-chroma langchain-openai langchain-text-splitters chromadb==0.5.0 sentence-transformers fuzzysearch pydantic PyYAML json_repair
```
 
 Wait, until all modules are installed.

 Note: on some Windows computers, you may have to type `python3` instead of `py` as `py` may not be recognised.
 
8. Install Qualcoder, from the downloaded folder and type

```bash
py -m pip install .
```

The `py` command uses the most recent installed version of Python. You can use a specific version on your Windows if you have many Python versions installed, e.g. `py -3.10`  See discussion here: [Difference between py and python](https://stackoverflow.com/questions/50896496/what-is-the-difference-between-py-and-python-in-the-terminal)

9. Run QualCoder from the command prompt

```bash
py -m qualcoder
```

10. If running QualCoder in a virtual environment, to exit the virtual environment type:

`deactivate`

The command prompt will then remove the  *(env)* wording.

**To start QualCoder again**

If you are not using a virtual environment, as long as you are in the same drive letter, eg C:

`py -m qualcoder`

If you are using a virtual environment:

`cd` to the Qualcoder-master (or Qualcoder release folder), then type:

`env\Scripts\activate.bat `

`py -m qualcoder`

### Debian/Ubuntu Linux

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
You should be inside the QualCoder-master folder or if using a release, e.g. the Qualcoder-3.4 folder.
Inside the QualCoder-master folder:

`python3.10 -m venv qualcoder`

Activate venv, this changes the command prompt display using (brackets): (qualcoder) 
Note: To exit venv type `deactivate`

`source qualcoder/bin/activate`

5. Update pip so that it installs the most recent Python packages.

`pip install --upgrade pip`

6. Install the needed Python modules.

`pip install chardet ebooklib ply openpyxl pandas pdfminer pyqt6 pillow pdfminer.six plotly pydub python-vlc rispy six SpeechRecognition xmlschema`

`pip install langchain langchain-community langchain-core langchain-chroma langchain-openai langchain-text-splitters chromadb==0.5.0 sentence-transformers fuzzysearch pydantic PyYAML json_repair`

7. Install QualCoder, and type the following, the dot is important:

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

It has not been tested, but please see the above instructions to build QualCoder inside a virtual environment. The below installation instructions may affect system-installed python modules.

1. Install modules from the command line

`sudo pacman -S python python-chardet python-openpyxl python-pdfminer python-pandas python-pillow python-ply python-pyqt6 python-pip`

2. Install additional python modules

`sudo python3 -m pip install ebooklib plotly pydub python-vlc rispy SpeechRecognition xmlschema`
`sudo python3 -m pip install langchain langchain-community langchain-core langchain-chroma langchain-openai langchain-text-splitters chromadb==0.5.0 sentence-transformers fuzzysearch pydantic PyYAML json_repair`

If successful, all requirements are satisfied.

3. Build and install QualCoder, from the downloaded folder type

`sudo python setup.py install`

4. To run type:

`qualcoder`

Or install from AUR as follows:

`yay -S qualcoder`

### Fedora/CentOS/RHEL linux

Please see the above instructions to build QualCoder inside a virtual environment.

### MacOS

The instructions work on Mac Monterey. It is recommended to use a virtual environment, see: https://sourabhbajaj.com/mac-setup/Python/virtualenv.html The below instructions can be used inside a virtual environment folder instead of placed in Applications.

You will need to install developer tools for macOS. [See https://www.cnet.com/tech/computing/install-command-line-developer-tools-in-os-x/](https://www.cnet.com/tech/computing/install-command-line-developer-tools-in-os-x/)

1) Install recent versions of [Python3](https://www.python.org/downloads/) and [VLC](https://www.videolan.org/vlc/).

2) Download the latest release "Source code" version in ZIP format: https://github.com/kaixxx/QualCoder/tree/ai_integration_rework (green 'Code' button > Download ZIP). Extract it into /Applications

3) Open the Terminal app (or any other command shell)

4) Install PIP using these commands (if not already installed). Check pip is installed: try typing `pip3 --version` and hit ENTER) 

```sh
curl https://bootstrap.pypa.io/get-pip.py -o get-pip.py


python3 get-pip.py
```

-> You should now be able to run `pip3` as above.

5) Install Python dependency modules using `pip`:

```sh
pip3 install chardet ebooklib openpyxl pandas pillow ply pdfminer.six plotly pydub pyqt6 python-vlc rispy six SpeechRecognition
```

```sh
pip install langchain langchain-community langchain-core langchain-chroma langchain-openai langchain-text-splitters chromadb==0.5.0 sentence-transformers fuzzysearch pydantic PyYAML json_repair
```

Be sure that you are in the QualCoder-ai_integration directory before doing Step 6.

To change the directory, enter or copy and run the script below.

`cd /Applications/QualCoder-ai_integration`

6) From the QualCoder-Master directory run the setup script:

`python3 -m pip install .`


You can now run with:

```
python3 /Applications/QualCoder-ai_integration/qualcoder/__main__.py
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

Open the Terminal App and move to the unzipped Qualcoder-ai_integration directory, then run the following commands:

1) Install Python dependency modules using `pip3`:

`pip3 install chardet ebooklib ffmpeg-python pyqt6 pillow ply pdfminer.six openpyxl pandas plotly pydub python-vlc rispy six SpeechRecognition xmlschema`

`pip3 install langchain langchain-community langchain-core langchain-chroma langchain-openai langchain-text-splitters chromadb==0.5.0 sentence-transformers fuzzysearch pydantic PyYAML json_repair`

2) Open the Terminal App and move to the unzipped Qualcoder-ai_integration directory, then run the following commands:

`pip3 install -U py2app` or for a system installation of python `sudo pip3 install -U py2app`

`python3 setup.py py2app`

 
## Dependencies
Required:

Python 3.8+ version, pyqt6, Pillow, six  (Mac OS), ebooklib, ply, chardet, pdfminer.six, openpyxl, pandas, plotly, pydub, python-vlc, rispy, SpeechRecognition, xmlschema, langchain, langchain-community, langchain-core, langchain-chroma, langchain-openai, langchain-text-splitters, chromadb==0.5.0, sentence-transformers, fuzzysearch, pydantic, PyYAML, json_repair

## License
QualCoder is distributed under the MIT LICENSE.

##  Citation APA style

Curtain, C. & Dröge, K. (2023) QualCoder AI beta [Computer software]. Retrieved from
https://github.com/kaixxx/QualCoder/tree/ai_integration_rework

## Creators

**Dr. Colin Curtain** BPharm GradDipComp Ph.D. Pharmacy lecturer at the University of Tasmania. I obtained a Graduate Diploma in Computing in 2011. I have developed my Python programming skills from this time onwards. The QualCoder project originated from my use of RQDA during my PhD - *Evaluation of clinical decision support provided by medication review software*. My original and now completely deprecated PyQDA software on PyPI was my first attempt at creating qualitative software. The reason for creating the software was that during my PhD RQDA did not always install or work well for me, but I did realise that I could use the same SQLite database and access it with Python. The current database is different from the older RQDA version. This is an ongoing hobby project, perhaps a labour of love, which I utilize with some of the Masters's and Ph.D. students I supervise. I do most of my programming on Ubuntu using the PyCharm editor, and I do a small amount of testing on Windows. I do not have a Mac or other operating system to check how well the software works regards installation and usage.

https://www.utas.edu.au/profiles/staff/umore/colin-curtain

https://scholar.google.com/citations?user=KTMRMWoAAAAJ&hl=en

**Dr. Kai Dröge**, PhD in sociology (with a background in computer science), qualitative researcher and teacher, [Lucerne University for Applied Science (Switzerland)](https://www.hslu.ch/de-ch/hochschule-luzern/ueber-uns/personensuche/profile/?pid=823) and [Institute for Social Research, Frankfurt/M. (Germany)](https://www.ifs.uni-frankfurt.de/personendetails/kai-droege.html).

I'm also the author of [noScribe, an AI-based audio transcription app](https://github.com/kaixxx/noScribe) that runs locally on your computer and is made for qualitative research.


## Leave a review
If you like QualCoder and find it useful for your work. Please leave a review on these sites:

https://www.saashub.com/qualcoder-alternatives

https://alternativeto.net/software/qualcoder

Also, if you like Qualcoder a lot and want to advertise interest in its use, please write an article about your experience using QualCoder.
