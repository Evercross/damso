# Damso (담소) 🎤

**타이핑은 그만. 말로 하세요.**

Damso는 macOS 메뉴바에서 동작하는 로컬 음성-텍스트 입력 앱입니다.
Qwen3-ASR (MLX) 기반으로 Apple Silicon GPU를 활용해 초고속 오프라인 음성 인식을 제공합니다.

## 주요 기능

- **🚀 Qwen3-ASR (MLX GPU)** — Apple Silicon 최적화, 실시간 음성 인식
- **⌨️ 커서에 직접 입력** — 현재 포커스된 앱에 바로 타이핑
- **🔑 글로벌 단축키** — Right Option(권장), Fn(🌐), 마우스 사이드 버튼으로 hold-to-speak
- **📖 용어 사전** — 개발 프리셋 + 커스텀 용어 자동 치환
- **📋 히스토리** — 로컬 SQLite 저장, 보관 기간 설정
- **🌐 다국어** — 한/영/일 혼용 인식
- **📌 메뉴바 앱** — 상주형, 포커스 안 뺏김
- **🔄 듀얼 엔진** — Qwen3-ASR (기본) + Whisper (폴백) 전환 가능

## 빠른 시작

```bash
# 1. 설치
bash setup.sh

# 2. 실행
bash run.sh
```

## 단축키

| 단축키 | 동작 |
|--------|------|
| **Right Option(⌥)** 누르고 말하기 | 놓으면 텍스트 삽입 (권장) |
| **Fn(🌐)** 누르고 말하기 | 놓으면 텍스트 삽입 (hold-to-speak) |
| **마우스 사이드 버튼(앞으로)** 누르고 말하기 | 놓으면 텍스트 삽입 |
| **Ctrl+Shift+M** | 딕테이션 토글 (시작/중지) |

## macOS 권한 설정 (필수)

1. **마이크** — 시스템 설정 → 개인정보 보호 및 보안 → 마이크 → 터미널 허용
2. **손쉬운 사용** — 시스템 설정 → 개인정보 보호 및 보안 → 손쉬운 사용 → 터미널 허용

## 설정

설정 파일: `~/.damso/config.json`

```json
{
  "stt_engine": "qwen3-asr",
  "qwen_model": "Qwen/Qwen3-ASR-1.7B",
  "whisper_model": "large-v3",
  "language": "ko",
  "hotkey_hold": "right_option",
  "history_retention_days": 30,
  "insert_method": "stable",
  "show_notification": false
}
```

## STT 엔진 비교

| 엔진 | 백엔드 | 속도 | 정확도 | 추천 |
|------|--------|------|--------|------|
| **Qwen3-ASR** | MLX (GPU) | **매우 빠름** | **우수** | **기본값** |
| Whisper | faster-whisper (CPU) | 보통 | 좋음 | 폴백용 |

## 용어 사전

사전 파일: `~/.damso/dictionary.json`

- **프리셋**: 개발 용어 자동 포함 (깃허브→GitHub, 리액트→React 등)
- **사용자 용어**: 설정 UI에서 추가하거나 직접 파일 편집
- 입력 전에 자동 치환되어 전문용어가 정확하게 입력됨

## 기술 스택

- Python 3.14+
- mlx-qwen3-asr (Qwen3-ASR, Apple Silicon MLX)
- faster-whisper (Whisper CPU fallback)
- rumps (macOS 메뉴바)
- Quartz CGEvent (글로벌 핫키 + 텍스트 삽입)
- sounddevice (오디오 캡처)
- pywebview (설정 UI)
- SQLite (히스토리/사전 저장)
