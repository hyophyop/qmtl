from __future__ import annotations

import ast
import gettext
import os
from pathlib import Path
from typing import Optional, Protocol


class Translator(Protocol):
    def gettext(self, message: str) -> str:
        ...


_translator: Translator = gettext.NullTranslations()
_current_language: Optional[str] = None
_language_source: Optional[str] = None  # "explicit" or "auto"


def _locale_dir() -> str:
    # qmtl/utils/i18n.py -> qmtl/locale
    return str(Path(__file__).resolve().parents[1] / "locale")


class _PoTranslations:
    def __init__(self, catalog: dict[str, str]):
        self._catalog = catalog

    def gettext(self, message: str) -> str:
        return self._catalog.get(message, message)


def _try_load_po(domain: str, localedir: str, lang: str | None) -> Optional[_PoTranslations]:
    if not lang:
        return None
    po_path = Path(localedir) / lang / "LC_MESSAGES" / f"{domain}.po"
    if not po_path.exists():
        return None
    parser = _PoParser()
    catalog = parser.parse(po_path)
    return _PoTranslations(catalog)


def set_language(lang: Optional[str]) -> None:
    """Install the language for CLI messages.

    If ``lang`` is None, detect from env. Falls back to English.
    """
    global _translator

    source = "explicit" if lang else "auto"
    if not lang:
        lang = detect_language()

    try:
        t = gettext.translation(
            domain="qmtl",
            localedir=_locale_dir(),
            languages=[lang] if lang else None,
            fallback=True,
        )
        # Prefer .po-based translations when present; otherwise fall back to
        # the standard gettext translator.
        po_fallback = _try_load_po("qmtl", _locale_dir(), lang)
        _translator = po_fallback or t
    except Exception:
        # Be resilient; always provide a translator
        po_fallback = _try_load_po("qmtl", _locale_dir(), lang)
        _translator = po_fallback or gettext.NullTranslations()
    finally:
        # Track the active language so downstream callers can decide whether to
        # reinstall translations without clobbering explicit selections.
        global _current_language, _language_source
        _current_language = lang
        _language_source = source


def _(message: str) -> str:
    """Translate a message using the currently installed translator."""
    return _translator.gettext(message)


def current_language() -> Optional[str]:
    """Return the currently installed language code, if any."""
    return _current_language


def language_source() -> Optional[str]:
    """Return how the current language was chosen ("explicit" or "auto")."""
    return _language_source


def detect_language() -> str:
    """Return preferred language code.

    Priority:
    - QMTL_LANG
    - LANGUAGE / LC_ALL / LC_MESSAGES / LANG (first two-letter code)
    - "en"
    """
    # Explicit override
    lang = os.environ.get("QMTL_LANG")
    if lang:
        return _normalize_lang(lang)

    for key in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        val = os.environ.get(key)
        if val:
            return _normalize_lang(val)
    return "en"


def _normalize_lang(value: str) -> str:
    # e.g., "ko_KR.UTF-8:en_US" -> "ko"
    token = value.split(":", 1)[0]
    token = token.split(".", 1)[0]
    token = token.replace("-", "_")
    return token.split("_", 1)[0].lower() or "en"


class _PoParser:
    def __init__(self) -> None:
        self._catalog: dict[str, str] = {}
        self._current_id: Optional[str] = None
        self._current_str: Optional[str] = None
        self._collecting: Optional[str] = None  # "id" or "str"

    def parse(self, path: Path) -> dict[str, str]:
        for raw in path.read_text(encoding="utf-8").splitlines():
            self._consume_line(raw.strip())
        self._finish_pair()
        return self._catalog

    def _consume_line(self, line: str) -> None:
        if not line or line.startswith("#"):
            return
        if line.startswith("msgid "):
            self._finish_pair()
            self._collecting = "id"
            self._current_id = self._unquote(line[6:].strip())
            self._current_str = None
            return
        if line.startswith("msgstr "):
            self._collecting = "str"
            self._current_str = self._unquote(line[7:].strip())
            return
        if line.startswith('"'):
            self._append_fragment(self._unquote(line))

    def _append_fragment(self, fragment: str) -> None:
        if self._collecting == "id" and self._current_id is not None:
            self._current_id += fragment
        elif self._collecting == "str" and self._current_str is not None:
            self._current_str += fragment

    def _finish_pair(self) -> None:
        if self._current_id is not None and self._current_str is not None:
            self._catalog[self._current_id] = self._current_str
        self._current_id = None
        self._current_str = None

    @staticmethod
    def _unquote(text: str) -> str:
        try:
            value = ast.literal_eval(text)
            return str(value)
        except (SyntaxError, ValueError):
            if text.startswith('"') and text.endswith('"'):
                return text[1:-1]
            return text
