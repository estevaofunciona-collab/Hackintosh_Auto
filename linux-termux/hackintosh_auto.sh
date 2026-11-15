#!/usr/bin/env bash
# Hackintosh_Auto v0.2 (experimental) - Linux and Termux (Android)
# Thin launcher: runs hackintosh_auto.py (next to this file, or downloaded from GitHub).
# Usage:  bash hackintosh_auto.sh [--report hardware_report.txt] [--out DIR] [--skip-recovery]
set -u
RAW='https://raw.githubusercontent.com/estevaofunciona-collab/Hackintosh_Auto/main/linux-termux/hackintosh_auto.py'

IS_TERMUX=0
case "${PREFIX:-}" in *com.termux*) IS_TERMUX=1;; esac

missing=""
for cmd in curl python3; do command -v "$cmd" >/dev/null 2>&1 || missing="$missing $cmd"; done
if [ -n "$missing" ]; then
  echo "Missing required tools:$missing"
  if [ "$IS_TERMUX" = 1 ]; then echo "Install them with:  pkg install curl python"
  else echo "Install them with your package manager, e.g.:  sudo apt install curl python3"; fi
  exit 1
fi

HERE="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd)"
PY="$HERE/hackintosh_auto.py"
if [ ! -f "$PY" ]; then
  PY="$(mktemp "${TMPDIR:-/tmp}/hackintosh_auto.XXXXXX.py")"
  echo "Downloading hackintosh_auto.py ..."
  curl -fsSL -o "$PY" "$RAW" || { echo "Could not download $RAW"; exit 1; }
fi
exec python3 "$PY" "$@"
