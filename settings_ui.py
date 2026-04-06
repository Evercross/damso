"""
Damso (담소) - Settings UI
Clean dark-themed settings window using pywebview.
"""
import json
import os
import sys
import threading
import webview
from config import load_config, save_config, load_dictionary, save_dictionary
from stt import (
    list_input_devices,
    get_model_update_info as stt_get_model_update_info,
    update_model_cache as stt_update_model_cache,
)
from diagnostics import generate_diagnostics_report
from permissions import (
    get_permission_state as perm_get_permission_state,
    open_accessibility_settings as perm_open_accessibility_settings,
    open_automation_settings as perm_open_automation_settings,
    prompt_accessibility_permission as perm_prompt_accessibility_permission,
)


class SettingsAPI:
    """JavaScript ↔ Python bridge for the settings UI."""

    def __init__(self, on_config_changed=None):
        self._window = None
        self.on_config_changed = on_config_changed

    def set_window(self, window):
        self._window = window

    # ── Config ──
    def get_config(self):
        return json.dumps(load_config())

    def save_config(self, config_json):
        config = json.loads(config_json)
        save_config(config)
        if self.on_config_changed:
            self.on_config_changed(config)
        return json.dumps({"ok": True})

    def get_audio_input_devices(self):
        return json.dumps(list_input_devices(), ensure_ascii=False)

    def get_model_update_info(self, engine, model_name):
        result = stt_get_model_update_info(engine, model_name)
        return json.dumps(result, ensure_ascii=False)

    def update_model_cache(self, engine, model_name):
        result = stt_update_model_cache(engine, model_name)
        return json.dumps(result, ensure_ascii=False)

    def get_runtime_meta(self):
        try:
            mtime = os.path.getmtime(sys.executable)
        except Exception:
            mtime = None
        return json.dumps(
            {
                "pid": os.getpid(),
                "executable": sys.executable,
                "frozen": bool(getattr(sys, "frozen", False)),
                "settings_mode": ("--settings" in sys.argv),
                "executable_mtime": mtime,
            },
            ensure_ascii=False,
        )

    def get_permission_state(self):
        return json.dumps(perm_get_permission_state(), ensure_ascii=False)

    def request_accessibility_prompt(self):
        ok = bool(perm_prompt_accessibility_permission())
        return json.dumps({"ok": ok}, ensure_ascii=False)

    def open_accessibility_settings(self):
        ok = bool(perm_open_accessibility_settings())
        return json.dumps({"ok": ok}, ensure_ascii=False)

    def open_automation_settings(self):
        ok = bool(perm_open_automation_settings())
        return json.dumps({"ok": ok}, ensure_ascii=False)

    def generate_diagnostics_report(self):
        result = generate_diagnostics_report(
            config=load_config(),
            log_tail_lines=180,
        )
        return json.dumps(result, ensure_ascii=False)

    # ── Dictionary ──
    def get_dictionary(self):
        return json.dumps(load_dictionary())

    def save_dictionary(self, dict_json):
        data = json.loads(dict_json)
        save_dictionary(data)
        return json.dumps({"ok": True})

    def add_user_term(self, from_text, to_text):
        d = load_dictionary()
        d["user_terms"][from_text] = to_text
        save_dictionary(d)
        return json.dumps({"ok": True})

    def remove_user_term(self, from_text):
        d = load_dictionary()
        d["user_terms"].pop(from_text, None)
        save_dictionary(d)
        return json.dumps({"ok": True})


