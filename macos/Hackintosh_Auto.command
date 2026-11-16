#!/bin/bash
# Hackintosh_Auto v0.2 (experimental) - macOS launcher. Double-click this file in Finder.
# (First time: right-click -> Open, because macOS blocks files downloaded from the internet.)
# It runs hackintosh_auto.py (next to this file, or downloaded from GitHub).
RAW='https://raw.githubusercontent.com/estevaofunciona-collab/Hackintosh_Auto/main/linux-termux/hackintosh_auto.py'
clear
echo "Hackintosh_Auto - macOS"
echo

if ! command -v python3 >/dev/null 2>&1 || ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)' 2>/dev/null; then
  echo "Python 3.8 or newer is needed and was not found."
  echo "Install it with ONE of these, then double-click this file again:"
  echo "  - run in Terminal:  xcode-select --install     (Apple's command line tools, includes Python 3)"
  echo "  - or download from https://www.python.org/downloads/macos/"
  echo
  read -r -p "Press Enter to close..." _
  exit 1
fi
if ! command -v curl >/dev/null 2>&1; then
  echo "curl was not found (it ships with macOS - something is wrong with this Mac)."
  read -r -p "Press Enter to close..." _
  exit 1
fi

HERE="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd)"
PY="$HERE/hackintosh_auto.py"
if [ ! -f "$PY" ]; then
  PY="$(mktemp "${TMPDIR:-/tmp}/hackintosh_auto.XXXXXX")"
  echo "Downloading hackintosh_auto.py ..."
  curl -fsSL -o "$PY" "$RAW" || { echo "Could not download $RAW"; read -r -p "Press Enter to close..." _; exit 1; }
fi
python3 "$PY" "$@"
echo
read -r -p "Press Enter to close..." _
