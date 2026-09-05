#!/bin/env bash
# Make this script executable
# Run it by typing inside the Qualcoder folder: ./run_from_source_Linux.sh
# Works on Ubuntu 26 and Fedora 44 

# This version is almost identitical to the changes proposed to "run_from_source_linux.sh", the difference is (appart of
# some minor wirting discrepancies) the addition off a tiny helper script that converts the XPM into PNG just if Wayland 
# missbehaves with that format (I read it may do that). The scriptlet is deleted after is job is done

# This simple helper that adds the icons, .desktop, and helper initalization 
# script to their designed places in ~/.local
#
# betor, 2026 (beto.rebonatto.neto@gmail.com)

#Created the procedure I added as a function in order to better separate my contributions from the install script
add_desktop_and_icon_files_to_the_correct_places_without_sudoing(){
    #This function automatically adds the icon to the correct and valid "dot folders" at Home. The structure is almosts equal to /usr used in .deb pcakges
    #That means that it is really easy to do the necessary changes when converting
    #Variables
    SCRIPT_DIR="$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" #Assigns the path of the directory of the script (aka repo root) so qualcoder knows that this script's directorys is where everything is
    #Assigns the path of the directory of the script (aka repo root) so qualcoder knows that this script's directorys is where everything is
    DOT_LOCAL_SHARE="$HOME/.local/share"
    APPS_DIR="$DOT_LOCAL_SHARE/applications"
    ICON_DIR="$DOT_LOCAL_SHARE/icons"
    BIN_DIR="$HOME/.local/bin"
    #Took this approach (using /home/user/.local directories) because you can port this script to a deb pkg since the folder structure just changes $HOME to /usr

    check_dir(){ #This fucntion is gigantic because this is one of the shortest way to check dirs while echoing different strings
        local dir="$1"
        if [ ! -d "$dir" ]; then
            case $dir in
                "$APPS_DIR")
                    echo ".desktops file's directory ($dir) does not exist. Trying to create...";;
                "$ICON_DIR")
                    echo "Icon's directory ($dir) does not exist. Trying to create...";;
                "$BIN_DIR")
                    echo "Binaries's directory ($dir) does not exist. Trying to create...";;
                *) 
                    echo "UNRECOGNIZED PATTERN"
            esac
            if ! mkdir -p "$dir"; then
                echo "Failed to create $dir. Support for .desktop will not work. Please set it up manually"
                return 1
            fi
        fi
        case $dir in
            "$APPS_DIR")
                echo ".desktops file's directory ($dir) exists.";;
            "$ICON_DIR")
                echo "Icon's directory ($dir) exists.";;
            "$BIN_DIR")
                echo "Binaries's directory ($dir) exists.";;
            *) 
                echo "UNRECOGNIZED PATTERN" 
        esac
        return 0
    }

    # Icon copy
    if check_dir "$ICON_DIR"; then
        if [ "$XDG_SESSION_TYPE" = "wayland" ]; then
            echo "XDG_SESSION_TYPE is \"wayland\" converting the XPM icon file to PNG"
            EXT=".png"
            touch "$SCRIPT_DIR/tmp_xmp_to_png.py" # creates a small python handler to convert to png because wayland does not handle xpm files well
            cat > "$SCRIPT_DIR/tmp_xmp_to_png.py" << EOF
from PIL import Image
import os
script_dir=os.path.abspath(os.path.dirname(__file__))
xmp=os.path.join(f"{script_dir}","qualcoder-debian/usr/share/icons/qualcoder.xpm")
png=os.path.join(os.environ["HOME"],".local/share/icons/qualcoder.png")
im=Image.open(xmp)
im.save(png)
EOF
        "$SCRIPT_DIR/.env/bin/python" "$SCRIPT_DIR/tmp_xmp_to_png.py" #calls the .env python directly
        rm "$SCRIPT_DIR/tmp_xmp_to_png.py" # deletes the helper
        elif [ "$XDG_SESSION_TYPE" = "x11" ]; then
            echo "XDG_SESSION_TYPE is \"x11\" copying XPM icon..."
            EXT=".xpm"
            if ! cp "$SCRIPT_DIR/qualcoder-debian/usr/share/icons/qualcoder.xpm" "$ICON_DIR/"; then
                echo "Failed to copy icon file correctly it'll not be displayed."
            fi
        else
            echo "Unknown or no graphical session"
        fi  
    fi
    # .desktop generation -> it is better to automatically generate the .desktop file via bash in order to better ensure the expansion of default env variables
    if check_dir "$APPS_DIR"; then
        if ! touch "$APPS_DIR/QualCoder.desktop"; then
            echo "Failed to create desktop file correctly icon support will not work."
        else
            cat > "$APPS_DIR/QualCoder.desktop" << EOF
