#!/bin/bash

echo "QualCoder will be copied to the directory /usr/share/"
echo "These actions require owner (sudo) permission"

sudo cp -r QualCoder /usr/share/QualCoder
sudo cp QualCoder/GUI/QualCoder.png /usr/share/pixmaps/QualCoder.png
sudo cp QualCoder.desktop /usr/share/applications/QualCoder.desktop

echo "Installation completed."
echo "You may need to install pyqt5."
echo "On Linux:"
echo "sudo pip3 install pyqt5"
echo "On Windows:"
echo "pip install pyqt5"
echo "To remove QualCoder from Linux run the following in the terminal:"
echo "sudo rm -R /usr/share/QualCoder"
echo "sudo rm /usr/share/pixmaps/QualCoder.png"
