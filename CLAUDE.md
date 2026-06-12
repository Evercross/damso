# CLAUDE.md — Damso (담소) 프로젝트 가이드

> 이 파일은 Claude Code가 damso 프로젝트를 이해하고 작업하기 위한 설정 파일입니다.
> 프로젝트 루트(`mallo_local/`)에 위치시켜 주세요.

---

## 프로젝트 개요

**Damso (담소)** — macOS 메뉴바 상주 음성-텍스트 입력 앱
- 핫키/마우스 버튼으로 음성 입력 시작 → STT 변환 → 현재 활성 앱에 텍스트 삽입
- 한국어/영어/일본어 지원
- 개인용 (개발자 본인 맥북에서만 사용)

### 핵심 사용 시나리오
- 작업 중 수시로 음성 입력 (카톡, 메모, 브라우저 등)
- 메뉴바 아이콘으로 입력 상태(녹음 중/변환 중) 실시간 확인
- 맥북 부팅 시 자동 시작 또는 Alfred 워크플로우로 즉시 실행

---

## 기술 스택

| 항목 | 값 |
|------|-----|
| 언어 | Python 3.14 |
| 메뉴바 | rumps 0.4+ |
| 설정 UI | pywebview 4.0+ (HTML/CSS/JS 임베딩) |
| STT 엔진 | Qwen3-ASR 1.7B (MLX GPU, 기본) / faster-whisper (CPU fallback) |
| macOS 연동 | PyObjC 12.1 (Quartz, AppKit) |
| 데이터 | SQLite (기록), JSON (설정/사전) |
| 실행 방식 | **터미널 실행 (python app.py)** — .app 빌드 사용 안 함 |

### 왜 터미널 실행인가
- .app (PyInstaller) 빌드 시 ad-hoc 서명 → 재빌드마다 TCC Accessibility 권한 리셋
- 터미널 실행 시 Terminal.app의 기존 Accessibility 권한을 상속 → 안정적
- rumps 메뉴바 아이콘은 터미널 실행에서도 동일하게 작동

---

## 아키텍처

### 파일 구조 (핵심만)

```
mallo_local/
├── app.py              # 엔트리포인트 — DamsoApp(rumps.App), 핫키, 딕테이션
├── stt.py              # STT 엔진 — Qwen3-ASR + Whisper fallback
├── text_inserter.py    # 텍스트 삽입 — CGEvent/AppleScript/Unicode
├── settings_ui.py      # 설정 UI — pywebview + HTML/JS
├── config.py           # 설정 관리 — JSON 로드/저장
├── dictionary.py       # 용어 치환 — 프리셋 76개 + 사용자 정의
├── history.py          # 기록 관리 — SQLite
├── permissions.py      # macOS 권한 체크
├── diagnostics.py      # 진단 리포트
├── run.sh              # 실행 스크립트
└── requirements.txt    # Python 의존성
```

### 삭제 대상 (레거시)
- `create_icon.py` — 중복, `create_icons.py`로 대체됨
- `launcher.c` — 네이티브 런처, PyInstaller로 대체됨 (지금은 PyInstaller도 미사용)
- `setup_app.py` — py2app 설정, 미사용
- `build_app.sh` / `Damso.spec` — PyInstaller 빌드, 터미널 실행으로 전환 시 불필요

### 삭제 대상 (미사용 의존성, requirements.txt에서 제거)
- `pynput` — CGEvent tap으로 대체됨
- `pyperclip` — pbcopy/pbpaste로 대체됨
- `py2app` — PyInstaller로 대체 후 다시 미사용

### 프로세스/스레드 구조

```
Main Thread (rumps event loop)
├── Daemon: Model loader thread
├── Daemon: Permission watcher (4초 폴링)
├── Daemon: Hotkey listener (CGEvent run loop)
├── Daemon: Hotkey action queue worker
├── Daemon: Dictation process thread (녹음→변환→삽입)
└── Subprocess: Settings UI (별도 프로세스)
```

### 런타임 데이터 위치

```
~/.damso/
├── config.json       # 사용자 설정
├── damso.db          # 기록 DB (SQLite)
├── dictionary.json   # 사용자 용어 사전
├── damso.log         # 런타임 로그
├── damso.lock        # 싱글 인스턴스 락
└── diagnostics/      # 진단 리포트 JSON
```

---

## 작업 규칙

### 반드시 지킬 것
1. **터미널 실행 기준으로 작업** — PyInstaller/.app 관련 코드 건드리지 않기
2. **기능 변경 전 현재 작동 확인** — 진단 리포트 결과 기준, 작동하는 기능을 깨뜨리지 않기
3. **macOS 권한은 건드리지 않기** — Accessibility/Automation 권한은 터미널이 대신 처리
4. **스레드 안전성 유지** — Lock, SimpleQueue 패턴 유지, 새 전역 상태 추가 금지
5. **설정 변경은 config.py 경유** — 설정 직접 수정 금지, 반드시 로드/저장 함수 사용

