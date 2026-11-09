#!/usr/bin/bash
set -euo pipefail

if [ -z "${1:-}" ]; then
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
install -d -m 755 QualCoder-x86_64.AppDir/
cp -a dist/QualCoder/. QualCoder-x86_64.AppDir/

install -D -m 755 dev/qualcoder-appimage/AppRun \
 QualCoder-x86_64.AppDir/AppRun

install -D -m 644 dev/qualcoder-appimage/usr/share/metainfo/io.github.ccbogel.qualcoder.appdata.xml \
 QualCoder-x86_64.AppDir/usr/share/metainfo/io.github.ccbogel.qualcoder.appdata.xml

install -D -m 644 qualcoder.png \
 QualCoder-x86_64.AppDir/qualcoder.png

# Desktop File
install -D -m 644 /dev/stdin \
    QualCoder-x86_64.AppDir/usr/share/applications/io.github.ccbogel.qualcoder.desktop << 'EOF'
[Desktop Entry]
Name=QualCoder
GenericName=QualCoder
Icon=qualcoder
Comment=Qualitative data analysis for text, images, audio, video.
Exec=QualCoder %F
Terminal=false
Type=Application
Categories=Science;
StartupWMClass=QualCoder
EOF

install -m 644 QualCoder-x86_64.AppDir/usr/share/applications/io.github.ccbogel.qualcoder.desktop \
    QualCoder-x86_64.AppDir/io.github.ccbogel.qualcoder.desktop

#Tools
TOOL=/tmp/appimagetool
if [ ! -x "$TOOL" ]; then
    wget -q -O "$TOOL" https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage
    chmod +x "$TOOL"
fi

#App Image Gen
ARCH=x86_64 /tmp/appimagetool --appimage-extract-and-run QualCoder-x86_64.AppDir QualCoder-x86_64.AppImage

if [ ! -f QualCoder-x86_64.AppImage ]; then
    echo "ERROR: AppImage was not produced" >&2
    exit 1
fi

mv QualCoder-x86_64.AppImage "QualCoder-${VERSION}-x86_64.AppImage"

echo Done!