# Damso v1.0 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Upgrade Mallo Local to Damso — replace Whisper CPU STT with Qwen3-ASR MLX for 10x faster transcription, rebrand all surfaces, and rebuild .app bundle.

**Architecture:** The app is a Python macOS menu bar STT tool (rumps + sounddevice + CGEvent). STT is isolated in `stt.py` with a clean interface. We replace the internals with `mlx-qwen3-asr` Session API while keeping the same public methods. All other modules stay unchanged except string replacements for branding.

**Tech Stack:** Python 3.14, mlx-qwen3-asr, sounddevice, rumps, pywebview, PyInstaller, macOS Quartz CGEvent

**Project path:** `/Users/Sung_Book/Downloads/mallo_custom/mallo_local`

---

### Task 1: Install mlx-qwen3-asr and verify it works

**Files:**
- Modify: `requirements.txt`

**Step 1: Install mlx-qwen3-asr in the existing venv**

```bash
cd /Users/Sung_Book/Downloads/mallo_custom/mallo_local
source .venv/bin/activate
pip install mlx-qwen3-asr
```

**Step 2: Verify the package imports and model loads**

```bash
python3 -c "
from mlx_qwen3_asr import Session
print('✅ mlx_qwen3_asr imported successfully')
session = Session(model='Qwen/Qwen3-ASR-1.7B')
print('✅ Qwen3-ASR-1.7B model loaded successfully')
"
```

Expected: Both prints succeed. First run downloads the model (~3.4GB).

**Step 3: Update requirements.txt**

Replace contents of `requirements.txt` with:

```
mlx-qwen3-asr>=0.1.0
faster-whisper>=1.0.0
sounddevice>=0.4.6
numpy>=1.24.0
rumps>=0.4.0
pynput>=1.7.6
pyperclip>=1.8.2
pyobjc-framework-Quartz>=10.0
pyobjc-framework-Cocoa>=10.0
pywebview>=4.0
Pillow>=10.0
```

Note: `faster-whisper` kept as fallback dependency.

**Step 4: Commit**

```bash
git add requirements.txt
git commit -m "feat: add mlx-qwen3-asr dependency for Qwen3-ASR support"
```

---

### Task 2: Replace STT engine with Qwen3-ASR (`stt.py`)

**Files:**
- Modify: `stt.py` (full rewrite of internals, same public API)

**Step 1: Rewrite stt.py**

Replace the entire contents of `stt.py` with the new multi-engine implementation:

