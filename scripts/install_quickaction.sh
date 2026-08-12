#!/usr/bin/env bash
# install_quickaction.sh — install "Dewatermark Text" macOS Quick Action
#
# Right-click any selected text → Quick Actions → "Dewatermark Text"
# Runs the Python dewatermark tool, replaces selected text with cleaned output.
#
# Usage:
#   ./install_quickaction.sh          # install
#   ./install_quickaction.sh uninstall # remove

set -euo pipefail

ACTION_NAME="Dewatermark Text"
WORKFLOW_DIR="$HOME/Library/Services"
WORKFLOW_FILE="$WORKFLOW_DIR/Dewatermark Text.workflow"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"

# Try to find the hermes venv python where dewatermark is installed,
# fall back to system python3
if [ -x "$HOME/.hermes/hermes-agent/venv/bin/python3" ]; then
  PYTHON_BIN="$HOME/.hermes/hermes-agent/venv/bin/python3"
fi

if [ "${1:-}" = "uninstall" ]; then
  echo "Removing '$ACTION_NAME' Quick Action..."
  rm -rf "$WORKFLOW_FILE"
  echo "Done."
  exit 0
fi

echo "Installing '$ACTION_NAME' Quick Action..."
echo "  Python: $PYTHON_BIN"

# Verify dewatermark is available
if ! "$PYTHON_BIN" -c "import dewatermark" 2>/dev/null; then
  echo "  WARNING: dewatermark package not found in $PYTHON_BIN"
  echo "  Install it first: pip install git+https://github.com/deand28/dewatermark-py.git"
  echo "  Or set PYTHON_BIN to a python that has it."
  echo "  Continuing anyway (workflow will fail at runtime without it)..."
fi

# Build the Automator workflow as a .workflow bundle
mkdir -p "$WORKFLOW_FILE/Contents"

# Info.plist — workflow metadata
cat > "$WORKFLOW_FILE/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>NSServices</key>
  <array>
    <dict>
      <key>NSBackgroundColorName</key>
      <string>background</string>
      <key>NSIconName</key>
      <string>NSTouchBarComposeTemplate</string>
      <key>NSMenuItem</key>
      <dict>
        <key>default</key>
        <string>Dewatermark Text</string>
      </dict>
      <key>NSMessage</key>
      <string>runWorkflowWithInput</string>
      <key>NSReturnTypes</key>
      <array>
        <string>public.utf8-plain-text</string>
      </array>
      <key>NSSendTypes</key>
      <array>
        <string>public.utf8-plain-text</string>
      </array>
    </dict>
  </array>
</dict>
</plist>
PLIST

# document.wflow — the actual Automator workflow definition
# Uses "Run Shell Script" action that pipes selected text through dewatermark
cat > "$WORKFLOW_FILE/Contents/document.wflow" <<'WFLOW'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>AMApplicationBuild</key>
  <string>535</string>
  <key>AMApplicationVersion</key>
  <string>2.10</string>
  <key>AMDocumentVersion</key>
  <string>2</string>
  <key>actions</key>
  <array>
    <dict>
      <key>action</key>
      <dict>
        <key>AMAccepts</key>
        <dict>
          <key>Container</key>
          <string>System</string>
          <key>Types</key>
          <array>
            <string>public.utf8-plain-text</string>
          </array>
        </dict>
        <key>AMActionVersion</key>
        <string>2.0.3</string>
        <key>AMApplication</key>
        <array>
          <string>Automator</string>
        </array>
        <key>AMParameterProperties</key>
        <dict>
          <key>COMMAND_STRING</key>
          <dict>
            <key>isPathPopUp</key>
            <false/>
          </dict>
          <key>CheckedForUserDefaultShell</key>
          <dict/>
          <key>TrimNewLine</key>
          <dict/>
          <key>UseNamedPipe</key>
          <dict/>
          <key>inputAsArgument</key>
          <dict/>
          <key>shell</key>
          <dict/>
        </dict>
        <key>AMProvides</key>
        <dict>
          <key>Container</key>
          <string>System</string>
          <key>Types</key>
          <array>
            <string>public.utf8-plain-text</string>
          </array>
        </dict>
        <key>ActionBundlePath</key>
        <string>/System/Library/Automator/Run Shell Script.action</string>
        <key>ActionName</key>
        <string>Run Shell Script</string>
        <key>ActionParameters</key>
        <dict>
          <key>COMMAND_STRING</key>
          <string>PYTHON_BIN="$HOME/.hermes/hermes-agent/venv/bin/python3"
if [ ! -x "$PYTHON_BIN" ]; then PYTHON_BIN="python3"; fi
echo "$1" | "$PYTHON_BIN" -m dewatermark -q 2>/dev/null || echo "$1"</string>
          <key>CheckedForUserDefaultShell</key>
          <true/>
          <key>TrimNewLine</key>
          <true/>
          <key>UseNamedPipe</key>
          <false/>
          <key>inputAsArgument</key>
          <true/>
          <key>shell</key>
          <string>/bin/bash</string>
        </dict>
        <key>BundleIdentifier</key>
        <string>com.apple.RunShellScript</string>
        <key>CFBundleVersion</key>
        <string>2.0.3</string>
        <key>CanShowSelectedItemsWhenRun</key>
        <false/>
        <key>CanShowWhenRun</key>
        <true/>
        <key>Category</key>
        <array>
          <string>AMCategoryUtilities</string>
        </array>
        <key>Class Name</key>
        <string>RunShellScriptAction</string>
        <key>InputUUID</key>
        <string>A8B7C6D5-E4F3-4A2B-8C1D-0E9F8A7B6C5D</string>
        <key>Keywords</key>
        <array>
          <string>Shell</string>
          <string>Script</string>
          <string>Command</string>
          <string>Run</string>
        </array>
        <key>OutputUUID</key>
        <string>B9C8D7E6-F5A4-4B3C-9D2E-1F0A9B8C7D6E</string>
        <key>UUID</key>
        <string>C0D9E8F7-A6B5-4C4D-AE3F-2A1B0C9D8E7F</string>
        <key>UnspecifiedApplications</key>
        <false/>
      </dict>
    </dict>
  </array>
  <key>connectors</key>
  <dict/>
  <key>workflowMetaData</key>
  <dict>
    <key>applicationBundleIDsByPath</key>
    <dict/>
    <key>applicationPaths</key>
    <array/>
    <key>inputTypeIdentifier</key>
    <string>com.apple.Automator.text</string>
    <key>outputTypeIdentifier</key>
    <string>com.apple.Automator.text</string>
    <key>presentationMode</key>
    <integer>0</integer>
    <key>processesInput</key>
    <integer>0</integer>
    <key>serviceApplicationPath</key>
    <string>/Applications/Automator.app</string>
    <key>serviceInputTypeIdentifier</key>
    <string>public.utf8-plain-text</string>
    <key>serviceOutputTypeIdentifier</key>
    <string>public.utf8-plain-text</string>
    <key>shouldUseRunningApplication</key>
    <integer>0</integer>
    <key>workflowTypeIdentifier</key>
    <string>com.apple.Automator.servicesMenu</string>
  </dict>
</dict>
</plist>
WFLOW

echo "  Installed to: $WORKFLOW_FILE"
echo ""
echo "Done. Right-click selected text → Quick Actions → '$ACTION_NAME'"
echo "Or assign a keyboard shortcut in:"
echo "  System Settings → Keyboard → Keyboard Shortcuts → Services"
echo ""
echo "To uninstall: $0 uninstall"
