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

Using AI to identify hard to see bugs, with solutions to resolve them.

## AI 

Improve AI model access.

## Code Text, Code A/V

Added option to select multiple coded text segments and resize them, providing they are all in the exact same positions. Marker options now are: underline, marker (a strong coloured highlight of the coded text), marker light (a light coloured highlight of the coded text).

Added Code Branch Filter to reduce tree clutter by showing only the select branch.

## Text Analysis - Lexicometry

New options for lexicometric analyses:

* Corpus creation for export to IRaMuTeQ.
* Text statistics report - summary, frequency table, hapax table. If selected, partition variable breakdown.
* Similarity graph with communities.
* Correspondence analysis.
* Reinert CHD (Classification Hiérarchique Descendante / Descending Hierarchical Classification). Dendrogram.
* BERTopic - topic modelling with BERT embeddings (sentence transformers).
  
## Graph (Mind map)

Radial option, now displays multiple radial graphs where there are multiple root nodes (root categories or codes).

## Report Codes

More sort options: Image by filename / pdf page / y value ; Audio video timeline, by filename then start time value.

## REFI export / import

Improvements to REFI QDPX Project export and import.

## References

Option to manually add a new reference.

## Text statistics (IRaMuTeQ methods)

New "Text statistics (IRaMuTeQ methods)" submenu in the Reports menu: builds an analysable corpus (coded segments or whole documents, with codes, cases and attributes as variables) from the project, with tokenisation, stopwords (built-in FR/EN lists plus an editable custom file) and optional light stemming, and a sparse forms x segments lexical table (active vs supplementary forms). Computation engines live in the pure-Python `irastats` package and are unit-tested without a GUI.
First analysis tab: descending text statistics (total occurrences, active/supplementary forms, decreasing frequency table, hapax, breakdown by partition variable), with CSV and HTML export.
New 'Specificities' tab: chi-square specificities per form and per modality of a partition variable (signed value, two-sided p-value via scipy.stats.chi2, configurable probability threshold, default 0.05), sorted from most to least specific, with CSV/HTML export and over/under-representation highlighting.
New 'Export IRaMuTeQ' button in the Corpus tab: writes the corpus (coded segments, plus whole documents when the checkbox is set) in the IRaMuTeQ text format, one '**** *code_<modality> *cas_<modality> *doc_<modality> ...' block per segment (native IRaMuTeQ variable format, restricted charset). The existing IRaMuTeQ export of the Report Codes dialog now shares the same token helper (irastats.corpus.iramuteq_token).
New 'Similarity graph' tab: co-occurrence graph of forms within segments (networkx), association measure configurable (Jaccard by default, or chi2/phi-squared), adjustable edge threshold, Louvain community detection (nodes colored by community, communities listed), halo of a selected form, drawn in a non-blocking matplotlib window (node size proportional to frequency, edge width to similarity), with PNG export.
New 'Correspondence analysis' tab: CA of the lexical table (forms x modalities of a partition variable, or forms x segments) by SVD of the standardized residuals (numpy only), eigenvalues/inertia table, factor map on axes 1x2 in a non-blocking matplotlib window (point size proportional to frequency, most contributive forms annotated), coordinates exported to CSV, PNG export.
New 'BERTopic' tab in the lexicometry dialog (proposal): BERT-based topic modeling of the corpus - sentence-transformers embeddings, clustering (HDBSCAN when available, else KMeans), c-TF-IDF topic words; unit of analysis selectable (coded segments / whole documents / UCI ~40 occurrences); topic table with representative segments, topic-size chart, distribution of topics by variable (code/case/document/attribute: table + stacked bar chart + CSV), and CSV export. Uses only dependencies already required by the AI features (scikit-learn is now declared explicitly).
Lexicometry dialog usability: wider window, tooltips on every button/checkbox/field, shorter comboboxes and stopwords field on its own row, explanation line under the parameters of each tab (UCI, CA, similarity graph, BERTopic), p-values of the specificities rounded to 3 decimals ("<0.001" when smaller), and a new 'Export ODT' button in the Text statistics tab.
The lexicometry dialog UI is now a Qt Designer file (src/GUI_UIs/ui_dialog_text_stats.ui, compiled to src/qualcoder/GUI/ui_dialog_text_stats.py with pyuic6), like the other dialogs; only icons, dynamic combo contents and signal connections are set in code.
Graphical consistency with the other QualCoder windows: all buttons of the lexicometry dialog are now square 32x32 icon buttons (minimumSize = maximumSize, as in the Reports dialogs such as code frequencies/comparisons), and the dialog is NonModal like ui_dialog_report_codings; layout margins and spacing keep the Qt defaults used across the other .ui files.
Lexicometry dialog reorganized into 5 tabs (Corpus / Statistics / Graphs / Reinert classification / Topics): Statistics and Graphs each show two result panels with shared parameters (partition variable, minimum frequency), the BERTopic tab is renamed Topics, and all graphs (similarity, CA factor map, Reinert dendrogram and forms x classes CA, topic charts) are now embedded directly in the dialog via matplotlib canvases, with an optional 'open in separate window' button and PNG export.
Wording of the lexicometry dialog: 'CA' is replaced by 'Correspondence analysis' in all labels, buttons and messages, and UCI is spelled out as 'initial context unit' in the tooltips, help texts and combo entries (French translation: 'unité de contexte initiale (UCI)', provided by the translation workflow).
Lexicometry dialog, Corpus tab: no more checkbox for the corpus source - it is inferred from the code selection: if all codes are selected (no filter) the whole documents are used (only the file selection applies), otherwise only the coded texts of the selected codes are used.
Lexicometry dialog, further UI feedback: the dialog no longer forces the main window minimum width (size policy Ignored when embedded in the Reports tab); in the Statistics tab the left/right split and the two duplicate tables are removed (each section shows only its HTML report); 'Modality' is renamed 'Category'; the help texts define segments/occurrences/forms/active forms/hapax, explain the correspondence analysis in one line, clarify that the edge threshold applies to the similarity graph only, and no longer mention the p-value decimals.
Lexicometry dialog, further feedback: in the Statistics tab a single Calculate button now runs all the statistics (descending statistics, frequencies, hapax, chi-square specificities) into one report shown in a single text area; the custom stopwords file row is removed from the Corpus tab (built-in stopword lists remain).
Lexicometry dialog, Topics tab: a busy pop-up is shown while the BERT model is downloaded/loaded and the topics are computed (first run can take several minutes), and the topic tables cap their columns at 500 px with word-wrapped rows so long texts fit.

New 'Reinert classification' tab: descending hierarchical classification (CHD, Reinert 1983/1990) of the corpus - UCI segmentation (~40 occurrences, bounded by punctuation), forms x UCI matrix of active forms (frequency >= 3), top-down binary splits maximizing the chi-square between classes (initialised from the first CA axis, refined by iterative reassignment, up to ~10 classes), with class profiles (signed chi-square specificities), most representative UCI per class, chi2/df summary, dendrogram of the classification tree (one color per class, most representative forms listed under each class) and CA of forms x classes (non-blocking matplotlib windows, PNG export), and CSV export. Defaults follow IRaMuTeQ and are adjustable in the dialog.

## Bug fixes

- macOS merge projects failed in 4.0. Fixed.

- emojis in text document causing some report issues: (1) Code retrival with context surrounding text - incorrect surrounding text; (2) Resizing coded segment in these text documents stored incorrect text due to incorrectly identified positions. Work has been done to improve emoji containing text. A Special Function has been added to fix older projects where the incorrectly stored coded text can be updated to the correct text.
- Improved REFI-QDA import accountisfor several errors.


# Known issues

-