```python
"""
Damso - Speech-to-Text Engine
Supports: Qwen3-ASR (MLX, default) and Whisper (faster-whisper, fallback)
"""
import numpy as np
import sounddevice as sd
import threading
import time
import tempfile
import os
import soundfile as sf


class STTEngine:
    """Local STT engine with pluggable backends.

    Default: Qwen3-ASR via mlx-qwen3-asr (Apple Silicon GPU)
    Fallback: Whisper via faster-whisper (CPU)
    """

    def __init__(self, engine="qwen3-asr", model_name=None, language="ko", sample_rate=16000):
        self.engine = engine
        self.language = language
        self.sample_rate = sample_rate
        self.is_recording = False
        self.audio_buffer = []
        self._stream = None
        self._lock = threading.Lock()

        # Engine-specific defaults
        if engine == "qwen3-asr":
            self.model_name = model_name or "Qwen/Qwen3-ASR-1.7B"
        else:
            self.model_name = model_name or "large-v3"

        self._session = None  # Qwen3-ASR session
        self._whisper_model = None  # Whisper model

    def load_model(self):
        """Load the STT model. Call once at startup."""
        if self.engine == "qwen3-asr":
            self._load_qwen()
        else:
            self._load_whisper()

    def _load_qwen(self):
        """Load Qwen3-ASR model via mlx-qwen3-asr Session API."""
        print(f"[STT] Loading Qwen3-ASR model: {self.model_name}...")
        from mlx_qwen3_asr import Session
        self._session = Session(model=self.model_name)
        print(f"[STT] ✅ Qwen3-ASR model loaded successfully.")

    def _load_whisper(self):
        """Load Whisper model via faster-whisper (CPU fallback)."""
        print(f"[STT] Loading Whisper model: {self.model_name}...")
        from faster_whisper import WhisperModel
        self._whisper_model = WhisperModel(
            self.model_name,
            device="cpu",
            compute_type="int8",
        )
        print(f"[STT] ✅ Whisper model loaded successfully.")

    def start_recording(self):
        """Start capturing audio from microphone."""
        if self.is_recording:
            return

        with self._lock:
            self.audio_buffer = []
            self.is_recording = True

        def audio_callback(indata, frames, time_info, status):
            if status:
                print(f"[STT] Audio status: {status}")
            if self.is_recording:
                self.audio_buffer.append(indata.copy())

        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype="float32",
            callback=audio_callback,
            blocksize=1024,
        )
        self._stream.start()
        print("[STT] 🔴 Recording started...")

    def stop_recording(self):
        """Stop recording and return the audio data."""
        if not self.is_recording:
            return None

        with self._lock:
            self.is_recording = False

        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None

        if not self.audio_buffer:
            print("[STT] No audio recorded.")
            return None

        audio = np.concatenate(self.audio_buffer, axis=0).flatten()
        print(f"[STT] Recording stopped. Audio length: {len(audio) / self.sample_rate:.1f}s")
        return audio

    def transcribe(self, audio_data):
        """Transcribe audio data to text."""
        if audio_data is None or len(audio_data) == 0:
            return ""

        # Minimum audio length check (0.5 seconds)
        if len(audio_data) / self.sample_rate < 0.5:
            print("[STT] Audio too short, skipping.")
            return ""

        print("[STT] ⏳ Transcribing...")
        start_time = time.time()

        if self.engine == "qwen3-asr":
            result = self._transcribe_qwen(audio_data)
        else:
            result = self._transcribe_whisper(audio_data)

        elapsed = time.time() - start_time
        print(f"[STT] ✅ Transcription done in {elapsed:.2f}s: '{result}'")
        return result

    def _transcribe_qwen(self, audio_data):
        """Transcribe using Qwen3-ASR."""
        if self._session is None:
            raise RuntimeError("Qwen3-ASR model not loaded. Call load_model() first.")

        # Save audio to temp WAV file (mlx-qwen3-asr expects file path or array)
        tmp_path = None
        try:
            tmp_fd, tmp_path = tempfile.mkstemp(suffix=".wav")
            os.close(tmp_fd)
            sf.write(tmp_path, audio_data, self.sample_rate)

            result = self._session.transcribe(tmp_path)
            return result.text.strip() if result.text else ""
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.remove(tmp_path)

    def _transcribe_whisper(self, audio_data):
        """Transcribe using faster-whisper (fallback)."""
        if self._whisper_model is None:
            raise RuntimeError("Whisper model not loaded. Call load_model() first.")

        segments, info = self._whisper_model.transcribe(
            audio_data,
            language=self.language,
            beam_size=5,
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=500),
        )

        text_parts = []
        for segment in segments:
            text_parts.append(segment.text.strip())

        return " ".join(text_parts).strip()

    def record_and_transcribe(self):
        """Convenience: stop recording and immediately transcribe."""
        audio = self.stop_recording()
        if audio is None:
            return ""
        return self.transcribe(audio)
```

**Step 2: Verify stt.py imports cleanly**

```bash
cd /Users/Sung_Book/Downloads/mallo_custom/mallo_local
source .venv/bin/activate
python3 -c "from stt import STTEngine; print('✅ STTEngine imports OK')"
```

Expected: `✅ STTEngine imports OK`

**Step 3: Commit**

```bash
git add stt.py
git commit -m "feat: replace STT engine with Qwen3-ASR MLX backend

Multi-engine STTEngine supporting Qwen3-ASR (MLX GPU, default) and
Whisper (CPU fallback). Same public API, 10x faster transcription."
```

---

### Task 3: Update config for multi-engine support (`config.py`)

