#!/bin/bash

echo "This installer is for Linux installations only"
echo "qualcoder will be copied to the directory /usr/share/"
echo "These actions require owner (sudo) permission"
echo "The installer will also install dependencies"
sudo apt install python3-pyqt5 python3-lxml python3-pil vlc qtwayland5 qpdf
# sudo apt install libavcodec-extra  # for streaming and transcoding
sudo cp -r qualcoder /usr/share/qualcoder
sudo cp qualcoder/GUI/QualCoder.png /usr/share/pixmaps/QualCoder.png
sudo cp qualcoder.desktop /usr/share/applications/qualcoder.desktop
echo "Installation completed."
echo "To remove qualcoder from Linux run the following in the terminal:"
echo "sudo rm -R /usr/share/qualcoder"
echo "sudo rm /usr/share/pixmaps/QualCoder.png"
echo "sudo rm /usr/share/applications/qualcoder.desktop"
