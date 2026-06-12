# STT Plugin Architecture

**Date:** 2026-04-07
**Status:** Approved

## Goal

Split monolithic `stt.py` into a plugin structure so STT backends can be added/removed/updated independently without touching shared code.

## Structure

```
stt/
├── __init__.py           # Public API (STTEngine, list_input_devices, etc.)
│                         # Audio recording/device management (shared)
│                         # Backend registry + auto-discovery
├── backend_qwen.py       # Qwen3-ASR (MLX GPU)
├── backend_whisper.py    # Whisper (faster-whisper, CPU)
└── backend_xxx.py        # Future backends — just add file
```

## Backend Interface

Each backend file defines a class with:
- `name`: engine key for config (e.g., "qwen3-asr")
- `display_name`: UI label (e.g., "Qwen3-ASR (MLX GPU)")
- `default_model`: default model identifier
- `models`: list of available model options for settings UI
- `load_model(model_name)`: load/initialize the model
- `transcribe(audio_data, language) -> str`: run inference
- `get_update_info(model_name)`: check for updates (HF-based)
- `update_model(model_name)`: download/update model

## Auto-discovery

`stt/__init__.py` imports all `backend_*.py` files in the package directory.
Each backend registers itself via `@register` decorator.
Settings UI reads available engines from the registry.

## External Interface (unchanged)

- `from stt import STTEngine, list_input_devices` — same as before
- `config.json` format unchanged
- `settings_ui.py` imports unchanged
- `app.py` imports unchanged

## Adding a New Backend

1. Create `stt/backend_xxx.py` with `@register` class
2. Add pip dependency to `requirements.txt`
3. Settings UI auto-populates from registry
