 #!/bin/bash

echo "This installer is for Fedora Linux installations using python 3.9 only."
echo "Change 3.9 in this script to higher numbers if you have a more recent version of python installed."
echo "This installer uses DNF package management."
echo "QualCoder will be copied to the directory /usr/share/"
echo "These actions require owner (sudo) permission"
echo "The installer will also install dependencies"
sudo dnf install python3-devel python3-pip python3-pyqt5 python3-lxml python3-pil vlc python3-ply python3-six python3-chardet -y
# python3-ebooklib is not available in Fedora, so install using pip
echo "Please wait ..."
python3 -m pip install --user pdfminer.six openpyxl Ebooklib pydub SpeechRecognition
sudo mv ~/.local/lib/python3.10/site-packages/Ebook* /usr/lib/python3.10/site-packages/
sudo mv ~/.local/lib/python3.10/site-packages/ebook* /usr/lib/python3.10/site-packages/
sudo cp -r qualcoder /usr/share/qualcoder
sudo cp qualcoder/GUI/qualcoder.png /usr/share/icons/qualcoder.png
sudo cp qualcoder/GUI/qualcoder.desktop /usr/share/applications/qualcoder.desktop
sudo python3 setup.py install
echo "If no errors then installation is completed."
echo "To remove qualcoder from Linux run the following in the terminal:"
echo "sudo rm -R /usr/share/qualcoder"
echo "sudo rm /usr/share/icons/qualcoder.png"
echo "sudo rm /usr/share/applications/qualcoder.desktop"
