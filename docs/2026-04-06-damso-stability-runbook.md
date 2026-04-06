# Damso Stability Runbook (2026-04-06)

## 1) Why it looked random (`됐다 안됐다`)

Damso insertion/hotkey reliability depends on **two independent macOS permissions**:

- `Accessibility (손쉬운 사용)` for global key capture and CGEvent typing/paste.
- `AppleEvents (자동화/System Events)` for AppleScript fallback insertion.

When either permission is missing, parts of the flow fail.  
When both are missing, insertion and hotkeys both fail.

In this project, repeated rebuild/install cycles with **ad-hoc signing** can also cause
permission re-grant prompts to reappear, which feels random from user perspective.

## 2) Key structural fixes now in place

- Menu bar now includes:
  - `모델 업데이트`
  - `권한 점검`
  - `진단 리포트 생성`
- Startup no longer auto-opens permission prompts every launch.
- Background permission watcher now logs/monitors permission state and re-attempts
  hotkey listener activation when Accessibility is restored.
- Settings launch now terminates stale `--settings` processes before opening a new one
  so the UI reflects the latest build.
- Settings page includes:
  - Model update status + `Check & Update`
  - Live permission status (`Accessibility` / `Automation`) with recovery buttons
  - Runtime metadata (actual executable path + build time)
  - Diagnostics report generator
- Build/install script now removes `dist/Damso.app` after install to reduce duplicate launch
  targets in Spotlight/Alfred.
- Build/install script supports stable signing identity via
  `DAMSO_CODESIGN_IDENTITY` and uses `ditto` install.

## 3) Deterministic health check (always same order)

1. Launch only `/Applications/Damso.app`.
2. Open Damso menu:
   - `진단 리포트 생성`
3. Confirm permissions:
   - System Settings > Privacy & Security > Accessibility: Damso ON
   - System Settings > Privacy & Security > Automation: Damso -> System Events ON
   - Damso menu > `권한 점검` once (refresh internal state)
4. Test insertion:
   - `텍스트 삽입 테스트` in TextEdit or Notes.
5. Test hold-to-talk:
   - Right Option hold -> speak -> release.

If failure persists, generate diagnostics again immediately after failure.

## 4) Cross-verification package for Claude Code

Share these artifacts:

- Latest diagnostics JSON in:
  - `~/.damso/diagnostics/`
- Runtime log:
  - `~/.damso/damso.log`
- Current config:
  - `~/.damso/config.json`
- This runbook:
  - `docs/2026-04-06-damso-stability-runbook.md`

## 5) Known constraints

- With ad-hoc signing, macOS trust continuity can be less stable across rebuilt binaries.
- For stable long-term distribution to other users, use a persistent signing identity
  (Developer ID/Application cert) and avoid frequent bundle identity changes.