**Files:**
- Modify: `config.py`

**Step 1: Update config.py**

Changes needed:
1. `DATA_DIR`: `~/.mallo_local` → `~/.damso`
2. `DB_PATH`: `mallo.db` → `damso.db`
3. Add data migration from old path
4. Add `stt_engine` and `qwen_model` to `DEFAULT_CONFIG`

Replace the entire contents of `config.py`:

```python
"""
Damso (담소) - Configuration
"""
import os
import json
import shutil

# Paths
APP_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.expanduser("~/.damso")
OLD_DATA_DIR = os.path.expanduser("~/.mallo_local")
DB_PATH = os.path.join(DATA_DIR, "damso.db")
CONFIG_PATH = os.path.join(DATA_DIR, "config.json")
DICTIONARY_PATH = os.path.join(DATA_DIR, "dictionary.json")


def _migrate_old_data():
    """Migrate data from ~/.mallo_local to ~/.damso if needed."""
    if os.path.exists(OLD_DATA_DIR) and not os.path.exists(DATA_DIR):
        print(f"[Config] Migrating data from {OLD_DATA_DIR} → {DATA_DIR}...")
        shutil.copytree(OLD_DATA_DIR, DATA_DIR)
        # Rename db file if it exists
        old_db = os.path.join(DATA_DIR, "mallo.db")
        new_db = os.path.join(DATA_DIR, "damso.db")
        if os.path.exists(old_db) and not os.path.exists(new_db):
            os.rename(old_db, new_db)
        print(f"[Config] ✅ Migration complete.")


# Migrate before ensuring directory
_migrate_old_data()

# Ensure data directory exists
os.makedirs(DATA_DIR, exist_ok=True)

# Default configuration
DEFAULT_CONFIG = {
    "stt_engine": "qwen3-asr",       # qwen3-asr or whisper
    "qwen_model": "Qwen/Qwen3-ASR-1.7B",  # Qwen model name
    "whisper_model": "large-v3",      # tiny, base, small, medium, large-v3
    "language": "ko",                  # ko, en, ja, etc. or None for auto-detect
    "hotkey_hold": "fn",               # Hold-to-speak key
    "hotkey_toggle": "fn+space",       # Toggle dictation key
    "sample_rate": 16000,
    "history_retention_days": 30,
    "insert_method": "cgevent",        # cgevent (recommended) or applescript
    "show_notification": True,
    "auto_punctuation": True,
}

# Default dictionary presets (dev terms)
DEFAULT_DICTIONARY = {
    "presets": {
        "dev": {
            "깃허브": "GitHub",
            "깃헙": "GitHub",
            "깃": "Git",
            "리액트": "React",
            "넥스트": "Next.js",
            "타입스크립트": "TypeScript",
            "자바스크립트": "JavaScript",
            "파이썬": "Python",
            "노드": "Node.js",
            "도커": "Docker",
            "쿠버네티스": "Kubernetes",
            "수파베이스": "Supabase",
            "버셀": "Vercel",
            "프리즈마": "Prisma",
            "테일윈드": "Tailwind",
            "웹팩": "Webpack",
            "바이트": "Vite",
            "에이피아이": "API",
            "씨아이씨디": "CI/CD",
            "피알": "PR",
            "이슈": "Issue",
            "커밋": "commit",
            "브랜치": "branch",
            "머지": "merge",
            "풀리퀘스트": "Pull Request",
            "디플로이": "deploy",
            "엔드포인트": "endpoint",
            "미들웨어": "middleware",
            "옵시디언": "Obsidian",
            "노션": "Notion",
            "슬랙": "Slack",
            "클로드": "Claude",
            "클로드코드": "Claude Code",
            "챗지피티": "ChatGPT",
            "제미나이": "Gemini",
            "코덱스": "Codex",
        }
    },
    "user_terms": {},
    "enabled_presets": ["dev"],
}


def load_config():
    """Load configuration from file, creating defaults if needed."""
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            saved = json.load(f)
            config = {**DEFAULT_CONFIG, **saved}
    else:
        config = DEFAULT_CONFIG.copy()
        save_config(config)
    return config


def save_config(config):
    """Save configuration to file."""
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def load_dictionary():
    """Load dictionary from file, creating defaults if needed."""
    if os.path.exists(DICTIONARY_PATH):
        with open(DICTIONARY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    else:
        save_dictionary(DEFAULT_DICTIONARY)
        return DEFAULT_DICTIONARY.copy()


def save_dictionary(dictionary):
    """Save dictionary to file."""
    with open(DICTIONARY_PATH, "w", encoding="utf-8") as f:
        json.dump(dictionary, f, ensure_ascii=False, indent=2)
```

