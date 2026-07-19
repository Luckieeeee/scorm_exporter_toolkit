#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="${PYTHON:-python3}"

if [[ $# -lt 1 || $# -gt 4 ]]; then
  cat <<'USAGE'
Usage:
  ./export_scorm.sh <course.json> [prefix] [plain|styled] [output-dir]

Examples:
  ./export_scorm.sh ~/Downloads/7613293_course.json "Units_5_7" styled
  ./export_scorm.sh ./captures/unit_8_course.json "Unit_8" plain ./outputs
USAGE
  exit 2
fi

INPUT_JSON="$1"
PREFIX="${2:-}"
MODE="${3:-styled}"
OUTPUT_DIR="${4:-$SCRIPT_DIR/outputs}"

if [[ "$MODE" != "plain" && "$MODE" != "styled" ]]; then
  echo "Mode must be either 'plain' or 'styled'." >&2
  exit 2
fi

if ! "$PYTHON" -c "import reportlab" >/dev/null 2>&1; then
  echo "Missing Python dependency: reportlab" >&2
  echo "Install it with: $PYTHON -m pip install -r requirements.txt" >&2
  exit 1
fi

ARGS=(
  "$SCRIPT_DIR/export_scorm_course.py"
  --input-json "$INPUT_JSON"
  --output-dir "$OUTPUT_DIR"
  --mode "$MODE"
)

if [[ -n "$PREFIX" ]]; then
  ARGS+=(--prefix "$PREFIX")
fi

"$PYTHON" "${ARGS[@]}"
