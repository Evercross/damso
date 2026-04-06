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
import logging
import soundfile as sf

log = logging.getLogger("damso")
HF_CACHE_DIR = os.path.expanduser("~/.cache/huggingface/hub")


def _coerce_device_config(value):
    """Normalize persisted input-device config to 'default' or integer index string."""
    if value is None:
        return "default"
    text = str(value).strip()
    if not text or text.lower() == "default":
        return "default"
    try:
        idx = int(text)
        if idx >= 0:
            return str(idx)
    except (TypeError, ValueError):
        pass
    return "default"


def _get_default_input_index():
    """Get default input device index from sounddevice, if available."""
    candidate = None
    try:
        default_device = sd.default.device
        if isinstance(default_device, (list, tuple)) and len(default_device) >= 1:
            idx = default_device[0]
            if idx is not None and int(idx) >= 0:
                candidate = int(idx)
        elif isinstance(default_device, int) and default_device >= 0:
            candidate = int(default_device)
    except Exception:
        candidate = None

    if candidate is not None:
        try:
            dev = sd.query_devices(candidate)
            if int(dev.get("max_input_channels", 0)) > 0:
                return candidate
        except Exception:
            pass

    # Fallback by matching default input device name.
    try:
        default_input = sd.query_devices(kind="input")
        default_name = str(default_input.get("name", "")).strip()
        if default_name:
            for idx, dev in enumerate(sd.query_devices()):
                if int(dev.get("max_input_channels", 0)) <= 0:
                    continue
                if str(dev.get("name", "")).strip() == default_name:
                    return idx
    except Exception:
        pass
    return None


def list_input_devices():
    """List available audio input devices for settings UI."""
    devices = []
    try:
        try:
            sd.default.reset()
        except Exception:
            pass
        default_idx = _get_default_input_index()
        for idx, dev in enumerate(sd.query_devices()):
            if int(dev.get("max_input_channels", 0)) <= 0:
                continue
            name = str(dev.get("name", f"Input {idx}"))
            samplerate = int(dev.get("default_samplerate", 0))
            label = f"{name} ({samplerate}Hz)"
            if default_idx is not None and idx == default_idx:
                label += " [System Default]"
            devices.append(
                {
                    "id": str(idx),
                    "name": name,
                    "label": label,
                    "is_default": bool(default_idx is not None and idx == default_idx),
                }
            )
    except Exception as exc:
        log.warning(f"[STT] Failed to enumerate input devices: {exc}")
    return devices


def _is_hf_repo_model(model_name):
    """Return True when model_name looks like a Hugging Face repo id."""
    text = str(model_name or "").strip()
    if "/" not in text:
        return False
    parts = text.split("/")
    return len(parts) == 2 and all(parts)


def _read_hf_cached_main_revision(repo_id):
    """Read locally cached 'main' revision for a Hugging Face model."""
    safe_repo = repo_id.replace("/", "--")
    ref_path = os.path.join(HF_CACHE_DIR, f"models--{safe_repo}", "refs", "main")
    if not os.path.exists(ref_path):
        return None
    try:
        with open(ref_path, "r", encoding="utf-8") as f:
            value = f.read().strip()
            return value or None
    except Exception:
        return None


def get_model_update_info(engine, model_name):
    """Check whether a newer upstream model revision exists."""
    engine = str(engine or "").strip().lower()
    model_name = str(model_name or "").strip()
    base = {
        "ok": False,
        "supported": False,
        "engine": engine,
        "model_name": model_name,
        "latest_revision": None,
        "cached_revision": None,
        "update_available": False,
        "message": "",
    }

    if engine != "qwen3-asr" and not _is_hf_repo_model(model_name):
        base["message"] = "현재는 Hugging Face 기반 모델만 업데이트 확인을 지원합니다."
        return base

    if not _is_hf_repo_model(model_name):
        base["message"] = "모델 형식이 Hugging Face 리포지토리 형식이 아닙니다."
        return base

    base["supported"] = True
    base["cached_revision"] = _read_hf_cached_main_revision(model_name)

    try:
        from huggingface_hub import HfApi

        latest = HfApi().model_info(model_name, revision="main").sha
    except Exception as exc:
        base["message"] = f"최신 버전 확인 실패: {exc}"
        return base

    base["ok"] = True
    base["latest_revision"] = latest
    cached = base["cached_revision"]
    base["update_available"] = (cached != latest)

    if cached is None:
        base["message"] = "로컬 캐시가 없어 첫 다운로드가 필요합니다."
    elif base["update_available"]:
        base["message"] = "새 모델 리비전이 있습니다."
    else:
        base["message"] = "이미 최신 리비전입니다."
    return base


def update_model_cache(engine, model_name):
    """Download/update model snapshot from Hugging Face main revision."""
    info = get_model_update_info(engine, model_name)
    if not info.get("supported"):
        return info
    if not info.get("ok"):
        return info
    if not info.get("update_available") and info.get("cached_revision"):
        result = dict(info)
        result["updated"] = False
        result["snapshot_path"] = None
        result["message"] = "이미 최신 리비전입니다."
        return result

    before = info.get("cached_revision")
    latest = info.get("latest_revision")
    result = dict(info)
    result["updated"] = False
    result["snapshot_path"] = None

    try:
        from huggingface_hub import snapshot_download

        snapshot_path = snapshot_download(
            repo_id=model_name,
            revision="main",
            local_files_only=False,
        )
    except Exception as exc:
        result["ok"] = False
        result["message"] = f"모델 업데이트 다운로드 실패: {exc}"
        return result

    after = _read_hf_cached_main_revision(model_name)
    result["cached_revision"] = after
    result["snapshot_path"] = snapshot_path
    result["updated"] = (before != after) and (after == latest)
    result["update_available"] = (after != latest)
    result["ok"] = True

    if result["updated"]:
        result["message"] = "모델이 최신 리비전으로 업데이트되었습니다."
    elif after == latest:
        result["message"] = "이미 최신 리비전입니다."
    else:
        result["message"] = "다운로드는 완료됐지만 최신 리비전 확인이 필요합니다."
    return result


