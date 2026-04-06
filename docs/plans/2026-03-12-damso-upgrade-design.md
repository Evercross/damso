# Damso v1.0 — Design Document

**Date**: 2026-03-12
**Status**: Approved
**Project**: Mallo Local → Damso (담소) upgrade

## Goal

Upgrade the local macOS STT app from Whisper (CPU, slow) to Qwen3-ASR (MLX, fast) and rebrand from "Mallo Local" to "Damso (담소)".

**Primary objective**: Speed — reduce transcription latency from ~6-8s to ~0.5s.

## Current State

- **Project path**: `/Users/Sung_Book/Downloads/mallo_custom/mallo_local`
- **Runtime**: Python 3.14.2, .app bundle via PyInstaller
- **STT engine**: `faster-whisper` (WhisperModel, CPU, int8)
- **Current config**: `large-v3` model → accurate but ~6-8s per 5s audio
- **UI**: macOS menu bar app (rumps) + settings window (pywebview)
- **Hotkeys**: Fn, Right Option, Mouse side button (hold-to-speak)

### File Structure

| File | Role |
|------|------|
| `app.py` | Main app, menu bar, hotkey listener |
| `stt.py` | STT engine (faster-whisper) |
| `config.py` | Config load/save, defaults, paths |
| `settings_ui.py` | pywebview settings window |
| `dictionary.py` | Term replacement |
| `history.py` | SQLite history |
| `text_inserter.py` | Clipboard paste via CGEvent |
| `build_app.sh` | PyInstaller .app build script |

## Design

### 1. STT Engine Replacement (`stt.py`)

Replace `faster-whisper` internals with `mlx-qwen3-asr` Session API.

**Before** (faster-whisper, CPU):
```python
from faster_whisper import WhisperModel
model = WhisperModel("large-v3", device="cpu", compute_type="int8")
segments, info = model.transcribe(audio, language="ko", beam_size=5, vad_filter=True)
```

**After** (mlx-qwen3-asr, Apple Silicon GPU):
```python
from mlx_qwen3_asr import Session
session = Session(model="Qwen/Qwen3-ASR-1.7B")
result = session.transcribe(audio_array_or_path)
text = result.text
```

Key changes inside `STTEngine`:
- `load_model()` → create `Session(model="Qwen/Qwen3-ASR-1.7B")`
- `transcribe(audio)` → save audio to temp WAV, call `session.transcribe(path)`
- Recording logic (`start_recording`, `stop_recording`) stays identical (sounddevice)
- Keep `faster-whisper` import as optional fallback

### 2. Rebranding: Mallo Local → Damso

| Item | Before | After |
|------|--------|-------|
| App class | `MalloApp` | `DamsoApp` |
| Data dir | `~/.mallo_local` | `~/.damso` |
| DB file | `mallo.db` | `damso.db` |
| Log file | `mallo_local.log` | `damso.log` |
| Logger name | `mallo` | `damso` |
| Bundle name | `Mallo Local.app` | `Damso.app` |
| Bundle ID | `com.mallolocal.app` | `com.damso.app` |
| Settings title | `Mallo Local Settings` | `Damso Settings` |
| Notifications | `Mallo Local` | `Damso` |

**Data migration**: On first launch, if `~/.mallo_local` exists and `~/.damso` doesn't, copy data over.

### 3. Config Changes

```json
{
  "stt_engine": "qwen3-asr",
  "qwen_model": "Qwen/Qwen3-ASR-1.7B",
  "whisper_model": "large-v3",
  "language": "ko",
  "hotkey_hold": "fn",
  "hotkey_toggle": "fn+space",
  "sample_rate": 16000,
  "history_retention_days": 30,
  "insert_method": "cgevent",
  "show_notification": true,
  "auto_punctuation": true
}
```

### 4. Settings UI Updates

- Sidebar logo: "Damso" with new accent
- Engine selector dropdown: Qwen3-ASR / Whisper
- Model selector updates based on engine choice
- Section label: "WHISPER" → "STT ENGINE"

### 5. Build Script Updates

- Output: `Damso.app`
- `requirements.txt`: add `mlx-qwen3-asr`, keep `faster-whisper` as optional
- PyInstaller spec: update app name, bundle ID, icon references

### 6. No Changes

These files need no logic changes (only string replacements for branding):
- `dictionary.py` — term replacement logic unchanged
- `history.py` — SQLite logic unchanged (path comes from config)
- `text_inserter.py` — paste logic unchanged

## Expected Performance

| Metric | Before | After |
|--------|--------|-------|
| Transcription (5s audio) | ~6-8s | ~0.5s |
| Model load time | ~3s | ~5s (first load, cached after) |
| Memory usage | ~3GB | ~3.4GB |
| Accuracy (Korean) | Whisper large-v3 | Equal or better |
| Device utilization | CPU only | Apple Silicon GPU (MLX) |

## Risk & Mitigation

| Risk | Mitigation |
|------|------------|
| mlx-qwen3-asr install fails | Keep faster-whisper as fallback in config |
| Qwen3-ASR Korean quality worse than expected | Config toggle to switch back to Whisper |
| Temp WAV file overhead | Use numpy array directly if API supports it |
| Data loss on migration | Copy (not move) from ~/.mallo_local |
