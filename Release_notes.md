# Installation

QualCoder is released under the LGPL v3 license

## Windows

Attached to the end of release page you will find two options:

QualCoder_4_0_Win_setup.exe: a Windows installer, will set up QualCoder like any normal app, with entries in the start menu, etc.
QualCoder_4_0_Win_Portable.exe: A portable binary. Double-click to run and wait for 15 seconds.

On first use of the exe, Windows will ask you to allow to run QualCoder. This is because it is from an unknown publisher. It costs a lot of money to get a trusted publisher certificate - so that will not be possible for the foreseeable future.

The executable files are large downloads. Occasionally you might get a CRDOWNLOAD issue. First, check the file is fully downloaded. If not then Resume downloads in your browser. If it seems to be fully downloaded then rename it to the name that was expected and double-click to run. (e.g. From CRDOWNLOAD to QualCoder_4_0_Win_Setup.exe)

## MacOS

Attached to the end of release page you will find two options:

QualCoder_4_0_arm64.dmg: App bundle for newer Macs with Apple Silicon (M1 ... M4 processors)
We are not able to compile a binary for Intel based Macs right now due to incompatibilities in the libraries we use.
The app bundles are compiled on macOS Sequoia. They might also work on Sonoma and Ventura.

If you do not admin rights on your macOS. The solution is to move the folder to /Users/mylogin/Applications and delete the com.apple.quarantine attribute from the dmg (xattr – d com.apple.quarantine /Users/mylogin/Applications/qualcoder.app).

We are currently not able to sign the app bundles, so you will get a warning that QualCoder is from an unregistered developer. You have to manually allow the app to be executed, if your Gatekeeper is active. Follow these steps:

Double-click the downloaded dmg-file.

Drag QualCoder into the link to your applications.
Start QualCoder by double-clicking the app within your applications folder. You will get an error that QualCoder is from an unregistered developer. The app will not start.
Go to Settings -> Privacy and Security -> Scroll down until you see a message stating QualCoder was prevented from starting. Click on "open anyway".
From now on, QualCoder should start without issues.

## Linux Ubuntu, Lubuntu, Mint, ZorinOS, Debian, Arch

This binary should work on the above recent releases of Linux distros, e.g. Linux Mint 22.3, Ubuntu 24.04 etc.

QualCoder_4_0_ubuntu executable

The binary file may work in other distros also. You need to make it executable, via the GUI or using the terminal.

### Linux Fedora

Fedora has a segmentation fault (software crashes) which is, we believe, currently not fixed, regarding audio / video coding. This fault has not been recently tested, so it may or may not still be present.

## Manual install

For install from source code, download the zip file below and use the instructions in the README file to install on your operating system.

# Changes in this release

## Menus and tabs

Menus have been re-shuffled.

## Journals

Export are now to ODT format.

Right-click menu option to convert a journal to a file for coding within the QualCoder project.

## Manage files

There is an 'Import survey' button for importing surveys from Excel and csv files.

Multiple rows selection. For context menu Delete and Export.

When in the file name column pressing delete will delete the file(s).

## All coding screens

Added sub-menus for Modify (Code or ecategoert selected), Filter, Sort.

## Code text

Can set font and size for the document.

Can resize codes with movable handles.

Can export the coded document (to ODF format) via: coding with coloured highlights, commments, or as an analytic report.

Menu for the header section of the codes-tree to have automatic column resizing or manual resizing. Also for code trees in other coding areas.

Added a Filter icon when the Codes tree is fileter to specific codes (via Show codes like, or Show codes by colour).

## Code PDF

Menu for the header section of the codes-tree to have automatic column resizing or manual resizing. Also for code trees in other coding areas.

Added a Filter icon when the Codes tree is fileter to specific codes (via Show codes like, or Show codes by colour).

## Code images

Can resize coded areas using rightclick menu option and resize using handles.

## Co-occurrence report

Proximity graphs

Export format for Gephi import.

## Graph (mind map)

Improved manipulation of objects.

Export format for draw.io import.

Ability to expand and collapse graph portions (categories).

Another way via a dialog window to add coded segments.

Options to organise the graph layout - radion, vertical, horizontal.

Improved selection of font sizes and colours in menus.

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

