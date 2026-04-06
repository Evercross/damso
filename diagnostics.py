"""
Damso - Runtime Diagnostics
Collects a support snapshot for reproducible troubleshooting.
"""
import datetime as dt
import json
import os
import subprocess
import sys

from permissions import get_permission_state


DIAG_DIR = os.path.expanduser("~/.damso/diagnostics")


def _read_tcc_rows():
    """Read damso-related TCC rows for quick permission inspection."""
    db_path = os.path.expanduser("~/Library/Application Support/com.apple.TCC/TCC.db")
    if not os.path.exists(db_path):
        return []

    sql = (
        "SELECT service,client,client_type,auth_value,last_modified "
        "FROM access WHERE client LIKE '%damso%' "
        "ORDER BY service,client;"
    )
    try:
        result = subprocess.run(
            ["sqlite3", db_path, sql],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except Exception:
        return []

    rows = []
    for line in (result.stdout or "").splitlines():
        parts = line.split("|")
        if len(parts) != 5:
            continue
        service, client, client_type, auth_value, last_modified = parts
        rows.append(
            {
                "service": service,
                "client": client,
                "client_type": client_type,
                "auth_value": auth_value,
                "last_modified": last_modified,
            }
        )
    return rows


def _codesign_info(path):
    if not path or not os.path.exists(path):
        return {"ok": False, "path": path, "details": []}
    try:
        result = subprocess.run(
            ["codesign", "-dv", "--verbose=2", path],
            capture_output=True,
            text=True,
            timeout=6,
            check=False,
        )
    except Exception as exc:
        return {"ok": False, "path": path, "error": str(exc), "details": []}

    # codesign writes metadata to stderr.
    raw = (result.stderr or "") + "\n" + (result.stdout or "")
    details = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith(
            ("Identifier=", "TeamIdentifier=", "Authority=", "Format=", "CodeDirectory")
        ):
            details.append(line)
    return {
        "ok": result.returncode == 0,
        "path": path,
        "returncode": result.returncode,
        "details": details,
    }


def _bundle_root(executable):
    if not executable:
        return ""
    marker = ".app/Contents/MacOS/"
    if marker not in executable:
        return ""
    prefix = executable.split(marker, 1)[0]
    return f"{prefix}.app"


def _tail_log(log_file, lines=120):
    if not log_file or not os.path.exists(log_file):
        return []
    try:
        with open(log_file, "r", encoding="utf-8") as f:
            content = f.read().splitlines()
        return content[-int(lines) :]
    except Exception:
        return []


def _find_processes():
    """List Damso and settings processes."""
    try:
        result = subprocess.run(
            [
                "pgrep",
                "-fal",
                "/Applications/Damso.app/Contents/MacOS/Damso|--settings",
            ],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        lines = [ln.strip() for ln in (result.stdout or "").splitlines() if ln.strip()]
        return lines
    except Exception:
        return []


def generate_diagnostics_report(config=None, log_file=None, log_tail_lines=120):
    """
    Write a diagnostics JSON report and return metadata.
    """
    ts = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    os.makedirs(DIAG_DIR, exist_ok=True)
    path = os.path.join(DIAG_DIR, f"damso-diagnostics-{ts}.json")

    if log_file is None:
        log_file = os.path.expanduser("~/.damso/damso.log")

    permission_state = get_permission_state()

    payload = {
        "generated_at": dt.datetime.now().isoformat(),
        "runtime": {
            "pid": os.getpid(),
            "executable": sys.executable,
            "cwd": os.getcwd(),
            "frozen": bool(getattr(sys, "frozen", False)),
            "settings_mode": ("--settings" in sys.argv),
        },
        "permissions": {
            **permission_state,
            "tcc_rows": _read_tcc_rows(),
        },
        "codesign": {
            "executable": _codesign_info(sys.executable),
            "bundle": _codesign_info(_bundle_root(sys.executable)),
            "installed_app": _codesign_info("/Applications/Damso.app"),
        },
        "processes": _find_processes(),
        "config": config or {},
        "log_tail": _tail_log(log_file, lines=log_tail_lines),
    }

    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    return {
        "ok": True,
        "path": path,
        "accessibility_trusted": payload["permissions"]["accessibility_trusted"],
        "system_events_ok": payload["permissions"]["system_events"]["ok"],
    }
