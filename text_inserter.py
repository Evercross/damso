"""
Damso - Text Inserter
Inserts transcribed text at the current cursor position in any app.
Uses clipboard + Cmd+V simulation with multiple fallback paths.
"""
import logging
import subprocess
import time

from permissions import is_accessibility_trusted, probe_system_events_permission

log = logging.getLogger("damso")


class TextInserter:
    """Insert text at the current cursor position via clipboard + paste shortcut."""

    _CMD_KEYCODE = 55
    _V_KEYCODE = 9
    _APPS_PREFER_TYPING = {
        "Codex",
        "Claude",
        "Claude Code",
        "Microsoft Edge",
        "KakaoTalk",
        "카카오톡",
    }
    _BUNDLES_PREFER_TYPING = {
        "com.microsoft.edgemac",
        "com.kakao.kakaotalkmac",
    }
    _APPS_NEED_SLOW_CLIPBOARD_RESTORE = {
        "KakaoTalk",
        "카카오톡",
    }
    _BUNDLES_NEED_SLOW_CLIPBOARD_RESTORE = {
        "com.kakao.kakaotalkmac",
    }

    def __init__(self, method="stable"):
        """
        Args:
            method: "stable"(recommended), "auto", "cgevent", or "applescript".
        """
        self.method = method
        self.last_insert_method = None

    def get_permission_diagnostics(self):
        """Return insertion-relevant permission state."""
        return {
            "accessibility_trusted": self._has_accessibility_permission(),
            "system_events": probe_system_events_permission(),
        }

    def insert(self, text):
        """Insert text at the current cursor position.

        Returns:
            bool: True when insertion command succeeded, False otherwise.
        """
        if not text:
            return False

        method = (self.method or "stable").strip().lower()
        if method not in {"stable", "auto", "cgevent", "applescript"}:
            method = "stable"

        app_info = self.get_active_app_info()
        app_name = (app_info.get("name") or "").strip()
        if not app_name or app_name.lower() == "unknown":
            app_name = self.get_active_app_name()
        bundle_id = (app_info.get("bundle_id") or "").strip()
        log.info(
            f"[Inserter] Target app detected: name='{app_name}', bundle='{bundle_id or '-'}'"
        )
        strategies = self._build_strategy(method, app_name, bundle_id)
        return self._run_strategy(text, app_name, bundle_id, strategies)

    @classmethod
    def _is_typing_first_app(cls, app_name, bundle_id):
        bundle_id = (bundle_id or "").lower()
        if app_name in cls._APPS_PREFER_TYPING:
            return True
        if bundle_id in cls._BUNDLES_PREFER_TYPING:
            return True
        return "kakaotalk" in (app_name or "").lower()

    def _build_strategy(self, method, app_name, bundle_id):
        """Build ordered insertion strategy list based on mode/app."""
        names = []
        typing_first = self._is_typing_first_app(app_name, bundle_id)

        if method == "applescript":
            names = ["applescript", "cgevent", "unicode"]
        elif method == "stable":
            # Stable mode keeps paste-first and includes AppleScript fallback.
            names = ["cgevent", "applescript", "unicode"]
        elif method == "cgevent":
            names = ["cgevent", "applescript", "unicode"]
        else:
            # Auto keeps one app-specific tweak for known typing-first apps.
            if typing_first:
                names = ["unicode", "applescript", "cgevent"]
            else:
                names = ["cgevent", "applescript", "unicode"]

        ordered = []
        for name in names:
            if name not in ordered:
                ordered.append(name)
        return ordered

    def _run_strategy(self, text, app_name, bundle_id, strategies):
        """Try insertion methods in order until one succeeds."""
        self.last_insert_method = None
        ordered = list(strategies)
        accessibility = self._has_accessibility_permission()
        automation = None

        # If Accessibility is missing, try AppleScript first as it can still work
        # when the app has Automation permission for System Events.
        if not accessibility:
            automation = probe_system_events_permission()
            if not automation.get("ok"):
                log.warning(
                    "[Inserter] Permission state: accessibility=missing, automation=blocked (code=%s)",
                    automation.get("code"),
                )
            if "applescript" in ordered:
                ordered = ["applescript"] + [s for s in ordered if s != "applescript"]
            else:
                ordered = ["applescript"] + ordered

        for name in ordered:
            if name == "applescript" and automation is not None and not automation.get("ok"):
                # Skip AppleScript when Automation is explicitly denied (error 1002).
                # However, if the code is None (unknown error), still attempt it.
                if automation.get("code") == 1002:
                    log.info("[Inserter] Strategy 'applescript' skipped (Automation explicitly denied, code=1002)")
                    continue
            try:
                if name == "unicode":
                    ok = self._insert_via_unicode_typing(text)
                elif name == "cgevent":
                    ok = self._insert_via_cgevent(text, app_name, bundle_id)
                else:
                    ok = self._insert_via_applescript(text, app_name, bundle_id)
            except Exception as exc:
                ok = False
                log.warning(f"[Inserter] Strategy '{name}' crashed: {exc}")

            if ok:
                self.last_insert_method = name
                log.info(f"[Inserter] Strategy '{name}' succeeded for app '{app_name}'")
                return True
            log.info(f"[Inserter] Strategy '{name}' failed for app '{app_name}'")

        log.warning(f"[Inserter] All insertion strategies failed for app '{app_name}'")
        return False

    @staticmethod
    def _read_clipboard_bytes():
        try:
            result = subprocess.run(
                ["pbpaste"],
                capture_output=True,
                timeout=3,
                check=False,
            )
            return result.stdout
        except Exception:
            return b""

    @staticmethod
    def _write_clipboard_bytes(payload):
        try:
            proc = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
            proc.communicate(payload, timeout=3)
            return proc.returncode == 0
        except Exception:
            return False

    def _clipboard_restore_delay(self, app_name, bundle_id):
        bundle_id = (bundle_id or "").lower()
        if app_name in self._APPS_NEED_SLOW_CLIPBOARD_RESTORE:
            return 0.85
        if bundle_id in self._BUNDLES_NEED_SLOW_CLIPBOARD_RESTORE:
            return 0.85
        if "kakaotalk" in (app_name or "").lower():
            return 0.85
        return 0.25

    def _with_temp_clipboard(self, text, paste_fn, app_name="", bundle_id=""):
        original = self._read_clipboard_bytes()
        try:
            if not self._write_clipboard_bytes(text.encode("utf-8")):
                log.warning("[Inserter] Failed to write text to clipboard via pbcopy.")
                return False
            time.sleep(0.08)
            return bool(paste_fn())
        finally:
            # Restore clipboard after insertion attempt.
            time.sleep(self._clipboard_restore_delay(app_name, bundle_id))
            if not self._write_clipboard_bytes(original):
                log.warning("[Inserter] Failed to restore original clipboard contents.")

    @staticmethod
    def _has_accessibility_permission():
        return is_accessibility_trusted()

    def _insert_via_cgevent(self, text, app_name="", bundle_id=""):
        """Insert text using pbcopy + Quartz CGEvent Cmd+V."""
        import Quartz

        if not self._has_accessibility_permission():
            log.warning("[Inserter] Accessibility permission missing. CGEvent paste skipped.")
            return False

        def _paste():
            self._wait_for_modifiers_release()

            # Build Cmd+V as "V key event with Command flag" so input source
            # (Korean/English IME) does not reinterpret it as literal typing.
            source = Quartz.CGEventSourceCreate(
                Quartz.kCGEventSourceStatePrivate
            )
            if source is None:
                log.warning("[Inserter] Failed to create CGEvent source.")
                return False

            Quartz.CGEventSourceSetLocalEventsSuppressionInterval(source, 0.0)

            v_down = Quartz.CGEventCreateKeyboardEvent(
                source, self._V_KEYCODE, True
            )
            v_up = Quartz.CGEventCreateKeyboardEvent(
                source, self._V_KEYCODE, False
            )

            events = (v_down, v_up)
            if any(evt is None for evt in events):
                log.warning("[Inserter] Failed to create one or more keyboard events.")
                return False

            Quartz.CGEventSetFlags(v_down, Quartz.kCGEventFlagMaskCommand)
            Quartz.CGEventSetFlags(v_up, Quartz.kCGEventFlagMaskCommand)

            for evt in events:
                Quartz.CGEventPost(Quartz.kCGHIDEventTap, evt)
                time.sleep(0.01)

            time.sleep(0.08)
            return True

        return self._with_temp_clipboard(text, _paste, app_name, bundle_id)

    def _insert_via_applescript(self, text, app_name="", bundle_id=""):
        """Insert text using pbcopy + AppleScript Cmd+V."""
        def _paste():
            # Use hardware keycode for "V" so paste works regardless of input source
            # (e.g., Korean IME active).
            script = (
                'tell application "System Events" to key code 9 '
                "using {command down}"
            )
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            if result.returncode != 0:
                stderr = (result.stderr or "").strip()
                if stderr:
                    log.warning(f"[Inserter] AppleScript paste failed: {stderr}")
                else:
                    log.warning("[Inserter] AppleScript paste failed with unknown error.")
                return False
            return True

        return self._with_temp_clipboard(text, _paste, app_name, bundle_id)

    def _insert_via_unicode_typing(self, text):
        """Insert text by typing Unicode characters directly."""
        import Quartz

        if not text:
            return False
        if not self._has_accessibility_permission():
            log.warning("[Inserter] Accessibility permission missing. Unicode typing skipped.")
            return False

        try:
            self._wait_for_modifiers_release()

            source = Quartz.CGEventSourceCreate(Quartz.kCGEventSourceStatePrivate)
            if source is None:
                log.warning("[Inserter] Failed to create event source for unicode typing.")
                return False

            Quartz.CGEventSourceSetLocalEventsSuppressionInterval(source, 0.0)

            # Let modifier release (Fn/Option) settle before typing.
            time.sleep(0.05)

            for ch in text:
                down = Quartz.CGEventCreateKeyboardEvent(source, 0, True)
                up = Quartz.CGEventCreateKeyboardEvent(source, 0, False)
                if down is None or up is None:
                    return False

                Quartz.CGEventKeyboardSetUnicodeString(down, len(ch), ch)
                Quartz.CGEventKeyboardSetUnicodeString(up, len(ch), ch)
                Quartz.CGEventPost(Quartz.kCGHIDEventTap, down)
                Quartz.CGEventPost(Quartz.kCGHIDEventTap, up)
                time.sleep(0.003)
            return True
        except Exception as exc:
            log.warning(f"[Inserter] Unicode typing failed: {exc}")
            return False

    @staticmethod
    def _wait_for_modifiers_release(timeout=0.25):
        """Wait briefly until global modifiers settle after hotkey release."""
        try:
            import Quartz

            mask = (
                Quartz.kCGEventFlagMaskAlternate
                | Quartz.kCGEventFlagMaskCommand
                | Quartz.kCGEventFlagMaskControl
                | Quartz.kCGEventFlagMaskShift
            )
            deadline = time.time() + timeout
            while time.time() < deadline:
                flags = Quartz.CGEventSourceFlagsState(
                    Quartz.kCGEventSourceStateCombinedSessionState
                )
                if (flags & mask) == 0:
                    return
                time.sleep(0.01)
        except Exception:
            # Best-effort delay if flags API is unavailable.
            time.sleep(0.03)

    @staticmethod
    def get_active_app_info():
        """Get frontmost app metadata (name, pid, bundle_id)."""
        try:
            from AppKit import NSWorkspace

            app = NSWorkspace.sharedWorkspace().frontmostApplication()
            if app is None:
                return {"name": "Unknown", "pid": None, "bundle_id": ""}
            return {
                "name": app.localizedName() or "Unknown",
                "pid": int(app.processIdentifier()),
                "bundle_id": app.bundleIdentifier() or "",
            }
        except Exception:
            return {
                "name": TextInserter.get_active_app_name(),
                "pid": None,
                "bundle_id": "",
            }

    @staticmethod
    def activate_app(app_info):
        """Bring the target application to front."""
        if not isinstance(app_info, dict):
            return False

        pid = app_info.get("pid")
        bundle_id = app_info.get("bundle_id")
        name = app_info.get("name")

        # Preferred path: NSRunningApplication by pid (no System Events permission needed).
        if pid:
            try:
                from AppKit import (
                    NSApplicationActivateIgnoringOtherApps,
                    NSRunningApplication,
                )

                app = NSRunningApplication.runningApplicationWithProcessIdentifier_(
                    int(pid)
                )
                if app is not None:
                    ok = bool(
                        app.activateWithOptions_(
                            NSApplicationActivateIgnoringOtherApps
                        )
                    )
                    if ok:
                        return True
            except Exception:
                pass

        # Fallback: activate by bundle id or app name.
        try:
            if bundle_id:
                result = subprocess.run(
                    ["open", "-b", bundle_id],
                    capture_output=True,
                    timeout=3,
                    check=False,
                )
                if result.returncode == 0:
                    return True

            if name:
                result = subprocess.run(
                    ["open", "-a", name],
                    capture_output=True,
                    timeout=3,
                    check=False,
                )
                if result.returncode == 0:
                    return True
        except Exception:
            pass

        return False

    @staticmethod
    def get_active_app_name():
        """Get the name of the currently focused application."""
        try:
            result = subprocess.run(
                [
                    "osascript",
                    "-e",
                    'tell application "System Events" to get name of first application process whose frontmost is true',
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return result.stdout.strip()
        except Exception:
            return "Unknown"
