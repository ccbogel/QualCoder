#!/bin/bash
# sudo aptitude install dpkg-dev fakeroot upx-ucl
# set -e

if [ -z "$1" ]; then
    echo "Usage: $0 <version> (ex: 3.8.3)"
    exit 1
fi

VERSION="$1"
NEW_DIR="qualcoder-${VERSION}"

# Compile QualCoder
python3 -m venv ".env"
source .env/bin/activate
python3 -m pip install --upgrade pip
pip install -r requirements.txt
pyinstaller qualcoder_onefile.spec --upx-dir=/usr/bin/upx
deactivate

#  Create .deb
echo "Copy template ${NEW_DIR}..."
cp -r "qualcoder-debian" "$NEW_DIR"

mkdir -p "${NEW_DIR}/src"
cp "dist/QualCoder" "${NEW_DIR}/src/qualcoder"
chmod +x "${NEW_DIR}/src/qualcoder"


echo "Update changelog ..."
cat > "${NEW_DIR}/debian/changelog" << EOF
qualcoder (${VERSION}) UNRELEASED; urgency=medium

  * New upstream release ${VERSION}.
  * See https://github.com/ccbogel/QualCoder/releases/tag/${VERSION}

 -- QualCoder Team <contact@qualcoder.org>  $(date -R)
EOF

sed -i "s/Standards-Version:.*/Standards-Version: ${VERSION}/" "${NEW_DIR}/debian/control"


echo "Build version ${VERSION}..."
cd "$NEW_DIR"
debuild -us -uc
cd ..

echo "Package released : qualcoder_${VERSION}_amd64.deb"
