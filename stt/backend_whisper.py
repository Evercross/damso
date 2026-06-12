"""
Damso STT Backend — Whisper (faster-whisper, CPU)

Fallback engine using OpenAI Whisper via faster-whisper.
"""
import logging

from . import register

log = logging.getLogger("damso")


@register
class WhisperBackend:
    name = "whisper"
    display_name = "Whisper (CPU)"
    default_model = "large-v3"
    config_model_key = "whisper_model"
    models = [
        {"id": "tiny", "label": "Tiny — Fastest"},
        {"id": "base", "label": "Base — Fast"},
        {"id": "small", "label": "Small — Balanced"},
        {"id": "medium", "label": "Medium �� Accurate"},
        {"id": "large-v3", "label": "Large V3 — Best quality"},
    ]

    def __init__(self):
        self._model = None

    def load_model(self, model_name: str) -> None:
        log.info(f"[STT] Loading Whisper model: {model_name}...")
        from faster_whisper import WhisperModel
        self._model = WhisperModel(
            model_name,
            device="cpu",
            compute_type="int8",
        )
        log.info("[STT] Whisper model loaded successfully.")

    def transcribe(self, audio_data, language: str, sample_rate: int) -> str:
        if self._model is None:
            raise RuntimeError("Whisper model not loaded. Call load_model() first.")

        segments, info = self._model.transcribe(
            audio_data,
            language=language,
            beam_size=5,
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=500),
        )

        text_parts = []
        for segment in segments:
            text_parts.append(segment.text.strip())

        return " ".join(text_parts).strip()
