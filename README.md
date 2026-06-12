# Damso (담소) 🎤

**타이핑은 그만. 말로 하세요.**

담소는 macOS 메뉴바에 상주하는 **완전 로컬** 음성 입력 앱입니다.
키를 누르고 말한 뒤 놓으면, 지금 커서가 있는 곳에 텍스트가 바로 입력됩니다.
음성은 한 글자도 외부로 나가지 않습니다 — 모든 인식이 내 맥 안에서 끝납니다.

> 카톡 답장, 슬랙 메시지, 메모, 그리고 Claude Code·Codex 같은 AI 코딩 도구에 프롬프트를 "말로" 넣는 용도에 최적화되어 있습니다.

<!-- TODO: 데모 GIF (Right Option 누르고 말하기 → 텍스트 삽입) -->

## 왜 담소인가

- **🔒 완전 오프라인** — Qwen3-ASR이 Apple Silicon GPU(MLX)에서 직접 돌아갑니다. 서버 없음, 구독 없음, 녹음 유출 없음.
- **🇰🇷 한국어 우선** — 한국어 인식 품질 기준으로 엔진을 골랐고, 한/영/일 혼용 발화도 처리합니다.
- **⚡ 빠름** — 7초 발화 기준 약 3초 내 변환 (M 시리즈 기준).
- **📖 용어 사전** — "깃허브→GitHub", "리액트→React" 같은 치환 규칙 내장 + 직접 추가 가능. 전문용어가 뭉개지지 않습니다.
- **🖱️ 손에 맞는 핫키** — Right Option, Fn(🌐), 심지어 **마우스 사이드 버튼**으로도 hold-to-speak.

## 요구 사항

| 항목 | 요구 |
|------|------|
| macOS | Apple Silicon (M1 이상) 권장 — 기본 엔진(MLX)이 GPU 사용 |
| Python | 3.12+ (Homebrew `brew install python3`) |
| 디스크 | 모델 약 4GB (첫 실행 시 자동 다운로드) |
| Intel Mac | Whisper CPU 폴백으로 동작 가능 (느림) |

## 설치 (3분)

```bash
git clone https://github.com/Evercross/damso.git
cd damso
bash setup.sh
```

설치가 끝나면 실행:

```bash
bash run.sh
```

첫 실행 시 STT 모델(약 4GB)을 자동 다운로드합니다. 메뉴바에 🎤 아이콘이 뜨면 준비 완료.

### macOS 권한 설정 (필수, 처음 한 번)

담소는 터미널을 통해 실행되므로, **사용하는 터미널 앱**(Terminal, iTerm2 등)에 권한을 줍니다:

1. **마이크** — 시스템 설정 → 개인정보 보호 및 보안 → 마이크 → 터미널 ✅
2. **손쉬운 사용** — 시스템 설정 → 개인정보 보호 및 보안 → 손쉬운 사용 → 터미널 ✅
   (글로벌 핫키 감지와 텍스트 삽입에 필요)

권한을 준 뒤 **앱을 재시작**하세요. 메뉴바 → `권한 점검`으로 상태를 확인할 수 있습니다.

## 사용법

| 단축키 | 동작 |
|--------|------|
| **Right Option(⌥)** 누르고 말하기 | 놓으면 입력 (권장) |
| **Fn(🌐)** 누르고 말하기 | 놓으면 입력 |
| **마우스 사이드 버튼** 누르고 말하기 | 놓으면 입력 |
| **Ctrl+Shift+M** | 토글 모드 (시작/중지) |

메뉴바 아이콘 색으로 상태를 알 수 있습니다: 대기 → 🔴 녹음 중 → ⏳ 변환 중.

### 용어 사전

`~/.damso/dictionary.json` 또는 설정 UI에서 관리합니다. 개발 용어 프리셋이 기본 포함되어 있고, 자주 오인식되는 단어를 등록하면 입력 직전에 자동 치환됩니다.

### 설정

메뉴바 → Settings, 또는 `~/.damso/config.json` 직접 편집:

```json
{
  "stt_engine": "qwen3-asr",
  "language": "ko",
  "hotkey_hold": "right_option",
  "history_retention_days": 30,
  "show_notification": false
}
```

## 문제 해결 (FAQ)

**핫키가 안 먹어요 / 텍스트가 입력 안 돼요**
→ 90%는 손쉬운 사용 권한 문제입니다. 시스템 설정에서 터미널 앱이 켜져 있는지 확인하고, 한 번 껐다 켠 뒤 담소를 재시작하세요. 메뉴바 → `진단 리포트 생성`으로 상태를 확인할 수 있습니다.

**인식이 이상해요**
→ 메뉴바 → 입력 장치에서 마이크가 올바른지 확인하세요. 특정 단어가 계속 틀리면 용어 사전에 등록하는 게 가장 빠릅니다.

**로그는 어디 있나요**
→ `~/.damso/damso.log`. 문제 신고 시 `진단 리포트 생성` 결과(`~/.damso/diagnostics/`)를 함께 보내주세요.

**완전 삭제하려면**
→ 클론한 폴더 삭제 + `rm -rf ~/.damso` + (모델까지) `~/.cache/huggingface/hub`에서 Qwen3-ASR 폴더 삭제.

## 기술 스택

Python · [mlx-qwen3-asr](https://github.com/mlx-community) (Qwen3-ASR, Apple Silicon MLX) · faster-whisper (폴백) · rumps (메뉴바) · Quartz CGEvent (핫키/삽입) · pywebview (설정 UI) · SQLite (히스토리)

## 로드맵

자동 언어 감지, 사운드 피드백, 히스토리 재삽입 → 다듬기 모드(구어체를 정돈된 문장으로), 내 목소리만 받아쓰기.
상세: [docs/plans/2026-06-12-damso-deployment-roadmap.md](docs/plans/2026-06-12-damso-deployment-roadmap.md)

---

문제가 생기면 이슈로 남겨주세요. 진단 리포트와 함께면 더 빨리 고칩니다. 🙏
