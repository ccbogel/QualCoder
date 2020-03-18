#!/bin/bash

echo "This installer is for Debian-based Linux installations only"
echo "This installer uses apt package management"
echo "QualCoder will be copied to the directory /usr/share/"
echo "These actions require owner (sudo) permission"
echo "The installer will also install dependencies"
sudo apt install python3-pip python3-pyqt5 python3-lxml python3-pil vlc python3-ebooklib python3-ply python3-six python3-chardet
echo "Please wait ..."
sudo python3 -m pip install pdfminer.six
sudo cp -r qualcoder /usr/share/qualcoder
sudo cp qualcoder/GUI/qualcoder.png /usr/share/pixmaps/qualcoder.png
sudo cp qualcoder/GUI/qualcoder.desktop /usr/share/applications/qualcoder.desktop
echo "If no errors then installation is completed."
echo "To remove qualcoder from Linux run the following in the terminal:"
echo "sudo rm -R /usr/share/qualcoder"
echo "sudo rm /usr/share/pixmaps/qualcoder.png"
echo "sudo rm /usr/share/applications/qualcoder.desktop"
