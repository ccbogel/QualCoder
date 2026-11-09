#!/usr/bin/bash
# set -e

if [ -z "$1" ]; then
    echo "Usage: $0 <version> (ex: 4.0.0)"
    exit 1
fi

VERSION="$1"

if [ -d dist ] && [ -d .venv ] && [ -n "$(ls -A dist 2>/dev/null)" ]; then
    echo Binary exist
else
    echo Compile QualCoder
    # Compile QualCoder
    python3 -m venv .venv
    source .venv/bin/activate
    python3 -m pip install --upgrade pip
    pip install -r requirements.txt
    # For the AppImage, using the "folder" spec results in a faster binary
    pyinstaller --clean --noconfirm "qualcoder.spec"
    deactivate
fi

# App Image Structure
rm -rf QualCoder-x86_64.AppDir #if some artifacts exist for some reason
mkdir -p QualCoder-x86_64.AppDir/usr/bin
cp -r dev/qualcoder-appimage/. QualCoder-x86_64.AppDir/
chmod +x QualCoder-x86_64.AppDir/AppRun
cp qualcoder.png QualCoder-x86_64.AppDir/
cp -r dist/QualCoder/. QualCoder-x86_64.AppDir/usr/bin/

# Desktop File
mkdir -p QualCoder-x86_64.AppDir/usr/share/applications
cat << EOF > QualCoder-x86_64.AppDir/usr/share/applications/io.github.ccbogel.qualcoder.desktop
[Desktop Entry]
Name=QualCoder
GenericName=QualCoder
Icon=qualcoder
Comment=Qualitative data analysis for text, images, audio, video.
Exec=qualcoder %F
Terminal=false
Type=Application
Categories=Science;Education;
StartupWMClass=QualCoder
EOF
cp QualCoder-x86_64.AppDir/usr/share/applications/io.github.ccbogel.qualcoder.desktop QualCoder-x86_64.AppDir/

#Tools
wget -q https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage -O /tmp/appimagetool
chmod +x /tmp/appimagetool

#App Image Gen
ARCH=x86_64 /tmp/appimagetool --appimage-extract-and-run QualCoder-x86_64.AppDir QualCoder-x86_64.AppImage

[[ -f QualCoder-x86_64.AppImage ]] && mv QualCoder-x86_64.AppImage "QualCoder-${VERSION}-x86_64.AppImage"

echo Done!