**Step 2: Verify config loads**

```bash
python3 -c "from config import load_config; c = load_config(); print('engine:', c['stt_engine']); print('✅ Config OK')"
```

Expected: `engine: qwen3-asr` then `✅ Config OK`

**Step 3: Commit**

```bash
git add config.py
git commit -m "feat: update config for Damso branding and multi-engine support

- Data dir: ~/.mallo_local → ~/.damso with auto-migration
- Add stt_engine and qwen_model config keys
- Default engine: qwen3-asr"
```

---

### Task 4: Update app.py — branding + engine wiring

**Files:**
- Modify: `app.py`

**Step 1: Apply all branding and engine changes to app.py**

The following changes are needed throughout `app.py`:

1. **Logger name**: `"mallo"` → `"damso"`
2. **Log messages**: All `"Mallo Local"` → `"Damso"`
3. **Class name**: `MalloApp` → `DamsoApp`
4. **Log file name**: `"mallo_local.log"` → `"damso.log"`
5. **Data dir reference**: `"~/.mallo_local"` → `"~/.damso"`
6. **Process info string**: `"Mallo Local is a menu bar app"` → `"Damso is a menu bar app"`
7. **STTEngine constructor**: Pass `engine` and `model_name` from config
8. **rumps.App title**: `"Mallo"` → `"Damso"`
9. **Notifications**: All `"Mallo Local"` → `"Damso"`
10. **Menu item labels**: Update Korean text references
11. **Test insert text**: `"Mallo Local 테스트"` → `"Damso 테스트"`
12. **main() banner**: Update ASCII art text
13. **Function name at bottom**: `MalloApp()` → `DamsoApp()`

Specific code changes in `__init__` for engine wiring:

```python
# Replace the old STTEngine construction:
self.stt = STTEngine(
    engine=self.config.get("stt_engine", "qwen3-asr"),
    model_name=(
        self.config.get("qwen_model") if self.config.get("stt_engine") == "qwen3-asr"
        else self.config.get("whisper_model")
    ),
    language=self.config["language"],
    sample_rate=self.config["sample_rate"],
)
```

And update `on_change_model` to handle engine-specific model changes:

```python
def on_change_model(self, model_size):
    """Change STT model."""
    engine = self.config.get("stt_engine", "qwen3-asr")
    if engine == "whisper":
        if model_size == self.config["whisper_model"]:
            return
        self.config["whisper_model"] = model_size
    else:
        if model_size == self.config["qwen_model"]:
            return
        self.config["qwen_model"] = model_size
    save_config(self.config)
    self.stt.model_name = model_size
    self.is_model_loaded = False
    self.title = "🎤"
    self._load_model_async()
    rumps.notification("Damso", "모델 변경", f"{model_size} 모델을 로딩합니다...")
```

**Step 2: Verify app.py imports and class instantiates**

```bash
python3 -c "
import sys; sys.modules['rumps'] = type(sys)('rumps')  # mock
from app import DamsoApp
print('✅ DamsoApp class exists')
" 2>/dev/null || echo "Check manually with: python3 app.py"
```

**Step 3: Commit**

```bash
git add app.py
git commit -m "feat: rebrand app.py from Mallo Local to Damso

- Class MalloApp → DamsoApp
- All notifications, logs, strings updated
- STTEngine wired with engine/model_name from config"
```

---

### Task 5: Update settings_ui.py — branding + engine selector

