# Damso 배포 로드맵 + 기능 기획 (2026-06-12)

> 작성 기준: 2026-06-12 런타임 로그 / git 히스토리 / 기존 문서(CLAUDE.md, FEATURE_IDEAS.md, 안정화 런북) 교차 검증.

---

## 0. 현재 상태 정정 (중요)

기존 핸드오프 요약("`/Applications/Damso.app` 런타임에서 accessibility=missing으로 삽입/핫키가 막힌 상태")은 **4월 6일 기준이며, 현재는 해당 없음.**

- **2026-06-12 13:45 로그 기준, 담소는 정상 작동 중.**
  - 터미널 실행(`python app.py`) → Right Option hold → Qwen3-ASR 변환(7초 음성 → 3.1초 변환) → `cgevent` 전략으로 Codex에 삽입 성공.
- 4월의 accessibility 문제는 **PyInstaller `.app` + ad-hoc 서명** 조합에서 재빌드마다 TCC 권한이 리셋되던 것. 이후 **터미널 실행으로 전환**하면서 해소됨 (Terminal.app의 Accessibility 권한 상속).
- 현재 `/Applications/damso.app`은 PyInstaller 번들이 아니라 **Automator 런처 스텁**(4/12 생성) — 터미널 실행을 앱처럼 띄우는 용도.
- `CLAUDE_CODE_HANDOFF.md`는 작업 트리에서 삭제됨(레거시 정리의 일부). 필요 시 `git show HEAD:CLAUDE_CODE_HANDOFF.md`로 열람 가능.

### 이미 완료된 것 (CLAUDE.md 이슈 목록보다 진척됨)
- [x] 로그 로테이션 — `RotatingFileHandler`(10MB, 5백업) 적용 확인 (app.py:108-121)
- [x] history.py `print()` → logging 전환, 미사용 `import time` 제거
- [x] 레거시 파일 삭제 (launcher.c, setup_app.py, build_app.sh, Damso.spec, build/ 등 — 작업 트리에서 삭제됨)
- [x] 텍스트 삽입 단계별 로깅 (`step:clipboard_*`, `step:cgevent_*`)
- [x] 알림 미리보기 기반 (`show_notification` 설정 + rumps.notification 구현, 현재 off)
- [x] 히스토리 조회 메뉴 (`on_open_history`, 최근 20개)

### ⚠️ 즉시 처리 필요: 미커밋 변경분
마지막 커밋(c86e231) 이후 **터미널 실행 전환 전체가 미커밋 상태** (app.py +1030줄, stt.py +341줄, text_inserter.py +436줄, 레거시 삭제 다수). 디스크 장애·실수 한 번이면 두 달치 작업이 날아감.

```bash
# 권장: 의미 단위로 커밋 (대략)
git add -A
git commit -m "feat: terminal-execution pivot — stability runbook, permission watcher, step logging, legacy cleanup"
# + .gitignore에 __pycache__/, .DS_Store, build/, dist/ 추가
```

---

## 1. 배포까지의 로드맵

> **2026-06-12 결정: 라이트 런칭으로 확정.**
> - 범위: GitHub 공개 배포 + 지인 공유. 풀 런칭(랜딩페이지/결제/마케팅) 안 함.
> - Apple Developer($99) 보류 — 지인은 "우클릭 → 열기" 안내로 충분. 사용자 10명+ 시 재검토.
> - 회의록/시스템 오디오 축 제외 (클라우드 영역, 라이트 범위 밖).
> - 다듬기 모드는 "사람에게 보내는 글" 타깃으로 v1.1.
> - 아이폰 보류 — iOS 제약(키보드 확장 마이크/메모리) + Swift 재작성 필요. 이동 중 캡처 니즈는 plaud-pipeline 영역.

"배포"의 정의(라이트 기준): **개발자 지인이 README만 보고 클론 → 설치 → 권한 설정 → 사용까지 막힘 없이 도달하는 상태.**

### Phase A — 리포 정리 & 기반 다지기 (1-2일)
1. 미커밋 변경분 커밋 + `.gitignore` 정비 (`__pycache__/`, `.DS_Store`, `build/`, `dist/`, `*.pyc`)
2. 프로젝트를 `~/Downloads/` 밖으로 이동 (예: `~/Projects/damso`) — Downloads는 macOS가 특별 취급(권한/정리 대상)하는 경로라 배포 베이스로 부적합. LaunchAgent/Automator 스텁 경로도 함께 갱신.
3. GitHub 리포 생성(private) — 백업 + 이슈 트래킹 + 추후 Releases 배포 채널
4. 버전 체계 도입 (`__version__ = "1.0.0"`, 메뉴바 About에 표시)

