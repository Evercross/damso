#!/bin/bash
# Damso (담소) - Run Script
# Usage: ./run.sh          (foreground)
#        ./run.sh &         (background)
#        ./run.sh --settings (settings window only)

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

if [ ! -d "$SCRIPT_DIR/.venv" ]; then
    echo "먼저 setup.sh를 실행해주세요:"
    echo "  bash $SCRIPT_DIR/setup.sh"
    exit 1
fi

source "$SCRIPT_DIR/.venv/bin/activate"
cd "$SCRIPT_DIR"
python app.py "$@"