**Files:**
- Modify: `settings_ui.py`

**Step 1: Update settings_ui.py**

Changes needed in the HTML template:
1. Sidebar logo: `"Mallo Local"` → `"Damso"`
2. Window title: `"Mallo Local — Settings"` → `"Damso — Settings"`
3. Page subtitle: `"Configure Whisper, hotkeys..."` → `"Configure STT engine, hotkeys..."`
4. Section label: `"WHISPER"` → `"STT ENGINE"`
5. Add engine selector dropdown before model selector:

```html
<div class="card-row">
    <div class="card-row-info">
        <div class="card-row-label">Engine</div>
        <div class="card-row-desc">Speech recognition backend</div>
    </div>
    <select id="cfg-engine" onchange="onEngineChange()">
        <option value="qwen3-asr">Qwen3-ASR (MLX GPU) — Fast</option>
        <option value="whisper">Whisper (CPU) — Legacy</option>
    </select>
</div>
```

6. Update model dropdown to show engine-specific options:

```html
<select id="cfg-model">
    <!-- Populated by JS based on engine selection -->
</select>
```

7. Add JavaScript function `onEngineChange()`:

```javascript
function onEngineChange() {
    const engine = document.getElementById('cfg-engine').value;
    const modelSelect = document.getElementById('cfg-model');
    modelSelect.innerHTML = '';

    if (engine === 'qwen3-asr') {
        modelSelect.add(new Option('Qwen3-ASR-1.7B — Best quality', 'Qwen/Qwen3-ASR-1.7B'));
        modelSelect.add(new Option('Qwen3-ASR-0.6B — Lighter', 'Qwen/Qwen3-ASR-0.6B'));
    } else {
        modelSelect.add(new Option('Tiny — Fastest', 'tiny'));
        modelSelect.add(new Option('Base — Fast', 'base'));
        modelSelect.add(new Option('Small — Balanced', 'small'));
        modelSelect.add(new Option('Medium — Accurate', 'medium'));
        modelSelect.add(new Option('Large V3 — Best quality', 'large-v3'));
    }
}
```

8. Update `loadConfig()` to set engine dropdown:

```javascript
document.getElementById('cfg-engine').value = config.stt_engine || 'qwen3-asr';
onEngineChange();
// Set model value after populating options
const modelKey = config.stt_engine === 'whisper' ? 'whisper_model' : 'qwen_model';
document.getElementById('cfg-model').value = config[modelKey] || '';
```

9. Update `saveSettings()`:

```javascript
config.stt_engine = document.getElementById('cfg-engine').value;
const modelVal = document.getElementById('cfg-model').value;
if (config.stt_engine === 'whisper') {
    config.whisper_model = modelVal;
} else {
    config.qwen_model = modelVal;
}
```

**Step 2: Verify settings_ui.py runs**

```bash
python3 -c "from settings_ui import SETTINGS_HTML; print('✅ Settings HTML length:', len(SETTINGS_HTML))"
```

**Step 3: Commit**

```bash
git add settings_ui.py
git commit -m "feat: update settings UI with Damso branding and engine selector

- Add STT engine dropdown (Qwen3-ASR / Whisper)
- Dynamic model options based on engine choice
- All branding updated to Damso"
```

---

### Task 6: Update build script and spec file

**Files:**
- Modify: `build_app.sh`
- Modify: `MalloLocal.spec` → rename to `Damso.spec`

**Step 1: Update build_app.sh**

All changes are string replacements:
- `"Mallo Local"` → `"Damso"` (app name)
- `"MalloLocal"` → `"Damso"` (executable name)
- `"com.mallolocal.app"` → `"com.damso.app"` (bundle ID)
- `"MalloLocal.icns"` → `"Damso.icns"` (icon file reference, keep fallback to `icon.icns`)
- Header banner text update
- Microphone description: `"Mallo Local needs..."` → `"Damso needs..."`
- Post-install instructions: Update app name references

**Step 2: Rename and update spec file**

```bash
mv MalloLocal.spec Damso.spec
```