[Desktop Entry]
Name=QualCoder
GenericName=qualcoder
Icon=$ICON_DIR/qualcoder$EXT
Comment=Qualitative data analysis for text, images, audio, video.
#Needs to change in .deb pkgs
Exec=$BIN_DIR/run-qualcoder

# Should this app run in terminal ?
Terminal=false

Type=Application
Categories=Science;Education;
StartupWMClass=QualCoder
EOF
            echo "\"QualCoder.desktop\" was sucessgully created at $APPS_DIR"
        fi
    fi
    # run-qualcoder scriplet generation 
    #This script makes easier to test Qualcoder/call it from the terminal because you can just go to your teminal and "qualcoder" this may be taken off for the deb pkg version because it'll compile the code and put the qualcoder binary inside /usr/bin
    if check_dir "$BIN_DIR"; then
        if ! touch "$BIN_DIR/run-qualcoder"; then
            echo "Failed to create run-qualcoder file. Please do it manually"
        else
            cat > "$BIN_DIR/run-qualcoder" << EOF
#!/bin/env bash
# This simple helper script goes to where the Source code is located (assigned
# during script generation, but easily modifiable by changing the variable
# \$SCRIPT_DIR), activates the Python Virtual Enviroment and runs the programm,
# and exits smoothly, by deactivating the venv.
#
# betor, 2026 (beto.rebonatto.neto@gmail.com)
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
# backup
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
#
# https://github.com/ccbogel/QualCoder
# https://qualcoder.wordpress.com/
# https://qualcoder.org/

\$SCRIPT_DIR="$SCRIPT_DIR"

cd "\$SCRIPT_DIR"
source .env/bin/activate

# Move to src folder to then run qualcoder module
echo "Starting QualCoder."
cd "\$SCRIPT_DIR/src"
python3 -m qualcoder

# Exit environment
cd ../
deactivate
echo "Exiting virtual environment."
EOF
        echo "\"$BIN_DIR/run-qualcoder\" was sucessgully created at $BIN_DIR"
        chmod +x "$BIN_DIR/run-qualcoder" 
        fi
        # This Approach allow for users who want the latest bugfixes and testing feature to call qualcoder easily for testing
        # while keeping the binary files and the string "qualcoder" free for .deb or the binary (if the user puts in there) 
        if [ -e "$HOME/.bash_aliases" ]; then
            ALIAS=$(cat "$HOME/.bash_aliases" | grep "qualcoder=\"run-qualcoder\"") 
            #checks if the alias already exists to avoid duplicated entries
            if [ -z "$ALIAS" ]; then
                echo "Assigning \"qualcoder\" as an alias to allow for CLI call"
                echo "qualcoder=\"run-qualcoder\"" >> "$HOME/.bash_aliases"
            else
                echo "Alias already exists"
            fi
        else
            echo "You do not have a .bash_aliases in your home folder"
            echo "Please create one if you use BaSH. Just \"touch ~/.bash_aliases\""
            echo "If you dont use BaSH regularly, please add an alias called \"qualcoder\" that points to \"$BIN_DIR/run-qualcoder\"" 
            # If a person is not using bash on linux they probably know what they're doing
        fi
    fi
return 0
}


echo "Starting"
# Create venv
if [ -d ".env" ]; then
    echo "Virtual environment exists."
else
    echo "Creating virtual environment."
    python3 -m venv ".env"
fi

# Activate environment
source .env/bin/activate

# Install required modules
echo "Installing requirements. This may take 10 minutes."
python3 -m pip install --upgrade pip
pip install -r requirements.txt

#Calls the function, but the interal code can be put in here
add_desktop_and_icon_files_to_the_correct_places_without_sudoing

# Move to src folder to then run qualcoder module
echo "Starting QualCoder."
cd "$SCRIPT_DIR/src"
python3 -m qualcoder

# Exit environment
cd ../
deactivate
echo "Exiting virtual environment."