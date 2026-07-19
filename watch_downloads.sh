#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="${PYTHON:-python3}"

if ! "$PYTHON" -c "import reportlab" >/dev/null 2>&1; then
  echo "Missing Python dependency: reportlab" >&2
  echo "Install it with: $PYTHON -m pip install -r requirements.txt" >&2
  exit 1
fi

"$PYTHON" "$SCRIPT_DIR/watch_downloads.py" "$@"
