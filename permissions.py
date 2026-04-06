"""
Damso - Permission Helpers
Centralized checks/probes for macOS Accessibility and Automation permissions.
"""
from __future__ import annotations

import ctypes
import ctypes.util
import logging
import subprocess

log = logging.getLogger("damso")


def is_accessibility_trusted():
    """Return True when this process is trusted for Accessibility APIs.

    Uses AXIsProcessTrustedWithOptions (PyObjC) first, falls back to ctypes.
    When running inside a PyInstaller .app bundle the check targets the
    running binary (Contents/MacOS/Damso), which is the entity macOS TCC
    evaluates.
    """
    # Method 1: PyObjC — preferred, returns the real per-process TCC state.
    try:
        from ApplicationServices import AXIsProcessTrustedWithOptions

        return bool(AXIsProcessTrustedWithOptions(None))
    except Exception:
        pass

    # Method 2: ctypes fallback (no PyObjC required).
    try:
        lib_path = ctypes.util.find_library("ApplicationServices")
        if not lib_path:
            lib_path = (
                "/System/Library/Frameworks/ApplicationServices.framework/"
                "ApplicationServices"
            )
        app_services = ctypes.cdll.LoadLibrary(lib_path)
        app_services.AXIsProcessTrusted.restype = ctypes.c_bool
        return bool(app_services.AXIsProcessTrusted())
    except Exception:
        return False


def prompt_accessibility_permission():
    """Trigger the native Accessibility permission prompt once (best effort).

    On ad-hoc signed apps macOS may silently ignore the prompt — in that case
    we fall back to opening System Settings directly so the user can grant
    permission manually.

    Returns current trust state after prompt attempt.
    """
    trusted = False
    try:
        from ApplicationServices import (
            AXIsProcessTrustedWithOptions,
            kAXTrustedCheckOptionPrompt,
        )

        trusted = bool(
            AXIsProcessTrustedWithOptions({kAXTrustedCheckOptionPrompt: True})
        )
    except Exception:
        trusted = is_accessibility_trusted()

    # If still not trusted after the prompt attempt, open Settings directly.
    # Ad-hoc signed apps often don't trigger the native prompt dialog.
    if not trusted:
        log.info(
            "[Permission] Accessibility prompt did not grant trust — "
            "opening System Settings for manual grant."
        )
        open_accessibility_settings()

    return trusted


def probe_system_events_permission():
    """Probe AppleScript System Events permission without destructive effects.

    Returns: {"ok": bool, "error": str, "code": int|None}
    """
    script = (
        'tell application "System Events" '
        "to get name of first application process whose frontmost is true"
    )
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except Exception as exc:
        return {"ok": False, "error": str(exc), "code": None}

    if result.returncode == 0:
        return {"ok": True, "error": "", "code": 0}

    stderr = (result.stderr or "").strip()
    code = None
    if "1002" in stderr:
        code = 1002
    elif "1743" in stderr:
        code = 1743
    return {"ok": False, "error": stderr, "code": code}


def open_accessibility_settings():
    """Open macOS Accessibility settings pane."""
    try:
        subprocess.Popen(
            [
                "open",
                "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility",
            ]
        )
        return True
    except Exception:
        return False


def open_automation_settings():
    """Open macOS Automation privacy settings pane."""
    try:
        subprocess.Popen(
            [
                "open",
                "x-apple.systempreferences:com.apple.preference.security?Privacy_Automation",
            ]
        )
        return True
    except Exception:
        return False


def get_permission_state():
    """Return a compact permission state snapshot for UI/logging."""
    automation = probe_system_events_permission()
    return {
        "accessibility_trusted": is_accessibility_trusted(),
        "system_events": automation,
    }
