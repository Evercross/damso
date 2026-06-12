"""
Damso STT Backend — Qwen3-ASR (MLX GPU)

Fast, high-quality speech recognition on Apple Silicon.
"""
import logging
import os
import tempfile

import gc
import soundfile as sf
import mlx.core as mx

from . import register

log = logging.getLogger("damso")


@register
class QwenBackend:
    name = "qwen3-asr"
    display_name = "Qwen3-ASR (MLX GPU)"
    default_model = "Qwen/Qwen3-ASR-1.7B"
    config_model_key = "qwen_model"
    models = [
        {"id": "Qwen/Qwen3-ASR-1.7B", "label": "Qwen3-ASR-1.7B — Best quality"},
        {"id": "Qwen/Qwen3-ASR-0.6B", "label": "Qwen3-ASR-0.6B — Lighter"},
    ]

    def __init__(self):
        self._session = None

    def load_model(self, model_name: str) -> None:
        log.info(f"[STT] Loading Qwen3-ASR model: {model_name}...")
        from mlx_qwen3_asr import Session
        self._session = Session(model=model_name)
        log.info("[STT] Qwen3-ASR model loaded successfully.")
        try:
            import mlx.core as mx
            mx.set_cache_limit(1024 * 1024 * 1024)  # 1GB cache limit
            log.info("[STT] MLX cache limit set to 1GB")
        except Exception as e:
            log.warning(f"[STT] Could not set MLX cache limit: {e}")

    def transcribe(self, audio_data, language: str, sample_rate: int) -> str:
        if self._session is None:
            raise RuntimeError("Qwen3-ASR model not loaded. Call load_model() first.")

        tmp_path = None
        try:
            tmp_fd, tmp_path = tempfile.mkstemp(suffix=".wav")
            os.close(tmp_fd)
            sf.write(tmp_path, audio_data, sample_rate)
            result = self._session.transcribe(tmp_path, language=language)
            return result.text.strip() if result.text else ""
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.remove(tmp_path)
            try:
                mx.clear_cache()
            except Exception:
                pass
            gc.collect()
