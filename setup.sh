#!/bin/bash
# Damso (담소) - Setup Script
# macOS용 음성-텍스트 입력 앱

set -e

echo "================================================"
echo "  Damso (담소) - 설치 스크립트"
echo "================================================"
echo ""

# Check macOS
if [[ "$OSTYPE" != "darwin"* ]]; then
    echo "❌ 이 앱은 macOS 전용입니다."
    exit 1
fi

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3이 필요합니다. brew install python3"
    exit 1
fi

PYTHON_VER=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo "✅ Python $PYTHON_VER 감지됨"

# Create virtual environment
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"

if [ ! -d "$VENV_DIR" ]; then
    echo ""
    echo "📦 가상 환경 생성 중..."
    python3 -m venv "$VENV_DIR"
fi

# Activate venv
source "$VENV_DIR/bin/activate"

# Install dependencies
echo ""
echo "📦 의존성 설치 중..."
pip install --upgrade pip -q
pip install -r "$SCRIPT_DIR/requirements.txt" -q

echo ""
echo "✅ 설치 완료!"
echo ""
echo "================================================"
echo "  실행 전 macOS 권한 설정이 필요합니다:"
echo "================================================"
echo ""
echo "  1. 마이크 접근 권한"
echo "     시스템 설정 → 개인정보 보호 및 보안 → 마이크"
echo "     → 터미널 (또는 사용하는 터미널 앱) 허용"
echo ""
echo "  2. 손쉬운 사용(Accessibility) 권한"
echo "     시스템 설정 → 개인정보 보호 및 보안 → 손쉬운 사용"
echo "     → 터미널 (또는 사용하는 터미널 앱) 허용"
echo "     (글로벌 단축키와 텍스트 삽입에 필요)"
echo ""
echo "================================================"
echo "  실행 방법:"
echo "================================================"
echo ""
echo "  cd $SCRIPT_DIR"
echo "  source .venv/bin/activate"
echo "  python app.py"
echo ""
echo "  또는 간단히:"
echo "  $SCRIPT_DIR/run.sh"
echo ""