class STTEngine:
    """Local STT engine with pluggable backends.

    Default: Qwen3-ASR via mlx-qwen3-asr (Apple Silicon GPU)
    Fallback: Whisper via faster-whisper (CPU)
    """

    def __init__(
        self,
        engine="qwen3-asr",
        model_name=None,
        language="ko",
        sample_rate=16000,
        min_audio_seconds=0.30,
        input_device="default",
    ):
        self.engine = engine
        self.language = language
        self.sample_rate = sample_rate
        self.min_audio_seconds = self._coerce_min_audio_seconds(min_audio_seconds)
        self.input_device = _coerce_device_config(input_device)
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

    @staticmethod
    def _coerce_min_audio_seconds(value):
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            parsed = 0.30
        return max(0.15, min(1.50, parsed))

    @staticmethod
    def _find_device_name(index):
        try:
            dev = sd.query_devices(index)
            return str(dev.get("name", f"#{index}"))
        except Exception:
            return f"#{index}"

    def _resolve_input_device(self):
        """Resolve configured input device for stream creation."""
        value = _coerce_device_config(self.input_device)
        self.input_device = value

        if value == "default":
            try:
                # Re-sync PortAudio defaults so system input changes apply immediately.
                sd.default.reset()
            except Exception:
                pass
            idx = _get_default_input_index()
            if idx is None:
                return None, "System Default (unresolved)"
            return idx, f"System Default -> {self._find_device_name(idx)} (#{idx})"

        try:
            idx = int(value)
        except (TypeError, ValueError):
            return None, "System Default (invalid config fallback)"

        try:
            dev = sd.query_devices(idx)
            if int(dev.get("max_input_channels", 0)) <= 0:
                raise ValueError("selected device has no input channels")
            name = str(dev.get("name", f"#{idx}"))
            return idx, f"{name} (#{idx})"
        except Exception as exc:
            log.warning(
                f"[STT] Configured input device #{idx} unavailable, fallback to default: {exc}"
            )
            return None, "System Default (fallback)"

    def load_model(self):
        """Load the STT model. Call once at startup."""
        if self.engine == "qwen3-asr":
            self._load_qwen()
        else:
            self._load_whisper()

    def _load_qwen(self):
        """Load Qwen3-ASR model via mlx-qwen3-asr Session API."""
        log.info(f"[STT] Loading Qwen3-ASR model: {self.model_name}...")
        from mlx_qwen3_asr import Session
        self._session = Session(model=self.model_name)
        log.info("[STT] Qwen3-ASR model loaded successfully.")

    def _load_whisper(self):
        """Load Whisper model via faster-whisper (CPU fallback)."""
        log.info(f"[STT] Loading Whisper model: {self.model_name}...")
        from faster_whisper import WhisperModel
        self._whisper_model = WhisperModel(
            self.model_name,
            device="cpu",
            compute_type="int8",
        )
        log.info("[STT] Whisper model loaded successfully.")

    def start_recording(self):
        """Start capturing audio from microphone."""
        if self.is_recording:
            return

        with self._lock:
            self.audio_buffer = []
            self.is_recording = True

        def audio_callback(indata, frames, time_info, status):
            if status:
                log.warning(f"[STT] Audio status: {status}")
            if self.is_recording:
                self.audio_buffer.append(indata.copy())

        device_idx, device_label = self._resolve_input_device()

        try:
            self._stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=1,
                dtype="float32",
                callback=audio_callback,
                blocksize=1024,
                device=device_idx,
            )
            self._stream.start()
            log.info(f"[STT] Recording started... (input={device_label})")
        except Exception as exc:
            # Fallback once to system default when explicit device failed.
            if device_idx is not None:
                log.warning(
                    f"[STT] Failed to open input device {device_label}: {exc}. "
                    "Retrying with system default."
                )
                self._stream = sd.InputStream(
                    samplerate=self.sample_rate,
                    channels=1,
                    dtype="float32",
                    callback=audio_callback,
                    blocksize=1024,
                    device=None,
                )
                self._stream.start()
                log.info("[STT] Recording started... (input=System Default fallback)")
            else:
                raise

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
            log.info("[STT] No audio recorded.")
            return None

        audio = np.concatenate(self.audio_buffer, axis=0).flatten()
        log.info(f"[STT] Recording stopped. Audio length: {len(audio) / self.sample_rate:.1f}s")
        return audio

    def transcribe(self, audio_data):
        """Transcribe audio data to text."""
        if audio_data is None or len(audio_data) == 0:
            return ""

        duration_sec = len(audio_data) / self.sample_rate
        min_sec = self._coerce_min_audio_seconds(self.min_audio_seconds)
        self.min_audio_seconds = min_sec

        # Minimum audio length check
        if duration_sec < min_sec:
            log.info(
                f"[STT] Audio too short ({duration_sec:.2f}s < {min_sec:.2f}s), skipping."
            )
            return ""

        log.info("[STT] Transcribing...")
        start_time = time.time()

        if self.engine == "qwen3-asr":
            result = self._transcribe_qwen(audio_data)
        else:
            result = self._transcribe_whisper(audio_data)

        elapsed = time.time() - start_time
        log.info(f"[STT] Transcription done in {elapsed:.2f}s")
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

            result = self._session.transcribe(tmp_path, language=self.language)
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
