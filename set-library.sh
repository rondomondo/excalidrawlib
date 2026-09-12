#!/usr/bin/env bash
set -euo pipefail

VS_CODE_USER="${VS_CODE_USER:-$USER}"
SETTINGS_FILE="${SETTINGS_FILE:-/Users/$VS_CODE_USER/Library/Application Support/Code/User/settings.json}"

usage() {
    cat >&2 <<EOF
$(basename "$0") -- Switch the active Excalidraw workspace library in VS Code

How it works:
  1. Excalidraw libraries can be exported to a .excalidrawlib file on disk.
  2. The Excalidraw VS Code extension setting 'excalidraw.workspaceLibraryPath'
     points to one of those files as the active library.
  3. Updating this setting has the same effect as clicking "Load library" in
     the Excalidraw UI -- the library is loaded into the sidebar immediately.
  4. By swapping the value you can dynamically switch which personal library
     is active without touching the UI.

Usage:
  $(basename "$0") <library-name>

  <library-name>  The base name (without extension) of the .excalidrawlib file to
                  set as the active library, e.g. 'dave' or 'work'
                  The '.excalidrawlib' extension is appended automatically.

Environment:
  VS_CODE_USER    OS username whose VS Code settings to update (default: \$USER -> $USER)
  SETTINGS_FILE   Full path to settings.json (default: /Users/<VS_CODE_USER>/Library/Application Support/Code/User/settings.json)

Examples:
  $(basename "$0") dave          # sets library to dave.excalidrawlib
  VS_CODE_USER=alice $(basename "$0") shared
  SETTINGS_FILE=/tmp/test-settings.json $(basename "$0") mylib
EOF
    exit 1
}

[[ $# -ne 1 ]] && usage
[[ "$1" == "-h" || "$1" == "--help" ]] && usage

word="${1%.excalidrawlib}.excalidrawlib"

if [[ -z "$word" ]]; then
    echo "Error: argument cannot be empty" >&2
    exit 1
fi

if [[ ! -f "$SETTINGS_FILE" ]]; then
    echo "Error: settings file not found: $SETTINGS_FILE" >&2
    exit 1
fi

# Validate word contains no path traversal or shell-unsafe characters

if [[ "$word" =~ [^a-zA-Z0-9._/-] ]]; then
    echo "Error: argument contains invalid characters (allowed: a-z A-Z 0-9 . _ / -)" >&2
    exit 1
fi

# Use python3 to safely parse and update JSON
python3 - "$SETTINGS_FILE" "$word" <<'PYEOF'
import json
import sys
import os

settings_file = sys.argv[1]
new_value = sys.argv[2]

with open(settings_file, 'r') as f:
    content = f.read()

# Parse with trailing-comma tolerance via a simple pre-process isn't trivial;
# use raw string replacement to preserve formatting and comments
import re

pattern = r'("excalidraw\.workspaceLibraryPath"\s*:\s*)"[^"]*"'
replacement = r'\g<1>"' + new_value + '"'

new_content, count = re.subn(pattern, replacement, content)

if count == 0:
    print("Error: 'excalidraw.workspaceLibraryPath' key not found in settings.json", file=sys.stderr)
    sys.exit(1)

# Write atomically
tmp = settings_file + '.tmp'
with open(tmp, 'w') as f:
    f.write(new_content)
os.replace(tmp, settings_file)

print(f"Updated excalidraw.workspaceLibraryPath -> \"{new_value}\"")
PYEOF