### Phase B — 패키징 재도전 (핵심 난관, 3-5일)
4월에 실패한 `.app` 패키징의 실패 원인은 **ad-hoc 서명 → 재빌드마다 TCC 리셋**이었음. 해법은 빌드 방식이 아니라 **서명 정체성의 안정화**:

1. **Apple Developer Program 가입 ($99/년) — 배포의 전제조건.**
   - Developer ID Application 인증서로 서명하면 재빌드해도 TCC 권한 유지됨 (TeamIdentifier 기준 신뢰).
   - 미가입 시: 자기 서명 인증서로 본인 머신은 해결되지만, 타인 배포는 Gatekeeper에 막힘 → 배포 불가.
2. PyInstaller `.app` 재빌드 (기존 Damso.spec은 git에 있음 — `git show HEAD:Damso.spec`)
   - MLX Metal 호환을 위한 네이티브 python3 임베딩은 c86e231 커밋에서 이미 해결한 바 있음.
   - `DAMSO_CODESIGN_IDENTITY=Developer ID Application: ...` 환경변수 경로는 빌드 스크립트에 이미 구현됨.
3. 공증(notarization): `xcrun notarytool submit` + `stapler` — Gatekeeper 통과 필수.
4. 모델 분리: 4GB Qwen 모델은 번들에 포함하지 말고 **첫 실행 시 다운로드** (HuggingFace cache 활용, 진행률 UI).

### Phase C — 신규 사용자 경험 (3-5일)
배포하면 "권한 설정"이 최대 이탈 지점. 본인이 두 달간 겪은 고통을 온보딩으로 흡수:

1. **첫 실행 온보딩 마법사** — 마이크 → 손쉬운 사용 → (필요시) 자동화 권한을 단계별로 안내, 각 단계에서 실시간 권한 감지(이미 permission watcher 있음)로 자동 진행.
2. **삽입 테스트 단계** — 온보딩 마지막에 "텍스트 삽입 테스트"(이미 메뉴에 있음)로 성공 확인.
3. 진단 리포트(이미 구현됨)를 "문제 신고" 버튼과 연결.

### Phase D — 배포 채널 & 운영 (2-3일)
1. GitHub Releases에 DMG 업로드 (`create-dmg`)
2. Homebrew cask (`brew install --cask damso`) — 개발자 타깃에 최적
3. 업데이트 확인: 메뉴바 `업데이트 확인` → GitHub Releases API 비교 (Sparkle은 Python 앱 통합이 번거로우니 v1은 수동 다운로드 안내로 충분)
4. 랜딩 페이지 1장 (GitHub Pages) — "완전 로컬, 오프라인 한국어 음성 입력" 포지셔닝

### 의사결정 현황 (2026-06-12 갱신)
| 결정 | 결론 |
|------|------|
| Apple Developer 가입 | **보류** — 라이트 런칭은 클론 설치 방식이라 불필요. 사용자 10명+ 시 재검토 |
| 배포 범위 | **무료, GitHub 공개 + 지인 공유** |
| 리포 공개 | **public** (남은 선택: LICENSE — 추후 서비스화 여지 고려 시 OSS 라이선스 없이 source-available도 옵션) |

### 라이트 런칭 체크리스트 (위 Phase A-D를 대체)
- [x] 미커밋 작업 커밋 + .gitignore (2026-06-12 완료, 4커밋)
- [ ] 화자 등록(N-6, "내 목소리만 받아쓰기")은 v1.1 — 시나리오: 배경 음성 필터링 (동시 발화 분리는 범위 밖)
- [x] README를 배포용 상세 페이지로 (2026-06-12 완료 — 데모 GIF만 TODO)
- [x] 앱 아이콘 리디자인 (2026-06-12 완료 — A2 "크림+코랄 말풍선 마이크", 메뉴바 템플릿 아이콘 포함)
- [ ] setup.sh 신규 머신 검증 (의존성/모델 다운로드 안내 포함)
- [ ] 마무리 디테일: 자동 언어 감지, 사운드 피드백, 히스토리 재삽입
- [ ] Mallo 유래 문구/프리셋 점검 후 교체
- [ ] GitHub 리포 생성(public) + push (gh CLI 미설치 — `brew install gh` 필요)
- [ ] 지인 1명 베타: README만 보고 설치 성공하는지 관찰 → 막힌 지점 수정

