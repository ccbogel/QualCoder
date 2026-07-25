We have jumped to version 4.0 as there are quite a few changes in this release.

# Installation

QualCoder is released under the LGPL v3 license

## Windows

Attached to the end of release page you will find two options:

Executables will be available when a release is made.

QualCoder_4_0_Win_setup.exe: a Windows installer, will set up QualCoder like any normal app, with entries in the start menu, etc.
QualCoder_4_0_Win_Portable.exe: A portable binary. Double-click to run and wait for 15 seconds.

On first use of the exe, Windows will ask you to allow to run QualCoder. This is because it is from an unknown publisher. It costs a lot of money to get a trusted publisher certificate - so that will not be possible for the foreseeable future.

The executable files are large downloads. Occasionally you might get a CRDOWNLOAD issue. First, check the file is fully downloaded. If not then Resume downloads in your browser. If it seems to be fully downloaded then rename it to the name that was expected and double-click to run. (e.g. From CRDOWNLOAD to QualCoder_4_0_Win_Setup.exe)

## MacOS

Attached to the end of release page you will find two options:

Executables will be aviaable when a release is made.

QualCoder_4_0_arm64.dmg: App bundle for newer Macs with Apple Silicon (M1 ... M4 processors)
We are not able to compile a binary for Intel based Macs right now due to incompatibilities in the libraries we use.
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

