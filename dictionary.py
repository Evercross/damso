"""
Damso - Dictionary / Term Replacement
Replaces recognized speech terms with correct technical terms before insertion.
"""
import re
from config import load_dictionary, save_dictionary


class Dictionary:
    """Manages preset and custom term replacements."""

    _BOUNDARY_CLASS = r"A-Za-z0-9_가-힣"
    _PUNCT_SPACE_CLASS = r"\s.,!?;:)\]}\>\"'…"
    _KOREAN_POSTFIX_CLASS = "은는이가을를와과도의로으랑께부터까지만밖에처럼이나나마"

    def __init__(self):
        self.data = load_dictionary()
        self._build_replacement_map()

    def _build_replacement_map(self):
        """Build a combined replacement map from enabled presets + user terms."""
        self.enabled = bool(self.data.get("enabled", True))
        self.replacements = {}

        # Add enabled preset terms
        for preset_name in self.data.get("enabled_presets", []):
            preset = self.data.get("presets", {}).get(preset_name, {})
            self.replacements.update(preset)

        # User terms override presets
        self.replacements.update(self.data.get("user_terms", {}))

        # Sort by length (longest first) to avoid partial replacements
        self._sorted_keys = sorted(self.replacements.keys(), key=len, reverse=True)
        self._compiled_rules = []
        for term in self._sorted_keys:
            replacement = self.replacements[term]
            mode = self._replacement_mode(term)
            if mode == "latin":
                pattern = re.compile(
                    rf"(?<![{self._BOUNDARY_CLASS}]){re.escape(term)}(?![{self._BOUNDARY_CLASS}])"
                )
            elif mode == "hangul":
                pattern = re.compile(
                    rf"(?<![{self._BOUNDARY_CLASS}]){re.escape(term)}(?=$|[{self._PUNCT_SPACE_CLASS}]|[{self._KOREAN_POSTFIX_CLASS}])"
                )
            else:
                pattern = None
            self._compiled_rules.append((term, replacement, pattern))

    @staticmethod
    def _replacement_mode(term):
        compact = "".join(term.split())
        if not compact:
            return "raw"
        if all("가" <= ch <= "힣" for ch in compact):
            return "hangul"
        if any(ch.isascii() and ch.isalnum() for ch in compact):
            return "latin"
        return "raw"

    def apply(self, text):
        """Apply dictionary replacements to text.

        Uses word boundary matching to avoid changing partial words.
        """
        if not text or not self.replacements or not self.enabled:
            return text

        result = text
        for term, replacement, pattern in self._compiled_rules:
            if pattern is None:
                result = result.replace(term, replacement)
            else:
                result = pattern.sub(replacement, result)

        return result

    def add_user_term(self, source, target):
        """Add a custom user term."""
        self.data["user_terms"][source] = target
        save_dictionary(self.data)
        self._build_replacement_map()

    def remove_user_term(self, source):
        """Remove a custom user term."""
        if source in self.data["user_terms"]:
            del self.data["user_terms"][source]
            save_dictionary(self.data)
            self._build_replacement_map()

    def get_all_terms(self):
        """Get all active replacement terms."""
        return self.replacements.copy()

    def get_user_terms(self):
        """Get user-defined terms only."""
        return self.data.get("user_terms", {}).copy()

    def toggle_preset(self, preset_name, enabled):
        """Enable or disable a preset."""
        enabled_presets = self.data.get("enabled_presets", [])
        if enabled and preset_name not in enabled_presets:
            enabled_presets.append(preset_name)
        elif not enabled and preset_name in enabled_presets:
            enabled_presets.remove(preset_name)
        self.data["enabled_presets"] = enabled_presets
        save_dictionary(self.data)
        self._build_replacement_map()

    def set_enabled(self, enabled):
        """Enable/disable dictionary replacement globally."""
        self.data["enabled"] = bool(enabled)
        save_dictionary(self.data)
        self._build_replacement_map()

    def reload(self):
        """Reload dictionary from file."""
        self.data = load_dictionary()
        self._build_replacement_map()
