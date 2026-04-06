"""
Damso (담소) - Main Application
macOS menu bar app for voice-to-text input at cursor position.

Usage:
    python app.py              # Main app
    python app.py --settings   # Settings window only

Hotkeys:
    - Right Option: Hold to speak, release to insert (recommended)
    - Fn (Globe): Hold to speak, release to insert
    - Mouse side buttons: Hold to speak, release to insert
    - Ctrl+Shift+M: Toggle dictation (fallback hotkey)
"""
import rumps
import threading
import time
import os
import sys
import atexit
import logging
import logging.handlers
import fcntl
import re
import subprocess
import queue
import signal

# Settings window is launched as a separate process with this flag.
SETTINGS_MODE = "--settings" in sys.argv

# Paths
RESOURCE_DIR = os.path.dirname(os.path.abspath(__file__))
_DATA_DIR = os.path.expanduser("~/.damso")
os.makedirs(_DATA_DIR, exist_ok=True)
LOG_FILE = os.path.join(_DATA_DIR, "damso.log")

def _notify_already_running():
    """Handle duplicate launch quietly to avoid repeated notification spam."""
    print("[Damso] Duplicate launch ignored (already running).")


def _release_instance_lock():
    """Release the singleton lock safely."""
    global _lock_fd
    try:
        if "_lock_fd" in globals() and _lock_fd:
            try:
                fcntl.flock(_lock_fd, fcntl.LOCK_UN)
            except Exception:
                pass
            _lock_fd.close()
            _lock_fd = None
    except Exception:
        pass


def _acquire_instance_lock(lock_file, retries=100, retry_interval=0.1):
    """Acquire singleton lock with a short retry window for restart races."""
    global _lock_fd
    os.makedirs(os.path.dirname(lock_file), exist_ok=True)
    open_flags = os.O_RDWR | os.O_CREAT
    if hasattr(os, "O_CLOEXEC"):
        open_flags |= os.O_CLOEXEC
    raw_fd = os.open(lock_file, open_flags, 0o644)
    try:
        os.set_inheritable(raw_fd, False)
    except Exception:
        pass
    _lock_fd = os.fdopen(raw_fd, "a+")

    for _ in range(retries + 1):
        try:
            fcntl.flock(_lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            _lock_fd.seek(0)
            _lock_fd.truncate()
            _lock_fd.write(str(os.getpid()))
            _lock_fd.flush()
            try:
                os.fsync(_lock_fd.fileno())
            except Exception:
                pass
            atexit.register(_release_instance_lock)
            return True
        except BlockingIOError:
            time.sleep(retry_interval)
        except IOError:
            time.sleep(retry_interval)

    return False


# ── Single instance lock ──
# Skip lock in settings-only process so the main app can open the settings window.
if not SETTINGS_MODE:
    # Prevents multiple Damso instances from running simultaneously.
    # Each instance loads a ~4GB model; duplicates exhaust memory and freeze the Mac.
    _LOCK_FILE = os.path.join(os.path.expanduser("~/.damso"), "damso.lock")
    _lock_fd = None
    if not _acquire_instance_lock(_LOCK_FILE):
        # Another instance is already running — quit silently
        print("[Damso] Already running. Exiting duplicate instance.")
        _notify_already_running()
        sys.exit(0)

sys.path.insert(0, RESOURCE_DIR)

# ── Logging: RotatingFileHandler (10MB, 5 backups) + stdout ──
_log_handlers: list[logging.Handler] = [
    logging.handlers.RotatingFileHandler(
        LOG_FILE, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8",
    ),
]
if sys.stdout is not None and hasattr(sys.stdout, "write"):
    _log_handlers.append(logging.StreamHandler(sys.stdout))
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=_log_handlers,
)
log = logging.getLogger("damso")
if not SETTINGS_MODE:
    log.info("=== Damso starting ===")

# ── Hide from Dock (show only in menu bar) ──
# Only for the main process; settings subprocess needs normal termination.
if not SETTINGS_MODE:
    try:
        from AppKit import NSApplication, NSApplicationActivationPolicyAccessory
        app = NSApplication.sharedApplication()
        app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
    except ImportError:
        pass

    try:
        from Foundation import NSProcessInfo
        NSProcessInfo.processInfo().disableAutomaticTermination_("Damso is a menu bar app")
        NSProcessInfo.processInfo().disableSuddenTermination()
    except Exception:
        pass

from stt import STTEngine, update_model_cache
from dictionary import Dictionary
from history import HistoryManager
from text_inserter import TextInserter
from config import load_config, save_config
from diagnostics import generate_diagnostics_report
from permissions import (
    get_permission_state,
    is_accessibility_trusted,
    open_accessibility_settings,
    open_automation_settings,
    prompt_accessibility_permission,
)