### 코딩 컨벤션
- 로깅: `log.info()` / `log.error()` 사용 (print 금지)
- 예외 처리: `except Exception: pass` 지양 — 최소한 `log.debug()` 추가
- 함수 단위 주석: 영문 docstring 유지
- 타입 힌트: 새로 추가/수정하는 함수에는 타입 어노테이션 필수

### 테스트
- 변경 후 기본 검증: `python app.py` 실행 → 메뉴바 아이콘 표시 → 음성 입력 → 텍스트 삽입
- 설정 UI: 메뉴바 → Settings 클릭 → 창 열림/닫힘 확인
- 종료: 메뉴바 → Quit → 프로세스 잔존 없는지 `ps aux | grep damso` 확인

---

## 현재 이슈 목록

### 해결 완료 (재빌드/재실행 필요)
- [x] 앱 종료 시 settings 서브프로세스 잔존
- [x] settings 창 닫아도 프로세스 미종료
- [x] force_exit 스레드 daemon=True 문제
- [x] 설정 창 kill 후 리소스 충돌

### P2: 구조 개선 (우선순위순)
- [ ] 로그 로테이션 없음 → RotatingFileHandler(10MB, 5백업)
- [ ] history.py에서 print() 사용 → log.info()로 통일
- [ ] 미사용 import 제거 (history.py의 `import time`)
- [ ] 레거시 파일 정리 (위 삭제 대상 참고)
- [ ] 미사용 의존성 제거 (requirements.txt)
- [ ] 타입 힌트 추가 (새 코드부터)

### P3: 개선 사항
- [ ] 권한 체크 캐싱 (30초 TTL)
- [ ] 모듈 레벨 NSApplication 설정 → main()으로 이동
- [ ] settings_ui.py HTML/CSS/JS 분리 (현재 1,047줄)
- [ ] subprocess 타임아웃 매직넘버 → 클래스 상수화
- [ ] 앱별 삽입 전략 하드코딩 → config로 이동
- [ ] 프로세스 이름 표시 개선 (Activity Monitor에서 "Damso"로 표시)

---

## 프로세스 이름 표시 (Activity Monitor / 활성 앱)

터미널 실행 시 프로세스가 "Python"으로 보이는 문제 해결:

```python
# app.py 상단에 추가
import ctypes
try:
    libc = ctypes.cdll.LoadLibrary("libc.dylib")
    # setproctitle 대체 — macOS에서 프로세스 이름 변경
    libc.setprogname(b"Damso")
except Exception:
    pass

# 또는 setproctitle 패키지 사용
# pip install setproctitle
# import setproctitle; setproctitle.setproctitle("Damso")
```

rumps 앱 이름은 이미 DamsoApp으로 설정되어 있으므로 메뉴바에는 정상 표시됨.

---

## 자동 시작 설정

### 방법 1: macOS 로그인 항목 (권장)
```bash
# ~/Library/LaunchAgents/com.damso.app.plist 생성
cat << 'EOF' > ~/Library/LaunchAgents/com.damso.app.plist
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.damso.app</string>
    <key>ProgramArguments</key>
    <array>
        <string>/Users/Sung_Book/Projects/damso/.venv/bin/python</string>
        <string>/Users/Sung_Book/Projects/damso/app.py</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <false/>
    <key>WorkingDirectory</key>
    <string>/Users/Sung_Book/Projects/damso</string>
    <key>StandardOutPath</key>
    <string>/tmp/damso-stdout.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/damso-stderr.log</string>
</dict>
</plist>
EOF

# 등록
launchctl load ~/Library/LaunchAgents/com.damso.app.plist
```

### 방법 2: Alfred 워크플로우
```bash
# Alfred 워크플로우에 다음 스크립트 등록
cd /Users/Sung_Book/Projects/damso && .venv/bin/python app.py &
```

---

## Codex 검증 체크리스트

Claude Code에서 작업 후, Codex에 다음을 검증 요청:

```
다음 변경사항을 검증해줘:

1. 기존 작동 기능이 깨지지 않았는지 (특히 STT, 텍스트 삽입, 메뉴바)
2. 스레드 안전성 — Lock/Queue 패턴이 유지되는지
3. macOS API 호출이 올바른지 (PyObjC 패턴)
4. 예외 처리가 적절한지 (silent except 없는지)
5. 설정 변경이 config.py 경유하는지

변경된 파일: [파일 목록]
변경 내용: [요약]
```

---

## 기능 로드맵

### Phase 1: 안정화 (현재)
- 터미널 실행 전환
- 레거시 정리
- 프로세스 종료 문제 해결 확인
- 로그 로테이션 추가

### Phase 2: 기능 확장 (기획 참고)
- → 별도 기획 문서 참조 (FEATURE_IDEAS.md)

### Phase 3: 배포 준비 (향후)
- Developer ID 서명
- .app 번들 재구성
- 자동 업데이트 (Sparkle)
