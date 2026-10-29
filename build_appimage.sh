#!/usr/bin/bash
# set -e

if [ -z $1 ]; then
    echo "Usage: $0 <version> (ex: 3.8.3) <onefile or not> (empty = binary + artifactes; 1 = one file binary)"
    exit 1
fi

VERSION="$1"
TYPE="$2"

COMPLEMENT=""

[[ "$TYPE" -eq 1 ]] && COMPLEMENT="_onefile"

if [ -d dist ]; then
    echo Binary exist
else
    echo Compile QualCoder
    # Compile QualCoder
    python3 -m venv .env
    source .env/bin/activate
    python3 -m pip install --upgrade pip
    pip install -r requirements.txt
    pyinstaller --clear --no-confirm "qualcoder_${COMPLEMENT}release.spec"
    deactivate
fi

# App Image Structure
rm -rf QualCoder-x86_64.AppDir
mkdir -p QualCoder-x86_64.AppDir/usr/bin
cp dev/qualcoder-appimage/AppRun QualCoder-x86_64.AppDir/
chmod +x QualCoder-x86_64.AppDir/AppRun
cp qualcoder.png QualCoder-x86_64.AppDir/.AppDir/
cp -r dist/QualCoder/. QualCoder-x86_64.AppDir/.AppDir/usr/bin/

# Desktop File
cat << EOF > QualCoder-x86_64.AppDir/QualCoder.desktop
[Desktop Entry]
Name=QualCoder
GenericName=QualCoder
Icon=qualcoder
Comment=Qualitative data analysis for text, images, audio, video.
Exec=/usr/bin/QualCoder
Terminal=false
Type=Application
Categories=Science;Education;
StartupWMClass=QualCoder
EOF

#Tools
wget -q https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage -O /tmp/appimagetool
chmod +x /tmp/appimagetool

#App Image Gen
ARCH=x86_64 /tmp/appimagetool --appimage-extract-and-run QualCoder-x86_64.AppDir QualCoder-x86_64.AppImage

[[ -f QualCoder-x86_64.AppImage ]] && mv QualCoder-x86_64.AppImage "QualCoder-${VERSION}-x86_64.AppImage"

echo Done!