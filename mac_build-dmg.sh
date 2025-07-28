#!/bin/sh
# Create a folder (named dmg) to prepare our DMG in (if it doesn't already exist).
mkdir -p dist/dmg
# Empty the dmg folder.
rm -r dist/dmg/*
# Copy the app bundle to the dmg folder.
cp -a "dist/Qualcoder.app" dist/dmg
cp -a "dist/QualCoder" dist/dmg/__main__
# If the DMG already exists, delete it.
test -f "dist/QualCoder.dmg" && rm "dist/QualCoder.dmg"
create-dmg \
  --volname "QualCoder" \
  --volicon "icons/qualcoder.icns" \
  --window-pos 200 120 \
  --window-size 600 300 \
  --icon-size 100 \
  --icon "Qualcoder.app" 175 120 \
  --hide-extension "Qualcoder.app" \
  --app-drop-link 425 120 \
  "dist/QualCoder.dmg" \
  "dist/dmg/"