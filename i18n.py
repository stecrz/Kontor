"""Language of the texts the service makes (messages, notes; the log stays English).
One catalogue for everything: web/i18n.js (key -> [German, English]); without English, German counts."""
from __future__ import annotations

import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
CATALOG = os.path.join(HERE, "web", "i18n.js")
LANGS = ("de", "en")
_cat = None
_lang = "de"


def _load() -> dict:
    global _cat
    if _cat is None:
        with open(CATALOG, encoding="utf-8") as f:
            txt = f.read()
        _cat = json.loads(txt[txt.index("{"):txt.rindex("}") + 1])
    return _cat


def set_lang(lang: str) -> None:
    global _lang
    _lang = lang if lang in LANGS else "de"


def lang() -> str:
    return _lang


def tr(key: str, *args) -> str:
    """The text of the key in the language set; {0}, {1} ... are replaced by args."""
    e = _load().get(key)
    s = (e[1] if _lang == "en" and len(e) > 1 and e[1] is not None else e[0]) if e else key
    return re.sub(r"\{(\d+)\}", lambda m: str(args[int(m.group(1))]), s) if args else s


def trn(key: str, n: int, *args) -> str:
    """Like tr with n as {0} and the text "singular|plural": the form for n (as tn in app.js)."""
    f = tr(key, n, *args).split("|")
    return f[0] if len(f) == 1 or n == 1 else f[1]
