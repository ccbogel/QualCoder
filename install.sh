#!/bin/bash

echo "This installer is for Linux installations only"
echo "qualcoder will be copied to the directory /usr/share/"
echo "These actions require owner (sudo) permission"
echo "The installer will also install dependencies"
sudo apt install python3-pip python3-pyqt5 python3-lxml python3-pil vlc qpdf python3-ebooklib python3-ply python3-six python3-chardet python3-click
sudo pip install pdfminer.six
sudo pip install pikepdf
# sudo apt install libavcodec-extra  # for streaming and transcoding
sudo cp -r qualcoder /usr/share/qualcoder
sudo cp qualcoder.png /usr/share/pixmaps/qualcoder.png
sudo cp qualcoder.desktop /usr/share/applications/qualcoder.desktop
echo "Installation completed."
echo "To remove qualcoder from Linux run the following in the terminal:"
echo "sudo rm -R /usr/share/qualcoder"
echo "sudo rm /usr/share/pixmaps/qualcoder.png"
echo "sudo rm /usr/share/applications/qualcoder.desktop"
