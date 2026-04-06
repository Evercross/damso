"""
Damso (담소) - Configuration
"""
import os
import json
import copy

# Paths
APP_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.expanduser("~/.damso")
DB_PATH = os.path.join(DATA_DIR, "damso.db")
CONFIG_PATH = os.path.join(DATA_DIR, "config.json")
DICTIONARY_PATH = os.path.join(DATA_DIR, "dictionary.json")

# Ensure data directory exists
os.makedirs(DATA_DIR, exist_ok=True)

# Default configuration
DEFAULT_CONFIG = {
    "stt_engine": "qwen3-asr",       # qwen3-asr or whisper
    "qwen_model": "Qwen/Qwen3-ASR-1.7B",  # Qwen model name
    "whisper_model": "large-v3",      # tiny, base, small, medium, large-v3
    "language": "ko",                  # ko, en, ja, etc. or None for auto-detect
    "hotkey_hold": "right_option",     # fn, right_option, both
    "hotkey_toggle": "fn+space",       # Toggle dictation key
    "sample_rate": 16000,
    "min_audio_seconds": 0.30,         # Minimum recording length to transcribe
    "audio_input_device": "default",   # "default" or device index string
    "history_retention_days": 30,
    "insert_method": "stable",         # stable, auto, cgevent, or applescript
    "show_notification": False,
    "auto_punctuation": True,
}

# Default dictionary presets (dev terms)
DEFAULT_DICTIONARY = {
    "enabled": True,
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

    insert_method = (config.get("insert_method") or "stable").strip().lower()
    if insert_method not in {"stable", "auto", "cgevent", "applescript"}:
        insert_method = "stable"
    config["insert_method"] = insert_method

    hold_mode = str(config.get("hotkey_hold", "right_option")).strip().lower()
    if hold_mode in {"fn", "globe"}:
        hold_mode = "fn"
    elif hold_mode in {"right_option", "option", "alt"}:
        hold_mode = "right_option"
    elif hold_mode in {"both", "fn+option", "option+fn"}:
        hold_mode = "both"
    else:
        hold_mode = "right_option"
    config["hotkey_hold"] = hold_mode

    raw_show_notification = config.get("show_notification", False)
    if isinstance(raw_show_notification, str):
        config["show_notification"] = raw_show_notification.strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
    else:
        config["show_notification"] = bool(raw_show_notification)

    try:
        min_audio_seconds = float(config.get("min_audio_seconds", 0.30))
    except (TypeError, ValueError):
        min_audio_seconds = 0.30
    # Clamp to a safe/meaningful range.
    config["min_audio_seconds"] = max(0.15, min(1.50, round(min_audio_seconds, 2)))

    audio_input = str(config.get("audio_input_device", "default")).strip()
    if not audio_input or audio_input.lower() == "default":
        config["audio_input_device"] = "default"
    else:
        try:
            idx = int(audio_input)
            config["audio_input_device"] = str(idx) if idx >= 0 else "default"
        except (TypeError, ValueError):
            config["audio_input_device"] = "default"

    return config


def save_config(config):
    """Save configuration to file."""
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def load_dictionary():
    """Load dictionary from file, creating defaults if needed."""
    if os.path.exists(DICTIONARY_PATH):
        with open(DICTIONARY_PATH, "r", encoding="utf-8") as f:
            saved = json.load(f)
            merged = copy.deepcopy(DEFAULT_DICTIONARY)

            if isinstance(saved.get("enabled"), bool):
                merged["enabled"] = saved["enabled"]

            if isinstance(saved.get("presets"), dict):
                for preset_name, preset_terms in saved["presets"].items():
                    if isinstance(preset_terms, dict):
                        merged["presets"][preset_name] = preset_terms

            if isinstance(saved.get("user_terms"), dict):
                merged["user_terms"] = saved["user_terms"]

            if isinstance(saved.get("enabled_presets"), list):
                merged["enabled_presets"] = saved["enabled_presets"]

            return merged
    else:
        save_dictionary(DEFAULT_DICTIONARY)
        return copy.deepcopy(DEFAULT_DICTIONARY)


def save_dictionary(dictionary):
    """Save dictionary to file."""
    with open(DICTIONARY_PATH, "w", encoding="utf-8") as f:
        json.dump(dictionary, f, ensure_ascii=False, indent=2)