SETTINGS_HTML = """
<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<title>Damso Settings</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }

:root {
    --bg: #1a1a1e;
    --sidebar-bg: #141416;
    --card-bg: #232328;
    --card-border: #2e2e35;
    --text: #e8e8ec;
    --text-dim: #8e8e93;
    --accent: #e84393;
    --accent-hover: #fd79a8;
    --green: #00b894;
    --input-bg: #2a2a30;
    --toggle-off: #48484a;
}

body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    background: var(--bg);
    color: var(--text);
    display: flex;
    height: 100vh;
    overflow: hidden;
    -webkit-font-smoothing: antialiased;
}

/* ── Sidebar ── */
.sidebar {
    width: 200px;
    background: var(--sidebar-bg);
    padding: 20px 12px;
    display: flex;
    flex-direction: column;
    gap: 4px;
    border-right: 1px solid var(--card-border);
    -webkit-app-region: drag;
}

.sidebar-logo {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 8px 12px;
    margin-bottom: 16px;
}

.sidebar-logo .icon {
    width: 36px;
    height: 36px;
    background: linear-gradient(135deg, #6c5ce7, #e84393);
    border-radius: 10px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 18px;
}

.sidebar-logo .name {
    font-size: 16px;
    font-weight: 600;
}

.nav-item {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 8px 12px;
    border-radius: 8px;
    cursor: pointer;
    font-size: 13px;
    color: var(--text-dim);
    transition: all 0.15s;
    -webkit-app-region: no-drag;
}

.nav-item:hover { background: rgba(255,255,255,0.05); color: var(--text); }
.nav-item.active { background: rgba(255,255,255,0.08); color: var(--text); }
.nav-item .emoji { font-size: 16px; width: 20px; text-align: center; }

/* ── Main Content ── */
.main {
    flex: 1;
    overflow-y: auto;
    padding: 24px 32px;
}

.page { display: none; }
.page.active { display: block; }

.page-title {
    font-size: 22px;
    font-weight: 700;
    margin-bottom: 4px;
}

.page-subtitle {
    font-size: 13px;
    color: var(--text-dim);
    margin-bottom: 24px;
}

/* ── Sections & Cards ── */
.section-label {
    font-size: 11px;
    font-weight: 600;
    color: var(--text-dim);
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-bottom: 8px;
    margin-top: 20px;
}

.section-label:first-of-type { margin-top: 0; }

.card {
    background: var(--card-bg);
    border: 1px solid var(--card-border);
    border-radius: 12px;
    padding: 0;
    margin-bottom: 12px;
}

.card-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 12px 16px;
    border-bottom: 1px solid var(--card-border);
}

.card-row:last-child { border-bottom: none; }

.card-row-info { flex: 1; }
.card-row-label { font-size: 14px; font-weight: 500; }
.card-row-desc { font-size: 12px; color: var(--text-dim); margin-top: 2px; }

/* ── Toggle ── */
.toggle {
    width: 44px;
    height: 26px;
    background: var(--toggle-off);
    border-radius: 13px;
    cursor: pointer;
    position: relative;
    transition: background 0.2s;
    flex-shrink: 0;
}

.toggle.on { background: var(--accent); }

.toggle::after {
    content: '';
    position: absolute;
    width: 22px;
    height: 22px;
    background: white;
    border-radius: 50%;
    top: 2px;
    left: 2px;
    transition: transform 0.2s;
}

.toggle.on::after { transform: translateX(18px); }

/* ── Select / Input ── */
select, input[type="text"] {
    background: var(--input-bg);
    border: 1px solid var(--card-border);
    color: var(--text);
    padding: 6px 12px;
    border-radius: 8px;
    font-size: 13px;
    outline: none;
}

select { cursor: pointer; min-width: 140px; }
select:focus, input[type="text"]:focus { border-color: var(--accent); }

/* ── Buttons ── */
.btn {
    padding: 6px 16px;
    border-radius: 8px;
    border: 1px solid var(--card-border);
    background: var(--input-bg);
    color: var(--text);
    font-size: 13px;
    cursor: pointer;
    transition: all 0.15s;
}

.btn:hover { background: rgba(255,255,255,0.1); }
.btn-accent { background: var(--accent); border-color: var(--accent); color: white; }
.btn-accent:hover { background: var(--accent-hover); }
.btn-danger { color: var(--accent); }
.btn-danger:hover { background: rgba(232,67,147,0.1); }

.btn-small {
    padding: 4px 10px;
    font-size: 12px;
    border-radius: 6px;
}

.btn-group {
    display: flex;
    gap: 6px;
}

/* ── Dictionary specific ── */
.term-row {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 16px;
    border-bottom: 1px solid var(--card-border);
}

.term-row:last-child { border-bottom: none; }

.term-from {
    font-size: 13px;
    color: var(--text-dim);
    min-width: 100px;
}

.term-arrow { color: var(--text-dim); font-size: 12px; }

.term-to {
    font-size: 13px;
    font-weight: 500;
    flex: 1;
}

.add-term-row {
    display: flex;
    gap: 8px;
    padding: 12px 16px;
    align-items: center;
}

.add-term-row input {
    flex: 1;
    padding: 8px 12px;
}

/* ── Status badge ── */
.badge {
    font-size: 11px;
    padding: 2px 8px;
    border-radius: 4px;
    font-weight: 600;
}

.badge-green { background: rgba(0,184,148,0.15); color: var(--green); }

/* ── Try It section ── */
.try-input {
    width: 100%;
    padding: 10px 14px;
    background: var(--input-bg);
    border: 1px solid var(--card-border);
    border-radius: 8px;
    color: var(--text);
    font-size: 13px;
    margin-bottom: 8px;
}

.try-output {
    width: 100%;
    padding: 10px 14px;
    background: var(--sidebar-bg);
    border-radius: 8px;
    font-size: 13px;
    font-weight: 600;
    min-height: 40px;
}

.try-label {
    font-size: 11px;
    color: var(--text-dim);
    margin-bottom: 4px;
    text-transform: uppercase;
}
</style>
</head>
<body>

<div class="sidebar">
    <div class="sidebar-logo">
        <div class="icon">🎤</div>
        <div class="name">Damso</div>
    </div>
    <div class="nav-item active" data-page="settings">
        <span class="emoji">⚙️</span> Settings
    </div>
    <div class="nav-item" data-page="dictionary">
        <span class="emoji">📖</span> Dictionary
    </div>
</div>

<div class="main">

    <!-- ═══ SETTINGS PAGE ═══ -->
    <div class="page active" id="page-settings">
        <div class="page-title">Settings</div>
        <div class="page-subtitle">Configure STT engine, hotkeys, and text cleanup</div>

        <div class="section-label">STT ENGINE</div>
        <div class="card">
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
            <div class="card-row">
                <div class="card-row-info">
                    <div class="card-row-label">Model</div>
                    <div class="card-row-desc">Local engine model selection</div>
                </div>
                <select id="cfg-model" onchange="refreshModelUpdateStatus()">
                    <!-- Populated by JS based on engine selection -->
                </select>
            </div>
            <div class="card-row">
                <div class="card-row-info">
                    <div class="card-row-label">Model update</div>
                    <div class="card-row-desc" id="model-update-status">Check if a newer model revision is available</div>
                </div>
                <button class="btn btn-small" id="btn-model-update" onclick="checkAndUpdateModel()">Check & Update</button>
            </div>
            <div class="card-row">
                <div class="card-row-info">
                    <div class="card-row-label">Language</div>
                    <div class="card-row-desc">Speech recognition language</div>
                </div>
                <select id="cfg-language">
                    <option value="ko">한국어</option>
                    <option value="en">English</option>
                    <option value="ja">日本語</option>
                    <option value="zh">中文</option>
                    <option value="">Auto-detect</option>
                </select>
            </div>
        </div>

        <div class="section-label">HOLD-TO-TALK</div>
        <div class="card">
            <div class="card-row">
                <div class="card-row-info">
                    <div class="card-row-label">Shortcut</div>
                    <div class="card-row-desc">Choose a hold key (Right Option recommended)</div>
                </div>
                <select id="cfg-hold-key">
                    <option value="right_option">Right Option (Recommended)</option>
                    <option value="fn">Fn (Globe)</option>
                    <option value="both">Fn + Right Option</option>
                </select>
            </div>
            <div class="card-row">
                <div class="card-row-info">
                    <div class="card-row-label">Audio input device</div>
                    <div class="card-row-desc">Select microphone source used by Damso</div>
                </div>
                <select id="cfg-audio-input">
                    <option value="default">System Default</option>
                </select>
            </div>
            <div class="card-row">
                <div class="card-row-info">
                    <div class="card-row-label">Min speech length</div>
                    <div class="card-row-desc">Ignore recordings shorter than this threshold</div>
                </div>
                <select id="cfg-min-audio-seconds">
                    <option value="0.25">0.25s (Very sensitive)</option>
                    <option value="0.30">0.30s (Recommended)</option>
                    <option value="0.40">0.40s (Balanced)</option>
                    <option value="0.50">0.50s (Conservative)</option>
                </select>
            </div>
        </div>

        <div class="section-label">TEXT CLEANUP</div>
        <div class="card">
            <div class="card-row">
                <div class="card-row-info">
                    <div class="card-row-label">Auto punctuation</div>
                    <div class="card-row-desc">Add punctuation and spacing automatically</div>
                </div>
                <div class="toggle" id="cfg-punctuation" onclick="toggleSwitch(this, 'auto_punctuation')"></div>
            </div>
            <div class="card-row">
                <div class="card-row-info">
                    <div class="card-row-label">Show notification</div>
                    <div class="card-row-desc">Display notification after text insertion</div>
                </div>
                <div class="toggle" id="cfg-notification" onclick="toggleSwitch(this, 'show_notification')"></div>
            </div>
        </div>

        <div class="section-label">APP</div>
        <div class="card">
            <div class="card-row">
                <div class="card-row-info">
                    <div class="card-row-label">Insert method</div>
                    <div class="card-row-desc">How text is typed at cursor (Stable recommended)</div>
                </div>
                <select id="cfg-insert-method">
                    <option value="stable">Stable (Recommended)</option>
                    <option value="auto">Auto (Legacy)</option>
                    <option value="cgevent">CGEvent</option>
                    <option value="applescript">AppleScript (Fallback)</option>
                </select>
            </div>
            <div class="card-row">
                <div class="card-row-info">
                    <div class="card-row-label">History retention</div>
                    <div class="card-row-desc">Auto-delete entries after days</div>
                </div>
                <select id="cfg-history-days">
                    <option value="7">7 days</option>
                    <option value="30">30 days</option>
                    <option value="90">90 days</option>
                    <option value="0">Keep forever</option>
                </select>
            </div>
        </div>

        <div class="section-label">SUPPORT</div>
        <div class="card">
            <div class="card-row">
                <div class="card-row-info">
                    <div class="card-row-label">Runtime</div>
                    <div class="card-row-desc" id="runtime-meta">Loading runtime metadata...</div>
                </div>
            </div>
            <div class="card-row">
                <div class="card-row-info">
                    <div class="card-row-label">Permission status</div>
                    <div class="card-row-desc" id="perm-status">Checking Accessibility/Automation status...</div>
                </div>
                <div class="btn-group">
                    <button class="btn btn-small" onclick="refreshPermissionState()">Refresh</button>
                    <button class="btn btn-small" onclick="requestAccessibilityPrompt()">Prompt</button>
                    <button class="btn btn-small" onclick="openPermissionSettings()">Open</button>
                </div>
            </div>
            <div class="card-row">
                <div class="card-row-info">
                    <div class="card-row-label">Diagnostics report</div>
                    <div class="card-row-desc" id="diag-status">Generate a report for cross-verification and troubleshooting</div>
                </div>
                <button class="btn btn-small" id="btn-diagnostics" onclick="createDiagnosticsReport()">Generate</button>
            </div>
        </div>

        <div style="margin-top: 16px; text-align: right;">
            <button class="btn btn-accent" onclick="saveSettings()">Save</button>
        </div>
    </div>

    <!-- ═══ DICTIONARY PAGE ═══ -->
    <div class="page" id="page-dictionary">
        <div class="page-title">Dictionary</div>
        <div class="page-subtitle">Custom term replacements before insertion</div>

        <div class="section-label">DICTIONARY</div>
        <div class="card">
            <div class="card-row">
                <div class="card-row-info">
                    <div class="card-row-label">Enable dictionary</div>
                    <div class="card-row-desc">Apply term replacements before insertion</div>
                </div>
                <div class="toggle on" id="dict-enabled" onclick="toggleDictEnabled(this)"></div>
            </div>
        </div>

        <div class="section-label">PRESET TERMS</div>
        <div class="card" id="preset-terms">
            <!-- Filled by JS -->
        </div>

        <div class="section-label">CUSTOM REPLACEMENTS</div>
        <div class="card">
            <div class="add-term-row">
                <input type="text" id="new-term-from" placeholder="From (e.g. 깃허브)">
                <span style="color:var(--text-dim)">→</span>
                <input type="text" id="new-term-to" placeholder="To (e.g. GitHub)">
                <button class="btn btn-accent btn-small" onclick="addUserTerm()">Add</button>
            </div>
        </div>
        <div class="card" id="user-terms">
            <!-- Filled by JS -->
        </div>

        <div class="section-label">TRY IT</div>
        <div class="card" style="padding: 16px;">
            <input class="try-input" id="try-input" placeholder="Type text to preview replacements..." oninput="updateTryIt()">
            <div class="try-label">OUTPUT</div>
            <div class="try-output" id="try-output"></div>
        </div>
    </div>
</div>

<script>
let config = {};
let dictionary = {};

// ── Navigation ──
document.querySelectorAll('.nav-item').forEach(item => {
    item.addEventListener('click', () => {
        document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
        document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
        item.classList.add('active');
        document.getElementById('page-' + item.dataset.page).classList.add('active');
    });
});

// ── Toggle ──
function toggleSwitch(el, key) {
    el.classList.toggle('on');
    config[key] = el.classList.contains('on');
}

// ── Load Config ──
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

    if (modelSelect.options.length > 0) {
        modelSelect.selectedIndex = 0;
    }
    refreshModelUpdateStatus();
}

async function refreshModelUpdateStatus() {
    const statusEl = document.getElementById('model-update-status');
    const engine = document.getElementById('cfg-engine').value;
    const model = document.getElementById('cfg-model').value;
    if (!statusEl) return;
    if (!model) {
        statusEl.textContent = 'Select a model first';
        return;
    }

    statusEl.textContent = 'Checking latest model revision...';
    try {
        const raw = await pywebview.api.get_model_update_info(engine, model);
        const info = JSON.parse(raw);
        if (!info.supported) {
            statusEl.textContent = info.message || 'Update check is not supported for this model';
            return;
        }
        if (!info.ok) {
            statusEl.textContent = info.message || 'Failed to check latest revision';
            return;
        }
        if (info.update_available) {
            const latest = (info.latest_revision || '').slice(0, 8);
            statusEl.textContent = `Update available (${latest})`;
        } else {
            statusEl.textContent = 'Already up to date';
        }
    } catch (e) {
        statusEl.textContent = 'Failed to check latest revision';
    }
}

async function checkAndUpdateModel() {
    const btn = document.getElementById('btn-model-update');
    const statusEl = document.getElementById('model-update-status');
    const engine = document.getElementById('cfg-engine').value;
    const model = document.getElementById('cfg-model').value;

    if (!model) {
        alert('Select a model first');
        return;
    }

    const originalLabel = btn.textContent;
    btn.disabled = true;
    btn.textContent = 'Updating...';
    statusEl.textContent = 'Checking and downloading latest model...';

    try {
        const raw = await pywebview.api.update_model_cache(engine, model);
        const result = JSON.parse(raw);
        if (!result.supported) {
            statusEl.textContent = result.message || 'Update is not supported for this model';
            alert(statusEl.textContent);
            return;
        }
        if (!result.ok) {
            statusEl.textContent = result.message || 'Model update failed';
            alert(statusEl.textContent);
            return;
        }

        if (result.updated) {
            statusEl.textContent = 'Updated to latest revision (restart Damso to apply)';
            alert('Model updated successfully. Restart Damso to apply the new revision.');
        } else {
            statusEl.textContent = result.message || 'Already up to date';
            alert(statusEl.textContent);
        }
    } catch (e) {
        statusEl.textContent = 'Model update failed';
        alert('Model update failed. Please try again.');
    } finally {
        btn.disabled = false;
        btn.textContent = originalLabel;
        refreshModelUpdateStatus();
    }
}

async function loadAudioInputDevices(selectedValue) {
    const select = document.getElementById('cfg-audio-input');
    select.innerHTML = '';
    select.add(new Option('System Default', 'default'));

    try {
        const raw = await pywebview.api.get_audio_input_devices();
        const devices = JSON.parse(raw);
        devices.forEach(dev => {
            const value = String(dev.id);
            const label = dev.label || dev.name || (`Device ${value}`);
            select.add(new Option(label, value));
        });
    } catch (e) {
        // Keep only the system default option if device query fails.
    }

    const target = String(selectedValue || 'default');
    const hasTarget = Array.from(select.options).some(opt => opt.value === target);
    select.value = hasTarget ? target : 'default';
}

async function loadConfig() {
    const raw = await pywebview.api.get_config();
    config = JSON.parse(raw);
    document.getElementById('cfg-engine').value = config.stt_engine || 'qwen3-asr';
    onEngineChange();
    // Set model value after populating options
    const modelKey = config.stt_engine === 'whisper' ? 'whisper_model' : 'qwen_model';
    document.getElementById('cfg-model').value = config[modelKey] || '';
    document.getElementById('cfg-language').value = config.language || 'ko';
    document.getElementById('cfg-hold-key').value = config.hotkey_hold || 'right_option';
    document.getElementById('cfg-insert-method').value = config.insert_method || 'stable';
    document.getElementById('cfg-history-days').value = String(config.history_retention_days || 30);
    await loadAudioInputDevices(config.audio_input_device || 'default');
    config.audio_input_device = document.getElementById('cfg-audio-input').value;
    setSelectClosestNumber('cfg-min-audio-seconds', config.min_audio_seconds || 0.30);
    config.min_audio_seconds = parseFloat(document.getElementById('cfg-min-audio-seconds').value);

    setToggle('cfg-punctuation', config.auto_punctuation);
    setToggle('cfg-notification', config.show_notification);
    await refreshModelUpdateStatus();
}

function setToggle(id, value) {
    const el = document.getElementById(id);
    if (value) el.classList.add('on');
    else el.classList.remove('on');
}

function setSelectClosestNumber(id, value) {
    const select = document.getElementById(id);
    const options = Array.from(select.options).map(opt => Number(opt.value));
    const target = Number(value);
    if (!Number.isFinite(target) || options.length === 0) return;
    let closest = options[0];
    for (const candidate of options) {
        if (Math.abs(candidate - target) < Math.abs(closest - target)) {
            closest = candidate;
        }
    }
    select.value = closest.toFixed(2);
}

async function saveSettings() {
    config.stt_engine = document.getElementById('cfg-engine').value;
    const modelVal = document.getElementById('cfg-model').value;
    if (config.stt_engine === 'whisper') {
        config.whisper_model = modelVal;
    } else {
        config.qwen_model = modelVal;
    }
    config.language = document.getElementById('cfg-language').value;
    config.hotkey_hold = document.getElementById('cfg-hold-key').value;
    config.insert_method = document.getElementById('cfg-insert-method').value;
    config.history_retention_days = parseInt(document.getElementById('cfg-history-days').value);
    config.audio_input_device = document.getElementById('cfg-audio-input').value;
    config.min_audio_seconds = parseFloat(document.getElementById('cfg-min-audio-seconds').value);
    config.auto_punctuation = document.getElementById('cfg-punctuation').classList.contains('on');
    config.show_notification = document.getElementById('cfg-notification').classList.contains('on');

    await pywebview.api.save_config(JSON.stringify(config));
    alert('Settings saved!');
}

async function loadRuntimeMeta() {
    const runtimeEl = document.getElementById('runtime-meta');
    if (!runtimeEl) return;

    try {
        const raw = await pywebview.api.get_runtime_meta();
        const meta = JSON.parse(raw);
        const ts = meta.executable_mtime ? new Date(meta.executable_mtime * 1000) : null;
        const timeLabel = ts ? ts.toLocaleString() : 'unknown build time';
        runtimeEl.textContent = `${meta.executable} | build ${timeLabel}`;
    } catch (e) {
        runtimeEl.textContent = 'Failed to read runtime metadata';
    }
}

async function refreshPermissionState() {
    const permEl = document.getElementById('perm-status');
    if (!permEl) return;
    permEl.textContent = 'Checking permission state...';

    try {
        const raw = await pywebview.api.get_permission_state();
        const state = JSON.parse(raw);
        const a11y = state.accessibility_trusted ? 'Accessibility: OK' : 'Accessibility: Missing';
        const automation = (state.system_events && state.system_events.ok)
            ? 'Automation: OK'
            : 'Automation: Blocked';
        permEl.textContent = `${a11y} | ${automation}`;
    } catch (e) {
        permEl.textContent = 'Failed to read permission state';
    }
}

async function requestAccessibilityPrompt() {
    try {
        await pywebview.api.request_accessibility_prompt();
    } catch (e) {
        // no-op
    } finally {
        refreshPermissionState();
    }
}

async function openPermissionSettings() {
    try {
        await pywebview.api.open_accessibility_settings();
        await pywebview.api.open_automation_settings();
    } catch (e) {
        // no-op
    } finally {
        setTimeout(refreshPermissionState, 700);
    }
}

async function createDiagnosticsReport() {
    const btn = document.getElementById('btn-diagnostics');
    const statusEl = document.getElementById('diag-status');
    const originalLabel = btn.textContent;
    btn.disabled = true;
    btn.textContent = 'Generating...';
    statusEl.textContent = 'Collecting logs and permission state...';

    try {
        const raw = await pywebview.api.generate_diagnostics_report();
        const result = JSON.parse(raw);
        statusEl.textContent = `Saved: ${result.path}`;
        alert(`Diagnostics report created:\n${result.path}`);
    } catch (e) {
        statusEl.textContent = 'Failed to generate diagnostics report';
        alert('Failed to generate diagnostics report');
    } finally {
        btn.disabled = false;
        btn.textContent = originalLabel;
    }
}

// ── Load Dictionary ──
async function loadDictionary() {
    const raw = await pywebview.api.get_dictionary();
    dictionary = JSON.parse(raw);
    const enabled = dictionary.enabled !== false;
    const toggle = document.getElementById('dict-enabled');
    if (enabled) toggle.classList.add('on');
    else toggle.classList.remove('on');
    renderPresetTerms();
    renderUserTerms();
}

async function toggleDictEnabled(el) {
    el.classList.toggle('on');
    dictionary.enabled = el.classList.contains('on');
    await pywebview.api.save_dictionary(JSON.stringify(dictionary));
}

function renderPresetTerms() {
    const container = document.getElementById('preset-terms');
    const presets = dictionary.presets?.dev || {};
    const entries = Object.entries(presets).slice(0, 15);  // Show first 15
    let html = '';
    entries.forEach(([from, to]) => {
        html += `<div class="term-row">
            <span class="term-from">${from}</span>
            <span class="term-arrow">→</span>
            <span class="term-to">${to}</span>
        </div>`;
    });
    if (Object.keys(presets).length > 15) {
        html += `<div class="term-row" style="justify-content:center;color:var(--text-dim);font-size:12px;">
            ... and ${Object.keys(presets).length - 15} more preset terms
        </div>`;
    }
    container.innerHTML = html;
}

function renderUserTerms() {
    const container = document.getElementById('user-terms');
    const terms = dictionary.user_terms || {};
    if (Object.keys(terms).length === 0) {
        container.innerHTML = '<div class="card-row" style="color:var(--text-dim);font-size:13px;">No custom terms yet</div>';
        return;
    }
    let html = '';
    Object.entries(terms).forEach(([from, to]) => {
        html += `<div class="term-row">
            <span class="term-from">${from}</span>
            <span class="term-arrow">→</span>
            <span class="term-to">${to}</span>
            <button class="btn btn-danger btn-small" onclick="removeUserTerm('${from.replace(/'/g, "\\'")}')">Delete</button>
        </div>`;
    });
    container.innerHTML = html;
}

async function addUserTerm() {
    const from = document.getElementById('new-term-from').value.trim();
    const to = document.getElementById('new-term-to').value.trim();
    if (!from || !to) return;
    await pywebview.api.add_user_term(from, to);
    document.getElementById('new-term-from').value = '';
    document.getElementById('new-term-to').value = '';
    await loadDictionary();
}

async function removeUserTerm(from) {
    await pywebview.api.remove_user_term(from);
    await loadDictionary();
}

function updateTryIt() {
    const input = document.getElementById('try-input').value;
    if (dictionary.enabled === false) {
        document.getElementById('try-output').textContent = input;
        return;
    }
    let result = input;
    // Apply presets
    const presets = dictionary.presets?.dev || {};
    const userTerms = dictionary.user_terms || {};
    const allTerms = {...presets, ...userTerms};
    // Sort by length (longest first)
    const sorted = Object.entries(allTerms).sort((a, b) => b[0].length - a[0].length);
    sorted.forEach(([from, to]) => {
        result = result.split(from).join(to);
    });
    document.getElementById('try-output').textContent = result;
}

// ── Init ──
window.addEventListener('pywebviewready', () => {
    loadConfig();
    loadDictionary();
    loadRuntimeMeta();
    refreshPermissionState();
    setInterval(refreshPermissionState, 5000);
});
</script>

</body>
</html>
"""


def open_settings_window(on_config_changed=None):
    """Open the settings window. Blocks until the window is closed."""
    api = SettingsAPI(on_config_changed=on_config_changed)
    window = webview.create_window(
        "Damso — Settings",
        html=SETTINGS_HTML,
        js_api=api,
        width=700,
        height=550,
        resizable=True,
        background_color="#1a1a1e",
    )
    api.set_window(window)
    webview.start()


if __name__ == "__main__":
    open_settings_window()