class DamsoApp(rumps.App):
    """Damso - macOS menu bar dictation app."""

    def __init__(self):
        # Try to use custom menu bar icon
        icon_path = os.path.join(RESOURCE_DIR, "icon_menubar.png")
        if not os.path.exists(icon_path):
            icon_path = None

        super().__init__(
            "Damso",
            icon=icon_path,
            title=None if icon_path else "Damso",
            quit_button=None,
            template=icon_path is not None,  # Template mode only with actual icon
        )

        # Load config
        self.config = load_config()

        # Initialize components
        self.stt = STTEngine(
            engine=self.config.get("stt_engine", "qwen3-asr"),
            model_name=(
                self.config.get("qwen_model") if self.config.get("stt_engine") == "qwen3-asr"
                else self.config.get("whisper_model")
            ),
            language=self.config["language"],
            sample_rate=self.config["sample_rate"],
            min_audio_seconds=self.config.get("min_audio_seconds", 0.30),
            input_device=self.config.get("audio_input_device", "default"),
        )
        self.dictionary = Dictionary()
        self.history = HistoryManager(
            retention_days=self.config["history_retention_days"]
        )
        self.inserter = TextInserter(method=self.config.get("insert_method", "stable"))

        # State
        self.is_dictating = False
        self.is_model_loaded = False
        self.is_loading_model = False
        self._recording_start_time = None
        self._dictation_target_app = None
        self._last_accessibility_notice_ts = 0.0
        self._last_empty_notice_ts = 0.0
        self._last_permission_notice_ts = 0.0
        self._last_permission_state = None
        self._hotkey_listener_lock = threading.Lock()
        self._hotkey_listener_running = False

        # Serialize hotkey callbacks to preserve start/stop ordering.
        self._hotkey_action_queue = queue.SimpleQueue()
        self._hotkey_worker = threading.Thread(
            target=self._process_hotkey_actions,
            daemon=True,
        )
        self._hotkey_worker.start()

        # Build menu
        self._build_menu()

        # Load model in background
        self._load_model_async()

        # On first launch (or after re-build), proactively trigger the native
        # Accessibility prompt so the user sees the system dialog immediately.
        # For ad-hoc signed apps the prompt may be silently ignored by macOS;
        # prompt_accessibility_permission() will fall back to opening System Settings.
        if not is_accessibility_trusted():
            log.info("[App] Accessibility not trusted at startup — prompting user.")
            prompt_accessibility_permission()

        # Start permission watcher + hotkey listener bootstrap.
        self._start_permission_watcher()
        self._start_hotkey_listener()

    def _build_menu(self):
        """Build the menu bar dropdown menu."""
        self.menu = [
            rumps.MenuItem("모델 로딩 중...", callback=None),
            None,  # separator
            rumps.MenuItem("받아쓰기 시작/중지", callback=self.on_toggle_dictation),
            rumps.MenuItem("텍스트 삽입 테스트", callback=self.on_test_insert),
            rumps.MenuItem("모델 업데이트", callback=self.on_update_model),
            rumps.MenuItem("권한 점검", callback=self.on_check_permissions),
            rumps.MenuItem("손쉬운 사용 설정 열기", callback=self.on_open_accessibility_settings),
            None,
            rumps.MenuItem("설정 열기", callback=self.on_open_settings_ui),
            rumps.MenuItem("진단 리포트 생성", callback=self.on_generate_diagnostics),
            None,
            rumps.MenuItem("종료", callback=self.on_quit),
        ]

    def _build_settings_submenu(self):
        """Build settings submenu."""
        settings = rumps.MenuItem("⚙️ 설정")

        # Model size
        model_menu = rumps.MenuItem("모델 크기")
        for size in ["tiny", "base", "small", "medium", "large-v3"]:
            item = rumps.MenuItem(
                f"{'✓ ' if size == self.config['whisper_model'] else '  '}{size}",
                callback=lambda sender, s=size: self.on_change_model(s),
            )
            model_menu.add(item)
        settings.add(model_menu)

        # Language
        lang_menu = rumps.MenuItem("언어")
        languages = {"ko": "한국어", "en": "English", "ja": "日本語", None: "자동 감지"}
        for code, name in languages.items():
            item = rumps.MenuItem(
                f"{'✓ ' if code == self.config['language'] else '  '}{name}",
                callback=lambda sender, c=code: self.on_change_language(c),
            )
            lang_menu.add(item)
        settings.add(lang_menu)

        # History retention
        retention_menu = rumps.MenuItem("히스토리 보관")
        for days in [7, 14, 30, 90, 365, 0]:
            label = "무기한" if days == 0 else f"{days}일"
            item = rumps.MenuItem(
                f"{'✓ ' if days == self.config['history_retention_days'] else '  '}{label}",
                callback=lambda sender, d=days: self.on_change_retention(d),
            )
            retention_menu.add(item)
        settings.add(retention_menu)

        return settings

    def _load_model_async(self):
        """Load whisper model in background thread."""
        def load():
            self.is_loading_model = True
            try:
                self.stt.load_model()
                self.is_model_loaded = True
                log.info("[App] Model loaded successfully")
            except Exception as e:
                log.info(f"[App] Model load failed: {e}")
                try:
                    if "모델 로딩 중..." in self.menu:
                        self.menu["모델 로딩 중..."].title = f"모델 로드 실패"
                except Exception:
                    pass
                return
            finally:
                self.is_loading_model = False

            # UI updates after successful load (separate try so model stays loaded)
            try:
                self.title = None if self.icon else "Damso"
                if "모델 로딩 중..." in self.menu:
                    self.menu["모델 로딩 중..."].title = "준비 완료"
            except Exception:
                pass
            try:
                engine = self.config.get("stt_engine", "qwen3-asr")
                model_label = self.config.get("qwen_model") if engine == "qwen3-asr" else self.config.get("whisper_model")
                rumps.notification(
                    "Damso",
                    "준비 완료",
                    f"모델({model_label}) 로드 완료",
                )
            except Exception:
                pass

        thread = threading.Thread(target=load, daemon=True)
        thread.start()

    def _start_permission_watcher(self):
        """Watch permission changes and recover hotkeys without app restart."""

        def watch():
            while True:
                try:
                    state = get_permission_state()
                    trusted = bool(state.get("accessibility_trusted"))
                    automation_ok = bool((state.get("system_events") or {}).get("ok"))
                    previous = self._last_permission_state

                    if previous != (trusted, automation_ok):
                        self._last_permission_state = (trusted, automation_ok)
                        log.info(
                            "[Permission] accessibility=%s automation=%s",
                            "ok" if trusted else "missing",
                            "ok" if automation_ok else "blocked",
                        )

                        now = time.time()
                        if (now - self._last_permission_notice_ts) > 12:
                            self._last_permission_notice_ts = now
                            if not trusted:
                                rumps.notification(
                                    "Damso",
                                    "손쉬운 사용 권한 필요",
                                    "메뉴의 '권한 점검'에서 상태 확인 후 허용해주세요.",
                                )

                    # Re-attempt hotkey listener whenever Accessibility is granted,
                    # even if a previous listener thread already exited (it resets the
                    # _hotkey_listener_running flag in its finally block).
                    if trusted and not self._hotkey_listener_running:
                        log.info("[Permission] Accessibility granted — (re)starting hotkey listener.")
                        self._start_hotkey_listener()
                except Exception as exc:
                    log.warning(f"[Permission] watcher failed: {exc}")

                time.sleep(4)

        threading.Thread(target=watch, daemon=True).start()

    def _start_hotkey_listener(self):
        """Start global hotkey listener using Quartz CGEvent tap."""
        with self._hotkey_listener_lock:
            if self._hotkey_listener_running:
                return
            self._hotkey_listener_running = True

        def listen():
            try:
                if not is_accessibility_trusted():
                    log.info("[Hotkey] Accessibility 권한이 없어 리스너 대기 상태로 전환합니다.")
                    return

                import Quartz

                # Modifier flags
                FN_FLAG = 0x800000     # NSEventModifierFlagFunction (kCGEventFlagMaskSecondaryFn)
                CTRL_FLAG = 0x40000    # NSEventModifierFlagControl
                SHIFT_FLAG = 0x20000   # NSEventModifierFlagShift
                OPTION_FLAG = 0x80000  # NSEventModifierFlagOption

                # Right Option key = keycode 61
                RIGHT_OPTION_KEYCODE = 61
                FN_KEYCODE = 63

                fn_was_pressed = False
                fn_release_token = 0
                right_option_down = False
                mouse_button_down = False

                def _get_hold_mode():
                    mode = str(self.config.get("hotkey_hold", "right_option")).strip().lower()
                    if mode in {"fn", "globe"}:
                        return "fn"
                    if mode in {"right_option", "option", "alt"}:
                        return "right_option"
                    if mode in {"both", "fn+option", "option+fn"}:
                        return "both"
                    return "right_option"

                # Mouse side buttons for hold-to-speak:
                # Button 3 = back, Button 4 = forward
                MOUSE_TRIGGER_BUTTONS = {3, 4}
                keyboard_tap = None
                mouse_tap = None
                active_mouse_button = None

                def _async_action(action):
                    """Queue dictation actions off the CGEvent callback thread."""
                    self._hotkey_action_queue.put(action)

                def keyboard_callback(proxy, event_type, event, refcon):
                    nonlocal fn_was_pressed, fn_release_token, right_option_down, mouse_button_down

                    try:
                        # ── Re-enable tap if macOS disabled it (timeout) ──
                        if event_type == Quartz.kCGEventTapDisabledByTimeout:
                            if keyboard_tap is not None:
                                Quartz.CGEventTapEnable(keyboard_tap, True)
                            return event

                        if event_type == Quartz.kCGEventTapDisabledByUserInput:
                            if keyboard_tap is not None:
                                Quartz.CGEventTapEnable(keyboard_tap, True)
                            return event

                        flags = Quartz.CGEventGetFlags(event)

                        # ── Modifier flag changes (Fn, Option, Ctrl, Shift) ──
                        if event_type == Quartz.kCGEventFlagsChanged:
                            keycode = Quartz.CGEventGetIntegerValueField(
                                event, Quartz.kCGKeyboardEventKeycode
                            )

                            # ── Fn (Globe) key detection ──
                            # Only react when the Fn key itself reports a flagsChanged event
                            # to avoid false stop/start from other modifier updates.
                            if keycode == FN_KEYCODE:
                                hold_mode = _get_hold_mode()
                                if hold_mode not in {"fn", "both"}:
                                    return event
                                fn_is_down = bool(flags & FN_FLAG)

                                if fn_is_down and not fn_was_pressed:
                                    fn_was_pressed = True
                                    fn_release_token += 1  # cancel pending release checks
                                    if not self.is_dictating:
                                        _async_action(self._start_dictation)

                                elif not fn_is_down and fn_was_pressed:
                                    fn_was_pressed = False
                                    fn_release_token += 1
                                    release_token = fn_release_token

                                    # Debounce quick Fn flag flicker (observed as ~0.1s false release).
                                    def _stop_after_fn_debounce(token=release_token):
                                        time.sleep(0.08)
                                        if token != fn_release_token:
                                            return
                                        try:
                                            current_flags = Quartz.CGEventSourceFlagsState(
                                                Quartz.kCGEventSourceStateCombinedSessionState
                                            )
                                            if current_flags & FN_FLAG:
                                                return
                                        except Exception:
                                            pass
                                        if self.is_dictating:
                                            self._stop_and_insert()

                                    _async_action(_stop_after_fn_debounce)

                            # ── Right Option key detection (alternative) ──
                            if keycode == RIGHT_OPTION_KEYCODE:
                                hold_mode = _get_hold_mode()
                                if hold_mode not in {"right_option", "both"}:
                                    return event
                                option_is_down = bool(flags & OPTION_FLAG)

                                if option_is_down and not right_option_down:
                                    right_option_down = True
                                    if not self.is_dictating:
                                        _async_action(self._start_dictation)

                                elif not option_is_down and right_option_down:
                                    right_option_down = False
                                    if self.is_dictating:
                                        _async_action(self._stop_and_insert)

                        # ── Regular key presses (Ctrl+Shift+M) ──
                        elif event_type == Quartz.kCGEventKeyDown:
                            keycode = Quartz.CGEventGetIntegerValueField(
                                event, Quartz.kCGKeyboardEventKeycode
                            )
                            # M key = keycode 46
                            if keycode == 46 and (flags & CTRL_FLAG) and (flags & SHIFT_FLAG):
                                _async_action(self._toggle_dictation)

                    except Exception:
                        pass  # Never block the event callback

                    return event

                def mouse_callback(proxy, event_type, event, refcon):
                    nonlocal mouse_button_down, active_mouse_button

                    try:
                        if event_type == Quartz.kCGEventTapDisabledByTimeout:
                            if mouse_tap is not None:
                                Quartz.CGEventTapEnable(mouse_tap, True)
                            return event

                        if event_type == Quartz.kCGEventTapDisabledByUserInput:
                            if mouse_tap is not None:
                                Quartz.CGEventTapEnable(mouse_tap, True)
                            return event

                        if event_type == Quartz.kCGEventOtherMouseDown:
                            button = Quartz.CGEventGetIntegerValueField(
                                event, Quartz.kCGMouseEventButtonNumber
                            )
                            if button in MOUSE_TRIGGER_BUTTONS:
                                if not mouse_button_down:
                                    mouse_button_down = True
                                    active_mouse_button = button
                                    if not self.is_dictating:
                                        _async_action(self._start_dictation)
                                # Consume trigger button event to avoid target-app side effects
                                # (focus shift/navigation by mouse hover position).
                                return None

                        elif event_type == Quartz.kCGEventOtherMouseUp:
                            button = Quartz.CGEventGetIntegerValueField(
                                event, Quartz.kCGMouseEventButtonNumber
                            )
                            if button in MOUSE_TRIGGER_BUTTONS:
                                if mouse_button_down and button == active_mouse_button:
                                    mouse_button_down = False
                                    active_mouse_button = None
                                    if self.is_dictating:
                                        _async_action(self._stop_and_insert)
                                # Consume trigger button release event as well.
                                return None

                    except Exception:
                        # Fail open: pass event through if callback errors.
                        return event

                    return event

                # Keyboard tap: passive listen-only for modifiers + key down.
                keyboard_event_mask = (
                    (1 << Quartz.kCGEventFlagsChanged) |
                    (1 << Quartz.kCGEventKeyDown)
                )

                keyboard_tap = Quartz.CGEventTapCreate(
                    Quartz.kCGSessionEventTap,
                    Quartz.kCGHeadInsertEventTap,
                    Quartz.kCGEventTapOptionListenOnly,  # Passive — never blocks system input
                    keyboard_event_mask,
                    keyboard_callback,
                    None,
                )

                if keyboard_tap is None:
                    log.info("[Hotkey] ❌ Event tap 생성 실패 (권한 상태 확인 필요)")
                    return

                # Mouse tap: active for trigger side-button events only.
                # We consume this button so target apps do not react (focus/navigation side-effects).
                mouse_event_mask = (
                    (1 << Quartz.kCGEventOtherMouseDown) |
                    (1 << Quartz.kCGEventOtherMouseUp)
                )

                mouse_tap = Quartz.CGEventTapCreate(
                    Quartz.kCGSessionEventTap,
                    Quartz.kCGHeadInsertEventTap,
                    Quartz.kCGEventTapOptionDefault,  # Active — required to consume trigger event
                    mouse_event_mask,
                    mouse_callback,
                    None,
                )

                if mouse_tap is None:
                    log.info("[Hotkey] ⚠️ 마우스 사이드 버튼 탭 생성 실패 (Fn/Option 핫키는 동작)")

                # Add taps to run loop
                run_loop_source = Quartz.CFMachPortCreateRunLoopSource(None, keyboard_tap, 0)
                Quartz.CFRunLoopAddSource(
                    Quartz.CFRunLoopGetCurrent(),
                    run_loop_source,
                    Quartz.kCFRunLoopCommonModes,
                )
                Quartz.CGEventTapEnable(keyboard_tap, True)

                if mouse_tap is not None:
                    mouse_run_loop_source = Quartz.CFMachPortCreateRunLoopSource(None, mouse_tap, 0)
                    Quartz.CFRunLoopAddSource(
                        Quartz.CFRunLoopGetCurrent(),
                        mouse_run_loop_source,
                        Quartz.kCFRunLoopCommonModes,
                    )
                    Quartz.CGEventTapEnable(mouse_tap, True)

                log.info("[Hotkey] ✅ 핫키 리스너 활성화됨")
                hold_mode = _get_hold_mode()
                if hold_mode in {"fn", "both"}:
                    log.info("[Hotkey]    🔵 Fn(🌐) 누르고 말하기 → 놓으면 입력")
                if hold_mode in {"right_option", "both"}:
                    log.info("[Hotkey]    🔵 Right Option 누르고 말하기 → 놓으면 입력")
                log.info("[Hotkey]    🔵 마우스 사이드 버튼(뒤/앞) 누르고 말하기 → 놓으면 입력 (앱 전달 차단)")
                log.info("[Hotkey]    🔵 Ctrl+Shift+M → 토글")
                if hold_mode in {"fn", "both"}:
                    log.info("[Hotkey] ⚠️  Fn키가 안 되면:")
                    log.info("[Hotkey]    시스템 설정 → 키보드 → '🌐 키를 누르면' → '입력 소스 변경'으로 설정")
                    log.info("[Hotkey]    (이모지 피커가 설정되어 있으면 Fn 이벤트가 시스템에 잡힘)")

                # Run the loop (blocking)
                Quartz.CFRunLoopRun()

            except ImportError:
                log.info("[Hotkey] ❌ pyobjc가 필요합니다: pip install pyobjc-framework-Quartz pyobjc-framework-Cocoa")
            except Exception as e:
                log.info(f"[Hotkey] Error: {e}")
                import traceback
                traceback.print_exc()
            finally:
                with self._hotkey_listener_lock:
                    self._hotkey_listener_running = False

        thread = threading.Thread(target=listen, daemon=True)
        thread.start()

    def _toggle_dictation(self):
        """Toggle dictation on/off."""
        if self.is_dictating:
            self._stop_and_insert()
        else:
            self._start_dictation()

    def _process_hotkey_actions(self):
        """Process hotkey actions sequentially to avoid start/stop races."""
        while True:
            action = self._hotkey_action_queue.get()
            try:
                action()
            except Exception as exc:
                log.warning(f"[Hotkey] Action failed: {exc}")

    def _refresh_runtime_config(self):
        """Refresh runtime config so settings changes apply without restart."""
        latest = load_config()
        self.config = latest
        self.inserter.method = latest.get("insert_method", "stable")
        self.stt.language = latest.get("language", self.stt.language)
        self.stt.min_audio_seconds = float(
            latest.get("min_audio_seconds", self.stt.min_audio_seconds)
        )
        self.stt.input_device = latest.get("audio_input_device", self.stt.input_device)
        self.history.retention_days = int(latest.get("history_retention_days", 30))
        self.dictionary.reload()

    def _cleanup_text(self, text):
        """Apply lightweight post-processing to transcription text."""
        if not text:
            return text
        if not self.config.get("auto_punctuation", True):
            return text

        # Normalize spaces while preserving line breaks.
        lines = []
        for line in text.splitlines():
            cleaned = re.sub(r"[ \t]+", " ", line.strip())
            cleaned = re.sub(r"\s+([,.;:!?])", r"\1", cleaned)
            lines.append(cleaned)
        result = "\n".join(lines).strip()
        if not result:
            return result

        # Add a closing period only for sentence-like single-line text.
        if (
            "\n" not in result
            and " " in result
            and result[-1] not in ".!?…)]}\"'"
            and re.search(r"[A-Za-z가-힣]", result)
        ):
            result += "."
        return result

    def _start_dictation(self):
        """Start recording."""
        log.info(f"[App] _start_dictation called (model_loaded={self.is_model_loaded}, is_dictating={self.is_dictating})")

        if not self.is_model_loaded:
            log.info("[App] ❌ Model not loaded yet!")
            rumps.notification("Damso", "대기 중", "모델을 아직 로딩 중입니다...")
            return

        if self.is_dictating:
            log.info("[App] ⚠️ Already dictating, ignoring.")
            return

        self._refresh_runtime_config()

        # Capture current target app so insertion can return focus there.
        self._dictation_target_app = self.inserter.get_active_app_info()
        target_name = self._dictation_target_app.get("name", "Unknown")
        target_pid = self._dictation_target_app.get("pid")
        log.info(f"[App] Target app captured: {target_name} (pid={target_pid})")

        self.is_dictating = True
        self._recording_start_time = time.time()
        self.title = " REC"  # Recording indicator
        log.info("[App] 🔴 Recording started!")
        self.stt.start_recording()

    def _stop_and_insert(self):
        """Stop recording, transcribe, apply dictionary, and insert at cursor."""
        log.info(f"[App] _stop_and_insert called (is_dictating={self.is_dictating})")

        if not self.is_dictating:
            log.info("[App] ⚠️ Not dictating, ignoring stop.")
            return

        self.is_dictating = False
        self.title = " ..." if self.icon else "..."  # Processing indicator
        target_app = self._dictation_target_app
        self._dictation_target_app = None

        def process():
            try:
                duration = time.time() - self._recording_start_time if self._recording_start_time else 0
                log.info(f"[App] ⏳ Processing... (recorded {duration:.1f}s)")

                # Transcribe
                raw_text = self.stt.record_and_transcribe()
                log.info(f"[App] 📝 Raw transcription: '{raw_text}'")

                if not raw_text:
                    log.info("[App] ⚠️ No text transcribed (empty result)")
                    now = time.time()
                    if (now - self._last_empty_notice_ts) > 8:
                        self._last_empty_notice_ts = now
                        rumps.notification(
                            "Damso",
                            "인식 결과 없음",
                            "말한 길이가 짧거나 입력이 잡히지 않았어요. 1초 이상 눌러서 다시 시도해 주세요.",
                        )
                    self.title = None if self.icon else "Damso"
                    return

                # Apply dictionary
                processed_text = self.dictionary.apply(raw_text)
                processed_text = self._cleanup_text(processed_text)
                log.info(f"[App] 📖 After dictionary: '{processed_text}'")

                # Restore insertion target app focus if user focus moved during recording.
                current_app = self.inserter.get_active_app_info()
                if (
                    isinstance(target_app, dict)
                    and target_app.get("pid")
                    and current_app.get("pid") != target_app.get("pid")
                ):
                    target_name = target_app.get("name", "Unknown")
                    current_name = current_app.get("name", "Unknown")
                    log.info(
                        f"[App] Focus moved ({target_name} -> {current_name}). Restoring target app..."
                    )
                    restored = self.inserter.activate_app(target_app)
                    if restored:
                        time.sleep(0.12)
                        log.info("[App] Target app focus restored.")
                    else:
                        log.warning("[App] Failed to restore target app focus.")

                app_name = self.inserter.get_active_app_name()
                log.info(f"[App] 🖥️ Active app: {app_name}")

                # Insert at cursor
                log.info("[App] Inserting text at cursor...")
                inserted = self.inserter.insert(processed_text)
                if not inserted and isinstance(target_app, dict) and target_app.get("pid"):
                    # One retry after focus restore for intermittent misses.
                    if self.inserter.activate_app(target_app):
                        time.sleep(0.12)
                        inserted = self.inserter.insert(processed_text)
                if inserted:
                    method_used = self.inserter.last_insert_method or "unknown"
                    log.info(f"[App] Text inserted successfully! (method={method_used})")
                else:
                    log.warning("[App] Text insertion failed.")
                    perm = self.inserter.get_permission_diagnostics()
                    has_accessibility = bool(perm.get("accessibility_trusted"))
                    system_events_ok = bool((perm.get("system_events") or {}).get("ok"))
                    log.warning(
                        "[App] Insertion permission state: accessibility=%s automation=%s",
                        "ok" if has_accessibility else "missing",
                        "ok" if system_events_ok else "blocked",
                    )
                    now = time.time()
                    if (now - self._last_accessibility_notice_ts) > 15:
                        self._last_accessibility_notice_ts = now
                        if not has_accessibility:
                            rumps.notification(
                                "Damso",
                                "손쉬운 사용 권한 필요",
                                "메뉴의 '권한 점검'에서 상태를 확인하고 손쉬운 사용을 허용해주세요.",
                            )
                        elif not system_events_ok:
                            rumps.notification(
                                "Damso",
                                "자동화 권한 필요",
                                "시스템 설정 > 개인정보 보호 및 보안 > 자동화에서 Damso 허용을 확인해주세요.",
                            )

                # Save to history
                self.history.add_entry(
                    raw_text=raw_text,
                    processed_text=processed_text,
                    language=self.config["language"],
                    duration=duration,
                    app_name=app_name,
                )

                # Show notification if enabled
                if self.config["show_notification"]:
                    if inserted:
                        display_text = processed_text[:50] + "..." if len(processed_text) > 50 else processed_text
                        rumps.notification("Damso", f"입력 완료 → {app_name}", display_text)
                    else:
                        rumps.notification(
                            "Damso",
                            "삽입 실패",
                            "손쉬운 사용 권한과 입력 커서 위치, Insert method(stable/cgevent)를 확인해주세요.",
                        )

            except Exception as e:
                log.info(f"[App] ❌ Error during transcription: {e}")
                import traceback
                traceback.print_exc()
                rumps.notification("Damso", "오류", str(e))
            finally:
                self.title = None if self.icon else "Damso"

        thread = threading.Thread(target=process, daemon=True)
        thread.start()

    # ── Menu callbacks ──────────────────────────────────────

    @rumps.clicked("받아쓰기 시작/중지")
    def on_toggle_dictation(self, sender):
        self._toggle_dictation()

    def on_check_permissions(self, sender):
        """Show current permission state and trigger guided recovery when needed."""
        state = get_permission_state()
        trusted = bool(state.get("accessibility_trusted"))
        automation = state.get("system_events") or {}
        automation_ok = bool(automation.get("ok"))

        log.info(
            "[Permission] manual check: accessibility=%s automation=%s",
            "ok" if trusted else "missing",
            "ok" if automation_ok else "blocked",
        )

        if trusted and automation_ok:
            rumps.notification("Damso", "권한 상태 정상", "손쉬운 사용/자동화 권한이 모두 확인되었습니다.")
            return

        # Trigger one explicit native prompt only when user asked for a check.
        if not trusted:
            trusted = bool(prompt_accessibility_permission())
            if not trusted:
                open_accessibility_settings()

        # Automation panel is informative; final consent still comes from macOS prompt.
        if not automation_ok:
            open_automation_settings()

        rumps.notification(
            "Damso",
            "권한 확인 필요",
            "시스템 설정에서 Damso의 손쉬운 사용/자동화 권한을 허용한 뒤 다시 테스트해주세요.",
        )

    def on_open_settings_ui(self, sender):
        """Open the settings UI as a separate process (pywebview needs main thread)."""
        self._terminate_settings_processes()

        app_script = os.path.abspath(__file__)
        log.info("[App] Opening settings UI: %s --settings", app_script)
        subprocess.Popen([sys.executable, app_script, "--settings"])

    def _terminate_settings_processes(self):
        """Terminate stale settings subprocesses so UI always reflects latest build."""
        try:
            result = subprocess.run(
                ["ps", "-Ao", "pid,args"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
        except Exception:
            return

        current_pid = os.getpid()

        killed_pids = []
        for line in (result.stdout or "").splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split(None, 1)
            if len(parts) != 2:
                continue
            try:
                pid = int(parts[0])
            except ValueError:
                continue
            if pid == current_pid:
                continue

            cmd = parts[1]
            settings_related = (
                " --settings" in cmd
                or "settings_ui.py" in cmd
            )
            if not settings_related:
                continue

            try:
                os.kill(pid, signal.SIGTERM)
                killed_pids.append(pid)
            except ProcessLookupError:
                pass
            except Exception:
                pass

        # Give terminated processes a moment to exit before spawning a new one.
        if killed_pids:
            log.info("[App] Terminated stale settings processes: %s", killed_pids)
            time.sleep(0.3)

    def on_generate_diagnostics(self, sender):
        """Generate a local diagnostics report for reproducible troubleshooting."""
        self._refresh_runtime_config()
        rumps.notification("Damso", "진단 리포트", "상태 점검 리포트를 생성 중입니다...")

        def run():
            try:
                result = generate_diagnostics_report(
                    config=self.config,
                    log_file=LOG_FILE,
                    log_tail_lines=180,
                )
                rumps.notification(
                    "Damso",
                    "진단 리포트 완료",
                    result.get("path", "~/.damso/diagnostics"),
                )
            except Exception as exc:
                log.warning(f"[App] Diagnostics report failed: {exc}")
                rumps.notification("Damso", "진단 리포트 실패", str(exc))

        threading.Thread(target=run, daemon=True).start()

    def on_open_accessibility_settings(self, sender):
        """Open Accessibility settings pane on demand."""
        open_accessibility_settings()

    def on_test_insert(self, sender):
        """Test text insertion without recording — verifies the paste pipeline works."""
        log.info("[Test] 텍스트 삽입 테스트 시작...")
        log.info("[Test] 3초 후에 커서 위치에 테스트 텍스트를 입력합니다.")
        log.info("[Test] 텍스트 에디터를 열고 커서를 놓아주세요!")

        def do_test():
            time.sleep(3)  # Give user time to click into a text field
            test_text = "안녕하세요! Damso 테스트입니다."
            log.info(f"[Test] Inserting: '{test_text}'")
            self._refresh_runtime_config()

            app_name = self.inserter.get_active_app_name()
            log.info(f"[Test] Active app: {app_name}")

            inserted = self.inserter.insert(test_text)
            if inserted:
                log.info("[Test] ✅ 텍스트 삽입 완료!")
                rumps.notification("Damso", "테스트 완료", f"'{test_text}' → {app_name}")
            else:
                perm = self.inserter.get_permission_diagnostics()
                log.warning(
                    "[Test] permission state: accessibility=%s automation=%s",
                    "ok" if perm.get("accessibility_trusted") else "missing",
                    "ok" if (perm.get("system_events") or {}).get("ok") else "blocked",
                )
                log.warning("[Test] ❌ 텍스트 삽입 실패")
                rumps.notification(
                    "Damso",
                    "테스트 실패",
                    "메뉴의 '권한 점검' 실행 후 Insert method(stable/cgevent)로 다시 테스트해주세요.",
                )

        thread = threading.Thread(target=do_test, daemon=True)
        thread.start()

    def on_update_model(self, sender):
        """Check/download the latest model revision for the current engine model."""
        self._refresh_runtime_config()
        engine = self.config.get("stt_engine", "qwen3-asr")
        model_name = (
            self.config.get("qwen_model")
            if engine == "qwen3-asr"
            else self.config.get("whisper_model")
        )

        rumps.notification(
            "Damso",
            "모델 업데이트",
            f"최신 모델을 확인 중입니다: {model_name}",
        )

        def run():
            try:
                result = update_model_cache(engine, model_name)
                if not result.get("supported"):
                    rumps.notification(
                        "Damso",
                        "모델 업데이트 미지원",
                        result.get("message", "현재 모델 형식은 자동 업데이트를 지원하지 않습니다."),
                    )
                    return
                if not result.get("ok"):
                    rumps.notification(
                        "Damso",
                        "모델 업데이트 실패",
                        result.get("message", "모델 업데이트 중 오류가 발생했습니다."),
                    )
                    return

                latest = str(result.get("latest_revision") or "")
                short_latest = latest[:8] if latest else "unknown"
                if result.get("updated"):
                    rumps.notification(
                        "Damso",
                        "모델 업데이트 완료",
                        f"{model_name} ({short_latest})\n앱 재시작 후 반영됩니다.",
                    )
                else:
                    rumps.notification(
                        "Damso",
                        "모델 최신 상태",
                        result.get("message", "이미 최신 리비전입니다."),
                    )
            except Exception as exc:
                log.warning(f"[App] Model update failed: {exc}")
                rumps.notification("Damso", "모델 업데이트 실패", str(exc))

        threading.Thread(target=run, daemon=True).start()

    def on_open_dictionary(self, sender):
        """Show dictionary terms in a window."""
        terms = self.dictionary.get_all_terms()
        user_terms = self.dictionary.get_user_terms()

        msg = "=== 활성 용어 사전 ===\n\n"
        msg += f"총 {len(terms)}개 용어\n\n"

        if user_terms:
            msg += "── 사용자 용어 ──\n"
            for src, tgt in sorted(user_terms.items()):
                msg += f"  {src} → {tgt}\n"
            msg += "\n"

        msg += "── 프리셋 용어 (일부) ──\n"
        preset_terms = {k: v for k, v in terms.items() if k not in user_terms}
        for i, (src, tgt) in enumerate(sorted(preset_terms.items())):
            if i >= 20:
                msg += f"  ... 외 {len(preset_terms) - 20}개\n"
                break
            msg += f"  {src} → {tgt}\n"

        # Add user term via dialog
        response = rumps.alert(
            title="용어 사전",
            message=msg,
            ok="닫기",
            other="용어 추가",
        )

        if response == 0:  # "용어 추가" clicked
            window = rumps.Window(
                message="추가할 용어를 입력하세요 (형식: 원본→대체)\n예: 버셀→Vercel",
                title="용어 추가",
                ok="추가",
                cancel="취소",
            )
            resp = window.run()
            if resp.clicked and "→" in resp.text:
                parts = resp.text.split("→", 1)
                if len(parts) == 2:
                    src, tgt = parts[0].strip(), parts[1].strip()
                    self.dictionary.add_user_term(src, tgt)
                    rumps.notification("Damso", "용어 추가됨", f"{src} → {tgt}")

    def on_open_history(self, sender):
        """Show recent history."""
        entries = self.history.get_recent(20)
        total = self.history.count()

        if not entries:
            rumps.alert("히스토리", "아직 기록이 없습니다.")
            return

        msg = f"=== 최근 기록 ({total}개 중 최근 20개) ===\n\n"
        for entry in entries:
            ts = entry["timestamp"][:16].replace("T", " ")
            app = entry["app_name"] or "?"
            text = entry["processed_text"][:60]
            msg += f"[{ts}] ({app})\n  {text}\n\n"

        response = rumps.alert(
            title="히스토리",
            message=msg,
            ok="닫기",
            other="전체 삭제",
        )

        if response == 0:  # "전체 삭제"
            confirm = rumps.alert("확인", "모든 히스토리를 삭제할까요?", ok="삭제", cancel="취소")
            if confirm == 1:
                self.history.clear_all()
                rumps.notification("Damso", "완료", "히스토리가 삭제되었습니다.")

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
        self.title = "Damso"
        self._load_model_async()
        rumps.notification("Damso", "모델 변경", f"{model_size} 모델을 로딩합니다...")

    def on_change_language(self, lang_code):
        """Change recognition language."""
        self.config["language"] = lang_code
        save_config(self.config)
        self.stt.language = lang_code
        lang_name = {"ko": "한국어", "en": "English", "ja": "日本語", None: "자동 감지"}.get(lang_code, lang_code)
        rumps.notification("Damso", "언어 변경", lang_name)

    def on_change_retention(self, days):
        """Change history retention period."""
        self.config["history_retention_days"] = days
        save_config(self.config)
        self.history.retention_days = days
        deleted = self.history.cleanup_old()
        if days <= 0:
            rumps.notification("Damso", "보관 기간 변경", "무기한 보관")
        else:
            rumps.notification("Damso", "보관 기간 변경", f"{days}일 (정리 {deleted}건)")

    def on_quit(self, sender):
        """Clean quit."""
        log.info("[App] 종료 요청됨 — 정리 중...")
        try:
            self.history.cleanup_old()
        except Exception:
            pass
        try:
            self._terminate_settings_processes()
        except Exception:
            pass
        try:
            _release_instance_lock()
        except Exception:
            pass
        log.info("[App] 정리 완료. 종료합니다.")

        # Fallback: ensure process fully exits even if background threads linger.
        # Use a non-daemon thread so it survives even if the main loop exits first.
        def _force_exit():
            time.sleep(1.0)
            os._exit(0)

        t = threading.Thread(target=_force_exit)
        t.daemon = False
        t.start()

        try:
            rumps.quit_application()
        except Exception:
            pass


def main():
    log.info("=" * 50)
    log.info("  Damso (담소) - 타이핑은 그만. 말로 하세요.")
    log.info("=" * 50)
    log.info("  단축키:")
    log.info("    Right Option(권장) 누르고 말하기 → 놓으면 입력")
    log.info("    Fn(🌐) 누르고 말하기 → 놓으면 입력")
    log.info("    마우스 사이드 버튼(뒤/앞) 누르고 말하기 → 놓으면 입력")
    log.info("    Ctrl+Shift+M → 딕테이션 토글")
    log.info("  메뉴바에서 🎤 아이콘을 확인하세요.")

    try:
        log.info("Creating DamsoApp...")
        app = DamsoApp()
        log.info("Starting rumps run loop...")
        app.run()
    except Exception as e:
        log.error(f"App crashed: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    if SETTINGS_MODE:
        from settings_ui import open_settings_window
        open_settings_window()
    else:
        main()
