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

    catalog: dict[str, str] = {}
    current_id: Optional[str] = None
    current_str: Optional[str] = None
    collecting: Optional[str] = None  # "id" or "str"

    def _finish_pair():
        nonlocal current_id, current_str
        if current_id is not None and current_str is not None:
            catalog[current_id] = current_str
        current_id = None
        current_str = None

    def _unquote(s: str) -> str:
        try:
            return ast.literal_eval(s)
        except (SyntaxError, ValueError):
            if s.startswith('"') and s.endswith('"'):
                s = s[1:-1]
            return s

    for raw in po_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        if line.startswith('msgid '):
            _finish_pair()
            collecting = "id"
            current_id = _unquote(line[6:].strip())
            current_str = None
            continue
        if line.startswith('msgstr '):
            collecting = "str"
            current_str = _unquote(line[7:].strip())
            continue
        if line.startswith('"'):
            frag = _unquote(line)
            if collecting == "id" and current_id is not None:
                current_id += frag
            elif collecting == "str" and current_str is not None:
                current_str += frag
            continue
        # ignore other directives (plural, context) for simplicity

    _finish_pair()
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
        # If .mo not available, provide .po fallback
        if isinstance(t, gettext.NullTranslations):
            po_fallback = _try_load_po("qmtl", _locale_dir(), lang)
            _translator = po_fallback or t
        else:
            _translator = t
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
