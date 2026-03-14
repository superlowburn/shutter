#!/bin/bash
set -e

echo "=== Shutter App Builder ==="
echo ""

# Clean previous builds
rm -rf build dist *.egg-info

# Build the .app bundle
echo "Building Shutter.app..."
python setup.py py2app

echo ""
echo "Build complete: dist/Shutter.app"
echo ""
echo "To run:  open dist/Shutter.app"
echo ""

# Optionally create DMG
if [ "$1" = "--dmg" ]; then
    DMG_NAME="Shutter-0.1.0"
    echo "Creating DMG..."
    if command -v create-dmg &> /dev/null; then
        create-dmg \
            --volname "Shutter" \
            --volicon "resources/icon.icns" \
            --window-pos 200 120 \
            --window-size 600 400 \
            --icon-size 100 \
            --icon "Shutter.app" 150 200 \
            --app-drop-link 450 200 \
            "dist/${DMG_NAME}.dmg" \
            "dist/Shutter.app"
    else
        hdiutil create -volname "Shutter" \
            -srcfolder "dist/Shutter.app" \
            -ov -format UDZO \
            "dist/${DMG_NAME}.dmg"
    fi
    echo "DMG created: dist/${DMG_NAME}.dmg"
fi
