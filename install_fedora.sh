#!/bin/bash

dnf_packages="python3-pip python3-devel python3-pdfminer.noarch python3-qt5 python3-pillow python3-openpyxl python3-pandas python3-plotly python3-pip python3-pyqt6 python3-pillow vlc python3-ply python3-six python3-chardet ffmpeg"
pip_packages="Ebooklib pydub SpeechRecognition pdfminer.six python-vlc rispy xmlschema"
python_version=3.12

printf "This installer is for Fedora Linux installations using python $python_version only.\n"
printf "Change the python_version in this script to a higher numbers if you have a more recent version of python installed.\n\n"
echo "This installer uses DNF package management."
echo "QualCoder will be copied to the directory /usr/share/"
echo "These actions require owner (sudo) permission"
echo "The installer will also install dependencies"
sudo dnf install $dnf_packages -y
# several python packages are not available by Fedora, so install using Python's package installer 'pip'
echo "Please wait ..."
python3 -m pip install $pip_packages
sudo cp -r qualcoder /usr/share/qualcoder
sudo cp qualcoder/GUI/qualcoder128.png /usr/share/icons/qualcoder128.png
sudo cp qualcoder/GUI/qualcoder.desktop /usr/share/applications/qualcoder.desktop
sudo python3 setup.py install
printf "\nIf no errors then installation is completed.\n\n"
echo "To remove qualcoder from Linux run the following in the terminal:"
echo "sudo rm -R /usr/share/qualcoder"
echo "sudo rm /usr/share/icons/qualcoder128.png"
echo "sudo rm /usr/share/applications/qualcoder.desktop"
printf "\nAlso note that via dnf the subsequent packages were installed (or used): $dnf_packages.\n\n"
printf "And via python's pip these packages were installed: $pip_packages.\n\n"
echo "Consider whether you still need these packages."