---

## 2. 기능 기획 (FEATURE_IDEAS.md 갱신판)

### 구현 현황 반영
| 기능 | 상태 |
|------|------|
| 1-1 알림 미리보기 | ✅ 구현됨 (`show_notification`, 기본 off) |
| 1-2 최근 히스토리 | 🔶 조회만 가능 — "클릭 시 재삽입" 미구현 |
| 1-3 자동 언어 감지 | ❌ 미구현 (`language="ko"` 고정) |
| 1-4 사전 학습 모드 | ❌ 미구현 |

### 신규 제안 (배포 관점에서 추가)

**N-1. 다듬기 모드 (Polish Mode)** — 임팩트 ★★★, 난이도 중
- 변환 직후 로컬 LLM(MLX로 Qwen3 4B급) 또는 Claude API로 "말버릇 제거 + 문장 정리" 한 단계 추가.
- 예: "어 그러니까 접수 관련해서 어 안내는…" → "접수 관련 안내는…"
- 음성 입력의 고질적 약점(구어체 그대로 입력됨)을 해결 — **유료화 근거가 되는 첫 기능.**
- 핫키 분리: Right Option = 그대로 삽입, Right Option+Shift = 다듬어서 삽입.

**N-2. 온보딩 마법사** — 임팩트 ★★★ (배포 필수), 난이도 중
- Phase C 참조. 기능이라기보다 배포 전제조건.

**N-3. 오인식 즉시 교정 → 사전 자동 제안** — 임팩트 ★★★, 난이도 중
- 삽입 직후 사용자가 텍스트를 수정하면(클립보드/이벤트 비교는 어려우니 v1은 "방금 입력 교정" 메뉴), 원문↔교정문 diff에서 치환 규칙 추출 → 사전에 제안.
- 기존 1-4의 현실적인 구현 경로.

**N-4. 입력 통계 대시보드** — 임팩트 ★★☆, 난이도 하
- 설정 UI에 "이번 주 N회, 총 M자, 절약한 타이핑 시간 ~X분" — 히스토리 DB에 데이터 이미 있음.
- 사용자 유지(retention)와 "이 앱이 가치 있다"는 체감을 만드는 배포용 기능.

**N-5. 푸시투토크 사운드 피드백** — 임팩트 ★★☆, 난이도 하
- 녹음 시작/종료 시 짧은 사운드 (NSSound). 메뉴바를 안 보고도 상태 인지 — hold-to-speak UX의 완성도.

### 우선순위 제안 (배포 목표 기준)

```
지금 바로 (배포 전 마무리, 코드 수정 수준):
  1. 1-3 자동 언어 감지        — stt.py 옵션 한 줄 수준, 체감 큼
  2. 1-2 히스토리 클릭 재삽입   — 메뉴 콜백 추가
  3. N-5 사운드 피드백          — NSSound 몇 줄

배포 준비와 병행 (Phase B-C 기간):
  4. N-2 온보딩 마법사          — 배포 전제조건
  5. N-4 입력 통계              — 설정 UI에 탭 추가

배포 후 v1.1 (차별화/유료화):
  6. N-1 다듬기 모드            — 핵심 차별점
  7. N-3 사전 자동 제안
  8. 3-1 실시간 자막 / 3-2 회의록 — 기존 Tier 3 유지
```

---

## 3. 경쟁 분석 & 차별화 전략 (vs Mallo)

> 출처: https://www.mallo.so/ko (2026-06-12 확인). 담소의 원조 영감이 된 앱.

### Mallo 현황
- **가격**: $19 일회성 (런칭 할인, 정가 $29) / 평생 라이선스, Mac 3대
- **macOS 전용**, 로컬 STT (Whisper 기본 / Parakeet / Qwen)
- 핵심 기능: hold-to-speak (Fn/Globe), 토글 모드, 용어 사전(프리셋+커스텀), 히스토리, 포커스 유지
- AI 후처리는 "선택형 문장 정리" 수준 — **깊은 AI 기능 없음**
- 타깃: 개발자(AI 코딩 도구), 콘텐츠 작성자 — 글로벌 제품의 한국어 번역 페이지