Update inside `Damso.spec`:
- `name='MalloLocal'` → `name='Damso'`
- `name='Mallo Local.app'` → `name='Damso.app'`
- `bundle_identifier='com.mallolocal.app'` → `bundle_identifier='com.damso.app'`
- `'CFBundleName': 'Mallo Local'` → `'CFBundleName': 'Damso'`
- `'CFBundleDisplayName': 'Mallo Local'` → `'CFBundleDisplayName': 'Damso'`
- Microphone/automation descriptions updated
- Icon reference: `'MalloLocal.icns'` → `'Damso.icns'` (or keep `icon.icns`)
- Replace `ctranslate2`/`faster_whisper` collect_all with `mlx_qwen3_asr`:

```python
mlx_d, mlx_b, mlx_h = collect_all('mlx_qwen3_asr')
# Keep faster_whisper as optional
try:
    fw_d, fw_b, fw_h = collect_all('faster_whisper')
except:
    fw_d, fw_b, fw_h = [], [], []
```

**Step 3: Commit**

```bash
git add build_app.sh Damso.spec
git rm MalloLocal.spec 2>/dev/null
git commit -m "feat: update build scripts for Damso branding

- Rename MalloLocal.spec → Damso.spec
- Update bundle name, ID, descriptions
- Add mlx_qwen3_asr to PyInstaller collection"
```

---

### Task 7: Update README and cleanup

**Files:**
- Modify: `README.md`
- Modify: `CLAUDE_CODE_HANDOFF.md`
- Modify: `run.sh`

**Step 1: Update README.md**

Update title, description, and all references from Mallo Local to Damso. Note the new engine and performance improvements.

**Step 2: Update CLAUDE_CODE_HANDOFF.md**

Update project description, file list, and tech stack to reflect Damso with Qwen3-ASR.

**Step 3: Update run.sh**

Replace banner/comments from "Mallo Local" to "Damso".

**Step 4: Commit**

```bash
git add README.md CLAUDE_CODE_HANDOFF.md run.sh
git commit -m "docs: update README and handoff docs for Damso v1.0"
```

---

### Task 8: Full integration test

**Step 1: Run the app from terminal**

```bash
cd /Users/Sung_Book/Downloads/mallo_custom/mallo_local
source .venv/bin/activate
python3 app.py
```

**Step 2: Verify checklist**

- [ ] App starts without errors
- [ ] Menu bar icon appears
- [ ] Qwen3-ASR model loads (check log: `"✅ Qwen3-ASR model loaded"`)
- [ ] Notification shows "Damso - 준비 완료"
- [ ] Hold Fn key → recording starts (log: `"🔴 Recording started"`)
- [ ] Release Fn key → transcription completes in <1s (log: `"✅ Transcription done in 0.XXs"`)
- [ ] Text inserts at cursor position
- [ ] Settings UI opens and shows "Damso" branding
- [ ] Engine selector shows Qwen3-ASR selected

**Step 3: Check branding**

```bash
grep -r "Mallo" app.py config.py stt.py settings_ui.py build_app.sh run.sh
```

Expected: No results (all references should be updated to Damso).
Exception: `CLAUDE_CODE_HANDOFF.md` may mention "formerly Mallo Local" — that's fine.

**Step 4: Commit if any fixes needed**

```bash
git add -A
git commit -m "fix: integration test fixes for Damso v1.0"
```

---

### Task 9: Build .app bundle

**Step 1: Build the app**

```bash
cd /Users/Sung_Book/Downloads/mallo_custom/mallo_local
bash build_app.sh
```

Answer `y` when asked to install to /Applications.

**Step 2: Verify .app bundle**

- [ ] `Damso.app` exists in `dist/` or `/Applications/`
- [ ] Double-click to launch → menu bar icon appears
- [ ] Grant Accessibility + Microphone permissions
- [ ] Hold-to-speak works from .app bundle

**Step 3: Final commit**

```bash
git add -A
git commit -m "release: Damso v1.0 — Qwen3-ASR MLX local STT app"
```