1. Download and install the Python programming language. Please use Python 3.12 on Windows, other versions may cause issues  [Python3](https://www.python.org/downloads/macos/). Download the latest "macOS 64-bit universal2 installer" for one of the above mentioned Python versions and open it to install Python.

2. Download the QualCoder software from: https://github.com/ccbogel/QualCoder from the Green Code button. This is the newest, but not yet officially released code (occasionally coding errors creep in).  Click the green button "Code", and then "Download ZIP". **Alternatively**, choose the most recent release zip, see the right-hand side of this page for the link to Releases.

3. Unzip the folder to a location (e.g. downloads) by double-clicking it. 

4. Use the Terminal app (`Applications -> Utilities -> Terminal`).

5. In the terminal, move (using the `cd` command) into the QualCoder folder. You should be inside the QualCoder-4.0 folder, e.g. 

```bash
cd Downloads/QualCoder-4.0
```

6. Install the virtual environment and required python modules. 

The `python3` command uses the most recent installed version of Python. You can use a specific version on your macOS, if you have many Python versions installed, e.g. `python3.12`. To verify you are using the correct Python version type `which python3`, which should output: `/Library/Frameworks/Python.framework/Versions/3.<version>/bin/python3`. If the output is `/usr/bin/python3`, don't continue, since this is your system's Python and it is discouraged to use.

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
cd Downloads/QualCoder-4.0
cd src 
python3 -m qualcoder
```

If you are using a virtual environment:

```bash
cd Downloads/QualCoder-4.0
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

yourcomputer:~Downloads/QualCoder-4.0

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

Core languages will be English, German, French, Spanish. this is due to having regular human review and updates. Additional languages are located in the Other Languages folder. These may not be human reviewed, and may not be updated recently.

## Data structure change

One major requested change is to allow codes to have sub-codes. This makes it possible to build hierarchies of codes and not only of categories.

## Backups

Project backups are now located in the same folder as the proejct path.

## Artificial Inteligence changes

Agentic restructure of AI features. Turns the AI chat into an agent that can not only talk, but also do things in QualCoder.
* Read-only gives the AI agent read access to the complete code tree, all the memos and codings, as well as the empirical data through a diverse set of search tools (text only).
*  Sandboxed allows for limited write-access: The agent can create new codes and codings, but it cannot change or delete existing ones. 
* Full access gives additional write access to existing codes, codings, attributes, and cases - with precautions: Destructive operation must be confirmed by the user.

## Menus and tabs

A new menu option Analysis has been added. Menu items have been re-organised between Analysis and Reports. The manage, Coding and Reports tabs have placeholder information that explains in more detail what each of these tabs is used for.

## Journals

Export are now to ODT format. Right-click menu option to convert a journal to a file for coding within the QualCoder project.

## Manage files

There is an 'Import survey' button for importing surveys from Excel and csv files. Multiple rows selection. For context menu Delete and Export. When in the file name column pressing delete will delete the file(s).

## The Codes Tree in all coding screens

Added sub-menus for Modify (Code or categories selected), Filter, Sort. Added a Filter icon when the Codes tree is filtered to specific codes (via Show codes like, or Show codes by colour). Added a code names text filter underneath the codes tree. Add a move category underneath category function. Can move a dragged item to the top and bottom of the visible tree, and the tree will scroll. Menu for the header section of the codes-tree to have automatic column resizing or manual resizing. Also for code trees in other coding areas.

## Code text

Can set font and size for the document. Can resize codes with movable handles. Can change text highlighting from marker style to underline style and or vertical code stripes. Can export the coded document (to ODF format) via: coding with coloured highlights, commments, or as an analytic report. Key presse for Shift B to go to bookmark, andC to add a new category. Edit text mode - now has a search bar.

## Code PDF

Vastly improved PDF presentation and manipulation (Thanks to Lorenzo for this). Text coding and image area coding can be performed on the PDF page. AI-assisted text analysis can be applied directly from the Code PDF window.

## Code images

Can resize coded areas using rightclick menu option and resize using handles.

## Code Audio / Video

A bookmark option has been added. So after it is aplied, in code A/V and view A/V (from mamage files) the ime position in the A/V will be restored and the text postiion will be restored. Key presses are B (make bookmark) and Shift B (go to bookmark).

## Co-occurrence report

Proximity graphs. Export format for Gephi import.

## Graph (mind map)

Improved manipulation of objects. Export format for draw.io import. Ability to expand and collapse graph portions (categories). Another way via a dialog window to add coded segments. Options to organise the graph layout - radion, vertical, horizontal. Improved selection of font sizes and colours in menus.

## Report codes

**Bug fixes**

-A/V search by cases:
--fixed an issue where the "important" filter and the ORDER BY clause were being applied to the wrong SQL query, causing incorrect filtering in audio/video results.

-Excel (XLSX) export: Fixed a duplicated column that incorrectly shifted the "a/v" value in case reports.

-"Only memos" filter in translated languages: The strings "Only memos" and "Only coded memos" were not marked for translation, causing the filter to fail in the Spanish version. It now works correctly in any language.

-Matrix headers: Fixed four issues that prevented code, file, and case memos from displaying correctly in the matrix view (including an "alll" typo, a comparison with an extra colon 'Case:', an incorrect tuple validation, and a misplaced "All memo" literal).

-"Also all memos" option: Now correctly displays the coded segment memo, a behavior that was previously missing despite being implied by the label.

-Fix merge projects error. Occured sometimes when projects with audio, video or image files are merged.

**New functions**

-Category hierarchy in headers: Full hierarchical path is now displayed before the code name (Root Category > Subcategory > … > Code), making the contextual reading of each segment easier.

-Co-occurring codes: Below each coded segment memo, the set of overlapping codes within the same file is listed in brackets, allowing quick identification of coding overlaps. Works for text, audio/video, and image data. View and export the overlapping codes.

-New category sorting option: Added a "Category A - z" "Category Z - a"  option to the sorting menu, which organizes results alphabetically according to the category hierarchy (with code name as a secondary criterion).

## Database queries

Run the sql using key press: Control + Enter Keys
Menu option - comment out selected text.

When running the sql statement, if a section of sql text is selected, only that selected text sql will be run.

## Charts

Can select stopwords from a list of several languages for the word cloud.

Added text filters to the combo-boxes for files, cases and categories. Right-click menu option.

## Report codes summary

Added context menu to Show coded files

## Report codes frequency

Added context menu to Show coded files, toggle automatic column width resize, show expanded code names.

# Known issues

-