### 기능 패리티 현황 (담소가 이미 따라잡은 것)
| 기능 | Mallo | Damso |
|------|-------|-------|
| 로컬 STT | ✅ Whisper 기본 | ✅ **Qwen3-ASR MLX 기본** (GPU, 더 빠름) + Whisper 폴백 |
| hold-to-speak | ✅ Fn/Globe | ✅ Right Option / Fn / **마우스 사이드 버튼** (Mallo에 없음) |
| 용어 사전 | ✅ | ✅ 프리셋 76개 + 커스텀 |
| 히스토리 | ✅ | ✅ SQLite + 보관기간 설정 |
| 토글 모드 | ✅ | ✅ Ctrl+Shift+M |

→ **코어 기능은 이미 패리티 이상.** 같은 기능으로 $19 시장에서 정면승부하면 후발주자가 불리. 차별화 축이 필요.

### 차별화 전략: "받아쓰기 도구"가 아니라 "한국어 AI 음성 입력"

Mallo가 비워둔 영역 = 담소의 색:

**축 1 — 한국어 네이티브 (가장 강한 해자)**
- Mallo는 글로벌 제품의 한국어 지원. 담소는 **한국어가 1순위인 제품.**
- 구어체→문어체 정제 (한국어 말버릇 "어 그러니까", "~해가지고" 제거 — 영어권 제품이 못 따라옴)
- 존댓말↔반말 변환, 비즈니스 어투 변환
- 한국 개발자/직장인 용어 프리셋 (이미 76개 보유 — 확장)

**축 2 — AI 후처리 깊이 (다듬기 모드 = 핵심 차별점)**
- Mallo: "선택형 문장 정리" 한 줄. 담소: 다듬기/요약/번역/포맷 파이프라인 (FEATURE_IDEAS 2-2, N-1)
- 로컬 LLM(MLX) 기반이면 "완전 로컬" 포지셔닝 유지하면서 차별화 — Mallo 대비 기술적 우위 (이미 MLX 스택 보유)

**축 3 — AI 코딩 워크플로 특화**
- 본인이 매일 Codex/Claude Code에 음성으로 프롬프트 입력 중 — **이 사용 패턴 자체가 제품.**
- "바이브코딩 보이스": 코딩 에이전트용 프롬프트 음성 입력에 최적화 (개발 용어 사전, 긴 발화 안정성, 터미널/IDE 삽입 안정성)
- Mallo도 개발자를 타깃하지만 특화 기능은 없음

**축 4 — 회의록/시스템 오디오 (Phase 3 킬러 기능)**
- Mallo에 전혀 없음. 장기 수익화 축.

### 가격/서비스화 제안
- Mallo의 $19 일회성이 "유틸리티 받아쓰기"의 가격 앵커. 담소가 같은 카테고리면 그 이하로 팔아야 함 → 손해.
- 제안: **코어(받아쓰기) 무료 또는 저가 일회성 + AI 기능(다듬기/회의록)을 유료 티어로.**
  - 로컬 LLM 다듬기 → 일회성 가격에 포함 가능 (서버 비용 없음)
  - Claude API 연동 기능(고급 다듬기, 회의록 요약) → 구독 또는 BYOK(자기 API 키)
- v1 배포는 무료 공개로 사용자/피드백 확보 → AI 기능과 함께 유료화가 현실적 순서.

### ⚠️ 주의사항
- 디렉토리명(`mallo_custom`)이 시사하듯 Mallo에서 출발한 프로젝트 — 코드는 Python 자체 구현이므로 문제없으나, **마케팅 문구·프리셋 사전·UI 문구를 Mallo에서 그대로 가져온 게 있다면 배포 전 교체할 것.** 아이디어는 자유지만 카피는 리스크.
- 리포/디렉토리명도 `damso`로 이전 권장 (Phase A의 이동과 함께).

---

## 4. 검증 체크리스트 (변경 후 매번)

1. `python app.py` → 메뉴바 🎤 표시
2. Right Option hold → 말하기 → 놓기 → 활성 앱에 삽입 (`damso.log`에서 `method=cgevent` 확인)
3. 설정 UI 열기/닫기 → `ps aux | grep -i damso`로 잔존 프로세스 없음
4. Quit → 프로세스 완전 종료
5. (패키징 후) `.app` 실행 시 진단 리포트에서 `accessibility_trusted: true` + 4월 6일 로그 패턴(`Strategy 'applescript' failed` 연쇄) 재발 없는지 확인
