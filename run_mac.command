#!/usr/bin/env bash
set -euo pipefail

# Launch YouTube subtitle tool on macOS.
# Assumes Python 3 and dependencies are already installed.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if ! command -v python3 >/dev/null 2>&1; then
  echo "[ERROR] python3 not found. Please install Python 3."
  exit 1
fi

python3 "$SCRIPT_DIR/youtube_subtitle_tool.py"
