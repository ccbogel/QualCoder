# QualCoder 4.1

**This is an _in development_ release note so executables are not made until 4.1 is actually released.
Notes below will be updated as functions are added and identified errors fixed.**

# Installation

QualCoder is released under the LGPL v3 license

## Windows

Attached to the end of the release page, you will find two options:

Executables will be available when a release is made.

QualCoder_4_1_Win_setup.exe: a Windows installer will set up QualCoder like any normal app, with entries in the start menu, etc.
QualCoder_4_1_Win_Portable.exe: A portable binary. Double-click to run and wait for 15 seconds.

On first use of the exe, Windows will ask you to allow to run QualCoder. This is because it is from an unknown publisher. It costs a lot of money to get a trusted publisher certificate - so that will not be possible for the foreseeable future.

The executable files are large downloads. Occasionally you might get a Unconfirmed12345.CRDOWNLOAD file issue. First, check the file is fully downloaded. If not, then Resume downloads in your browser. If it seems to be fully downloaded, then rename Unconfirmed12345.CRDOWNLOAD to the name that was expected and double-click to run. (e.g. to QualCoder_4_1_Win_Setup.exe)

## MacOS

Attached to the end of the release page, you will find two options:

Executables will be available when a release is made.

QualCoder_4_1_arm64.dmg: App bundle for newer Macs with Apple Silicon (M1 ... M4 processors)
We are not able to compile a binary for Intel-based Macs right now due to incompatibilities in the libraries we use.
The app bundles are compiled on macOS Sequoia. They might also work on Sonoma and Ventura.

If you do not have admin rights on your macOS. The solution is to move the folder to /Users/mylogin/Applications and delete the com.apple.quarantine attribute from the dmg (xattr - d com.apple.quarantine /Users/mylogin/Applications/qualcoder.app).

We are currently not able to sign the app bundles, so you will get a warning that QualCoder is from an unregistered developer. You have to manually allow the app to be executed, if your Gatekeeper is active. Follow these steps:

Double-click the downloaded dmg-file.

Drag QualCoder into the link to your applications.
Start QualCoder by double-clicking the app within your applications folder. You will get an error that QualCoder is from an unregistered developer. The app will not start.
Go to Settings -> Privacy and Security -> Scroll down until you see a message stating QualCoder was prevented from starting. Click on "open anyway".
From now on, QualCoder should start without issues.

**Alternatively, install from source:**

Use a virtual environment (commands in point 6 below). Not using a virtual environment may affect other Python software you may have installed.

1. Download and install the Python programming language. Please use recent Python versions, e.g. 3.13 or newer. Older versions may cause issues  [Python3](https://www.python.org/downloads/macos/). Download the latest "macOS 64-bit universal2 installer" for one of the above-mentioned Python versions and open it to install Python.

2. Download the QualCoder software from: https://github.com/ccbogel/QualCoder from the Green Code button. This is the newest, but not yet officially released code (occasionally coding errors creep in).  Click the green button "Code", and then "Download ZIP". **Alternatively**, choose the most recent release zip. See the right-hand side of this page for the link to Releases.

3. Unzip the folder to a location (e.g. downloads) by double-clicking it. 

4. Use the Terminal app (`Applications -> Utilities -> Terminal`).

5. In the terminal, move (using the `cd` command) into the QualCoder folder. You should be inside the QualCoder-4.1 folder, e.g. 

```bash
cd Downloads/QualCoder-4.1
```

6. Install the virtual environment and required python modules. 

The `python3` command uses the most recent installed version of Python. You can use a specific version on your macOS, if you have many Python versions installed, e.g. `python3.13`. To verify you are using the correct Python version type `which python3`, which should output: `/Library/Frameworks/Python.framework/Versions/3.<version>/bin/python3`. If the output is `/usr/bin/python3`, don't continue, since this is your system's Python and it is discouraged to use.

The install may take up to 10 minutes. 

```bash
python3 -m venv env # this creates the virtual environment with the name "env" in your current directory
source env/bin/activate # this activates the virtual environment "env", (env) should appear in front of your prompt
pip3 install --upgrade pip # optionally; pip and pip3 are equivalent withing a virtual environment
pip3 install -r requirements.txt
```

7. Run QualCoder from the command prompt

```bash
cd src
python3 -m qualcoder # python and python3 are equivalent withing a virtual environment
```

8. If running QualCoder in a virtual environment, to exit the virtual environment type:

```bash
deactivate
```

The command prompt will then remove the *(env)* wording.

**To start QualCoder again**

If you are not using a virtual environment:

```bash
cd Downloads/QualCoder-4.1
cd src 
python3 -m qualcoder
```

If you are using a virtual environment:

```bash
cd Downloads/QualCoder-4.1
source env/bin/activate
cd src 
python3 -m qualcoder
```

## Linux

- If you are on **Debian based system (Debian, Ubuntu / Lubuntu / ZorinOS, Linux Mint)** :
  Install pip. This is a tool that downloads extra python modules :  `sudo apt install python3-pip`
  If you are using audio or video, install VLC (download from site) or: `sudo apt install vlc`
  If you are using the alternative Ubuntu Desktop manager **Xfce** you may need to run this: `sudo apt install libxcb-cursor0`
- If you are on **Fedora** : **There is a problem with using VLC from python. The software crashes, we are unable to find a solution to this. So audio and video cannot be used within a QualCoder project on Fedora.**
- If you are on **Arch/Manjaro Linux** : If you are using audio or video, install VLC (download from site) or: `sudo pacman -S vlc` and Install pip and venv: `sudo pacman -S python python-pip python-virtualenv`
  
1. Download and unzip the Qualcoder folder. 

2. Then `cd` to the QualCoder folder.

For example, you may now be in this folder, where you unzipped QualCoder: 

yourcomputer:~Downloads/QualCoder-4.1

3a. Instead of the commands from 3b. onwards, run the shell file which will run all these below commands. Make this file executable (Right-click and go to Properties), then type the below command and press Enter: 

`./run_from_source_Linux.sh`

3b. Instead of using the shell script, you can enter each of these commands to set up the virtual environment and install python modules. The virtual environment will be in its own folder called env. Installing the required modules for the first time takes a while, maybe 10 minutes.

```
python3 -m venv env
source env/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

5. Move to the inner src folder, then:
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

`bash -c 'cd ~/.local/share/qualcoder/src/ && ~/.local/share/qualcoder/env/bin/python3 -m qualcoder'`

# Changes in this release

Overall, improved the user interface styling to give a modern look. Reduced the number of style options to three only, to make maintenance easier: native, original, dark.

## Code Text, Code A/V

Added option to select multiple coded text segments and resize them, providing they are all in the exact same positions. Marker options now are: underline, marker (a strong coloured highlight of the coded text), marker light (a light coloured highlight of the coded text).

## Graph (Mind map)

Radial option, now displays multiple radial graphs where there are multiple root nodes (root categories or codes).

## Report Codes

More sort options: Image by filename / pdf page / y value ; Audio video timeline, by filename then start time value.

## Bug fixes

- macOS merge projects failed in 4.0. Fixed.

- emojis in text document causing some report issues: (1) Code retrival with context surrounding text - incorrect surrounding text; (2) Resizing coded segment in these text documents stored incorrect text due to incorrectly identified positions. Work has been done to improve emoji containing text. A Special Function has been added to fix older projects where the incorrectly stored coded text can be updated to the correct text.
- Improved REFI-QDA import accountisfor several errors.


# Known issues

-

