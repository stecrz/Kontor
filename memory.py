"""The assistant's memory: what the user told it to remember -- about themselves, their plans, decisions, people, preferences
and how it should answer. A second brain on this Mac, kept beside the model (the model itself never changes or grows):

  notes    short texts in the user's own words, each with its date and where it came from (a conversation, the settings, a
           backup). Encrypted in Kontor's data folder (memory-notes-0001.json, ...: at most SEGMENT notes per file, so that
           a change writes one small file however much is remembered, and a damaged file loses one file's notes, never
           all). In the backup; never in the log or a package; a reset and removing Kontor delete them.
  profile  the few notes every question is given (pinned ones first, then the latest made or used), within a fixed budget --
           so that a question costs the same however much is remembered. Everything else is found by searching.
  search   by words, without a model (search, recall): word forms (Urlaube finds Urlaub, Häuser Haus), parts of compound
           words (Urlaubskasse finds Urlaub, Berater Steuerberater), slips of a letter (Urlaup). What fits a question comes
           with it (recall, within a fixed budget); the notes an answer rested on count as used (touch: memory-used.json).
           And by meaning, when the small model for it is on this Mac (assistant.py): every note's embedding beside its file
           (memory-vectors-0001.json, ...: encrypted like the notes, made anew when a note or the model changes, gone with
           the note); then "Ferien" finds "Urlaub". Without that model the word search stays.

Only Kontor reads and writes here. The model has no way to this file: it runs in a sandbox that cannot read Kontor's data, and
it has no tool that writes a note. What becomes a note is decided outside its answer (assistant.py).

A note that replaces another names it (replaces); the older one stays, marked as replaced, until the user deletes it -- taking
the newer one away brings it back. Forgetting deletes: the note is gone from its file at once.

Never remembered: passwords, PINs, TANs, keys, card numbers (secret_problem) -- Kontor stores no credentials.
A backup is a file from outside: what comes back from one says so (how "backup"), is told to the log, and can replace
nothing that was there.
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import math
import operator
import os
import re
import secrets
import threading
import unicodedata
from array import array
from collections import Counter
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, Iterable, List, Optional, Set, Tuple

from i18n import tr
from storage import StoreLocked
from web_search import GENERIC, LEGAL, _INVISIBLE, _fold

log = logging.getLogger("kontor.memory")

FILE = "memory-notes-%04d.json"                    # in Kontor's data folder, beside its other files (encrypted; a new data key covers every file there)
SEGMENT = 1000                                     # notes in one file at most
FORMAT = 1                                         # of a file of notes (and of the notes in a backup)
TEXT_MAX = 600                                     # characters of one note
PROFILE_TOKENS = 1500                              # the profile at most (less in a small context: profile_budget)
RECALL_TOKENS = 500                                # notes that fit a question, given with it (less in a small context: recall_budget)
USED_FILE = "memory-used.json"                     # when a note last helped an answer (beside the notes, encrypted): the profile prefers those
SEARCH_TERMS = 300                                 # different words of a query looked at (a long pasted text: those at its beginning and end)
WORD_MAX = 40                                      # letters of a word at most (longer: no word -- a code, a link -- and searching it would take long)
PART, SLIP = 0.7, 0.6                              # how well a part of a compound word (at most), a slip of a letter matches (the same word: 1)
VEC_FILE = "memory-vectors-%04d.json"              # beside each file of notes: their embeddings (finding by meaning; encrypted, made anew when needed)
SEM_FLOOR, SEM_MIN = 0.3, 0.5                      # likeness of a note's and a question's embeddings: below the floor it counts nothing; found by meaning alone from SEM_MIN
TALKS_FILE = "memory-chats-%04d.json"              # what the saved conversations said, to search them (Talks; encrypted, a few conversations per file)
TALKS_PER_FILE = 10
TALK_Q, TALK_A = 800, 900                          # characters of a question, of an answer kept for searching
HOWS = ("chat", "manual", "backup")                # where a note came from: said in a conversation, typed in the settings, restored
KINDS = ("", "fact", "preference", "plan", "decision", "person", "reason", "style")       # what it is about ("": not told)
# words that say nothing about what a text is about (folded as _fold does: ae, oe, ue, ss): left out when texts are compared
STOP = frozenset("""aber alle allem allen aller alles also andere anderen auch auf aus bei beim bin bis bist bitte dann das dass dein deine deinem deinen deiner dem den
denn der des dich die dies diese diesem diesen dieser dieses dir doch dort durch eben ein eine einem einen einer eines einmal etwas euch fuer ganz gar gegen geht
gibt habe haben hast hat hatte hier ich ihm ihn ihr ihre ihrem ihren immer ins ist jetzt kann kein keine keinem keinen koennen mal man mehr mein meine meinem
meinen meiner mich mir mit muss nach nicht nichts noch nun nur oder ohne schon sehr sein seine seinem seinen seiner seit sich sie sind soll sollen sollte ueber
und uns unser unsere unter viel vom von vor wann war waren warum was weil welche welchem welchen welcher wenn wer werde werden wie wieder will wir wird wirst wo
wollen worden wuerde wurde zu zum zur zwar about after again all also and any are because been before being but can could did does doing for from had has have
her here him his how into its just more most not now off once only other our out over own she should some such than that the their them then there these they
this those through too under until very was were what when where which while who why will with would you your""".split())
_SEG_NAME = re.compile(r"memory-notes-(\d{4,6})\.json(?:\.enc)?")
_VEC_NAME = re.compile(r"memory-vectors-(\d{4,6})\.json(?:\.enc)?")
_TALK_NAME = re.compile(r"memory-chats-(\d{4,6})\.json(?:\.enc)?")
_CID = re.compile(r"[0-9a-f]{8,32}")
_NOTE_ID = re.compile(r"n[0-9a-f]{10}")
_MORE_INVISIBLE = re.compile("[\u180b-\u180d\u2800\U000e0100-\U000e01ef]")      # further characters nobody sees (variation selectors, a blank braille cell)


class NoteError(ValueError):
    """A note that cannot be kept (empty, too long, a credential) -- its text is for the user."""


def profile_budget(context: int) -> int:
    """Tokens the profile may take: PROFILE_TOKENS, in a small context about 4.5 % of it."""
    return max(300, min(PROFILE_TOKENS, int(context) // 22))


def recall_budget(context: int) -> int:
    """Tokens the notes that fit a question may take: RECALL_TOKENS, in a small context about 2.5 % of it."""
    return max(150, min(RECALL_TOKENS, int(context) // 40))


# -- finding notes by their words (no model: the standard library only) --------------------------------------------------------
def stem(w: str) -> str:
    """A folded word (as _fold gives it) without its ending, so that its forms meet: Urlaube, Urlauben, Urlaubs -> urlaub;
    Häuser (haeuser) -> haus, Bänke -> bank (an umlaut counts as its vowel); payments -> payment, booked -> book. Never shorter
    than four letters; a word with a digit stays as it is. A key to compare by, not a word to show."""
    if any(c.isdigit() for c in w):
        return w
    w = w.replace("ae", "a").replace("oe", "o").replace("ue", "u")
    while True:
        if len(w) > 6 and w.endswith(("ern", "ing")):
            w = w[:-3]
        elif len(w) > 5 and w.endswith(("em", "er", "en", "es", "nd", "ed")):
            w = w[:-2]
        elif len(w) > 4 and w[-1] in "esn":
            w = w[:-1]
        else:
            return w


def terms(text: Any) -> List[str]:
    """The words of a text that say what it is about, as search compares them: folded, without words like "und", "the"
    (STOP), stemmed; numbers of two digits and more as they are; nothing longer than WORD_MAX."""
    out = []
    for w in _fold(text).split():
        if len(w) > WORD_MAX:
            continue
        if any(c.isdigit() for c in w):
            if len(w) >= 2:
                out.append(w)
        elif len(w) >= 3 and w not in STOP:
            out.append(stem(w))
    return out


def _grams(t: str) -> Set[str]:
    """The three-letter pieces of a word, with its beginning and end marked (^ur, rla, ub$)."""
    p = "^" + t + "$"
    return {p[i:i + 3] for i in range(len(p) - 2)}


def _near(a: str, b: str, k: int) -> bool:
    """Whether a turns into b with at most k letters changed, added, left out or swapped with their neighbour."""
    if abs(len(a) - len(b)) > k:
        return False
    before: List[int] = []
    prev = list(range(len(b) + 1))
    for i in range(1, len(a) + 1):
        cur = [i] + [0] * len(b)
        for j in range(1, len(b) + 1):
            v = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (a[i - 1] != b[j - 1]))
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                v = min(v, before[j - 2] + 1)
            cur[j] = v
        if min(cur) > k:
            return False
        before, prev = prev, cur
    return prev[-1] <= k


def _rank(ix: "_Index", query: Any, more: Any, skip: Set[str], valid: Any, like: Optional[Dict[str, float]]) -> List[Tuple[float, str]]:
    """(score, id) of what fits a query (see Memory.search) -- only ids in valid, none in skip; like: how alike each is by
    meaning (None: words alone)."""
    some = lambda ts: ts if len(ts) <= SEARCH_TERMS else ts[:SEARCH_TERMS // 2] + ts[-(SEARCH_TERMS // 2):]
    asked: Dict[str, float] = {t: 1.0 for t in some(list(dict.fromkeys(terms(query))))}
    for t in some(list(dict.fromkeys(terms(more)))):
        asked.setdefault(t, 0.5)
    best: Dict[str, Dict[str, float]] = {}               # id -> query word -> how well
    tells: Set[str] = set()
    for q, weight in asked.items():
        for t, how in ix.like(q).items():
            gain = weight * how * ix.idf(t)
            for nid in ix.post[t]:
                mine = best.setdefault(nid, {})
                if gain > mine.get(q, 0.0):
                    mine[q] = gain
                if ix.telling(t):
                    tells.add(nid)
    scored = [(sum(v.values()), nid) for nid, v in best.items() if nid in tells and nid not in skip and nid in valid]
    if like is not None:                                 # by words and by meaning together
        top_w = max((sc for sc, _ in scored), default=0.0) or 1.0
        words = {nid: sc / top_w for sc, nid in scored}
        sem = lambda nid: max(0.0, (like.get(nid, 0.0) - SEM_FLOOR) / (1 - SEM_FLOOR))
        found = set(words) | {nid for nid, c in like.items() if c >= SEM_MIN and nid not in skip and nid in valid}
        scored = [(words.get(nid, 0.0) + sem(nid), nid) for nid in found]
    if not scored:
        return []
    top = max(sc for sc, _ in scored)
    return [(sc, nid) for sc, nid in scored if sc >= top * 0.25]


def pack(v: Iterable[float]) -> array:
    """An embedding as it is kept: a byte per number (-127 ... 127, scaled to its largest) -- a quarter of the room, and what
    comparing needs (only the direction counts)."""
    v = [float(x) for x in v]
    top = max((abs(x) for x in v), default=0.0) or 1.0
    return array("b", [max(-127, min(127, int(round(x / top * 127)))) for x in v])


def _norm(a: array) -> float:
    return math.sqrt(sum(x * x for x in a)) or 1.0


def _text_key(text: str) -> str:
    """Which text an embedding was made of (a note changed since: made anew)."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


class _Index:
    """The words of the notes that count, for search: which notes hold a word, and the words by their pieces (to find parts
    of compound words and slips of a letter without comparing every word). Built anew after a change (search needs it)."""

    def __init__(self, notes: Iterable[dict]):
        self.post: Dict[str, Set[str]] = {}
        self.n = 0
        for n in notes:
            self.n += 1
            for t in n["terms"] if "terms" in n else set(terms(n["text"])):
                self.post.setdefault(t, set()).add(n["id"])
        self.grams: Dict[str, Set[str]] = {}
        for t in self.post:
            if not any(c.isdigit() for c in t):
                for g in _grams(t):
                    self.grams.setdefault(g, set()).add(t)

    def idf(self, t: str) -> float:
        """How much a word says: the fewer notes hold it, the more."""
        return math.log(1.0 + self.n / len(self.post[t]))

    def telling(self, t: str) -> bool:
        """A word not in most notes (with a few notes: any) -- one that can tell a note from the others."""
        return len(self.post[t]) <= max(3, self.n * 0.3)

    def like(self, q: str, inside: bool = True) -> Dict[str, float]:
        """The words of the notes a word of a query finds, each with how well: 1 the same word (in any of its forms), PART a
        part of a compound word or the compound of a part (less, the less of the longer word it is) (four letters and more at its beginning or end, five inside; the
        rest three letters at least: teuer is no part of Steuer),
        SLIP a slip of one letter (two in words of nine letters and more; words of five letters and more). inside: also the
        words of the notes that are a part of q (Urlaubskasse finds Urlaub; not in the list's filter, which finds what is typed)."""
        out: Dict[str, float] = {}
        if q in self.post:
            out[q] = 1.0
        if any(c.isdigit() for c in q):                  # numbers: only as they are
            return out
        if len(q) >= 4:                                  # q in a longer word of the notes: every inner piece of q is in it
            inner = [q[i:i + 3] for i in range(len(q) - 2)]
            have = set.intersection(*(self.grams.get(g, set()) for g in inner))
            for t in have:
                if len(t) >= len(q) + 3 and (t.startswith(q) or t.endswith(q) or (len(q) >= 5 and q in t)):
                    out[t] = max(out.get(t, 0.0), PART * (0.5 + 0.5 * len(q) / len(t)))
        for i in range(len(q) if inside else 0):         # a word of the notes in q (Urlaubskasse: urlaub)
            for j in range(i + 4, len(q) + 1):
                part = q[i:j]
                if len(q) >= len(part) + 3 and part in self.post and (i == 0 or j == len(q) or len(part) >= 5):
                    out[part] = max(out.get(part, 0.0), PART * (0.5 + 0.5 * len(part) / len(q)))
        if len(q) >= 5:
            k = 1 if len(q) <= 8 else 2
            shared = Counter(t for g in _grams(q) for t in self.grams.get(g, ()))
            need = max(1, len(q) - 4 * k)                # one change touches at most four pieces
            for t, c in shared.items():
                if c >= need and t not in out and len(t) >= 5 and _near(q, t, k):
                    out[t] = SLIP
        return out


def clean(text: Any) -> str:
    """A note's text as it is kept: one paragraph, no control or invisible characters (text nobody sees must not reach the
    model), spaces put in order."""
    t = unicodedata.normalize("NFC", str(text or ""))
    t = _MORE_INVISIBLE.sub("", _INVISIBLE.sub("", "".join(" " if c in "\r\n\t\u2028\u2029" else c for c in t)))
    t = "".join(c for c in t if unicodedata.category(c) not in ("Cc", "Cf", "Co", "Cs", "Cn"))
    return re.sub(r"\s+", " ", t).strip()


_L = "A-Za-zÄÖÜäöüß"
_NOT_IN_A_WORD = r"(?<![%s])" % _L, r"(?![%s])(?!-[%s])" % (_L, _L)       # not the middle of a word, not the first part of one (TAN-Verfahren, PIN-Brief)
# a secret word and its value: after ":", "=" or "is" (within the sentence) -- a value with a digit or of eight characters and more
_WORD_SECRET = re.compile(_NOT_IN_A_WORD[0] + r"(?:(?:[%s]+[\s-]?)?(?:passwort|passw(?:ö|oe)rter|passwords?|passphrase|kennwort|kennw(?:ö|oe)rter)|pw|passcode|secret|"
                          r"token|api[\s_-]?(?:keys?|schl(?:ü|ue)ssel)|private[\s_-]?key|zugangscode|login)" % _L + _NOT_IN_A_WORD[1]
                          + r"[^.!?]{0,60}?(?::|=|\blautet\b|\bist\b|\bis\b|\bhei(?:ß|ss)t\b)\s*[\"'„“‚‘«»]?(\S{3,})", re.I)
# a number that is a secret: a few digits after its word, with or without "is" (PIN 4711, CVV: 123, Geheimzahl ist die 0815)
_NUMBER_SECRET = re.compile(_NOT_IN_A_WORD[0] + r"(?:(?:karten|handy|sim|konto|online|banking|ec|giro|app)[\s-]?)?(?:pins?|pin[\s-]?codes?|puks?|tans?|cvv2?|cvc2?|"
                            r"geheimzahl(?:en)?|sicherheitscodes?|pr(?:ü|ue)fziffern?)" + _NOT_IN_A_WORD[1] + r"[^.!?\d]{0,24}?(?<![\d.,])(\d{3,8})(?![\d%s]|[.,]\d|-[%s])" % (_L, _L), re.I)
_CODE_PART = re.compile(r"[A-Za-z0-9_+=]{20,}")      # a long random code: a part of twenty and more characters with small and capital letters and digits
_DIGITS = re.compile(r"(?<!\w)\d(?:[ .\-]?\d)*(?!\w)")                # a run of digits, also in groups


def _luhn(digits: str) -> bool:
    total = 0
    for i, c in enumerate(reversed(digits)):
        d = int(c)
        if i % 2:
            d = d * 2 - 9 if d > 4 else d * 2
        total += d
    return total % 10 == 0


def _card(d: str) -> bool:
    """A payment card by its length, the start of its number and its check digit."""
    return ((len(d) == 16 and (d[0] == "4" or 51 <= int(d[:2]) <= 55 or 2221 <= int(d[:4]) <= 2720)) or (len(d) == 15 and d[:2] in ("34", "37"))) and _luhn(d)


def secret_problem(text: str) -> bool:
    """Whether a text holds a credential: a password or key with its value, a PIN, TAN or card check number, a long random
    code, a card number (also with its expiry date or check number behind it). In doubt yes -- the user is told and can
    say it without the value."""
    for m in _WORD_SECRET.finditer(text):
        v = m.group(1).strip("\"'„“‚‘«».,;")
        if any(c.isdigit() for c in v) or len(v) >= 8:
            return True
    if _NUMBER_SECRET.search(text):
        return True
    for m in _CODE_PART.finditer(text):
        v = m.group(0)
        if all(re.search(p, v) for p in (r"[a-z]", r"[A-Z]", r"\d")):
            return True
    for m in _DIGITS.finditer(text):
        if re.search(r"[A-Z]{2}\d{2} ?$", text[max(0, m.start() - 6):m.start()]):       # (the digits of an IBAN are no card)
            continue
        groups = re.split(r"[ .\-]", m.group(0))
        for i in range(len(groups)):                     # the card's own groups, whatever stands before or behind them
            d = ""
            for g in groups[i:]:
                d += g
                if len(d) >= 15 and _card(d):
                    return True
                if len(d) > 16:
                    break
    return False


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _stamp(v: Any, fallback: str) -> str:
    """A time as a note keeps it ("2026-11-22 10:00:00") -- a real one, and not in the future; anything else: the fallback."""
    t = str(v or "")
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}", t):
        return fallback
    try:
        when = datetime.strptime(t, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return fallback
    return t if datetime(1990, 1, 1) <= when <= datetime.now() + timedelta(days=1) else fallback


def same_text(t: str) -> str:
    """Two notes are the same when they differ in capitals and spaces only (a sign counts: "> 60 %" is not "< 60 %")."""
    return re.sub(r"\s+", " ", t).strip().casefold()


def _valid(n: Any) -> Optional[dict]:
    """A note as read from a file or a backup: checked, cut to what a note may hold -- None if it is none."""
    if not isinstance(n, dict) or not _NOTE_ID.fullmatch(str(n.get("id") or "")):
        return None
    text = clean(n.get("text"))[:TEXT_MAX]
    if not text:
        return None
    created = _stamp(n.get("created"), _now())
    src = n.get("source") if isinstance(n.get("source"), dict) else {}
    out: Dict[str, Any] = {"id": n["id"], "text": text, "created": created, "changed": max(created, _stamp(n.get("changed"), created)),
                           "source": {"how": src.get("how") if src.get("how") in HOWS else "manual"}}
    if re.fullmatch(r"[0-9a-f]{8,32}", str(src.get("chat") or "")):
        out["source"]["chat"] = src["chat"]
    if src.get("pasted") is True:
        out["source"]["pasted"] = True
    if n.get("pinned") is True:
        out["pinned"] = True
    if n.get("kind") in KINDS and n.get("kind"):
        out["kind"] = n["kind"]
    rep = [r for r in n.get("replaces") or [] if isinstance(r, str) and _NOTE_ID.fullmatch(r) and r != n["id"]] if isinstance(n.get("replaces"), list) else []
    if rep:
        out["replaces"] = rep[:20]
    names = [clean(x)[:60] for x in n.get("names") or [] if isinstance(x, str) and clean(x)] if isinstance(n.get("names"), list) else []
    if names:
        out["names"] = names[:12]
    return out


class Memory:
    """The notes, held in memory once read (lazily: nothing is read before the first use) and written file by file."""

    def __init__(self, store, on_change: Optional[Callable[[str, dict, dict], None]] = None):
        """on_change(what, note, more): told after "remember", "replace", "edit", "forget", "forget_all", "restore", "backup"
        -- for the log of changes (assistant.py). Called after the memory's lock is released."""
        self.store = store
        self.on_change = on_change
        self.lock = threading.RLock()
        self._notes: Optional[Dict[str, dict]] = None      # id -> note, in the order they were made
        self._seg: Dict[str, int] = {}                     # id -> number of its file
        self._by_seg: Dict[int, List[str]] = {}            # number of a file -> the ids in it
        self._broken: Set[int] = set()                     # files that could not be read: never written again
        self._replaced: Dict[str, str] = {}                # id of a replaced note -> id of the note that replaced it
        self._used: Dict[str, str] = {}                    # id -> when it last helped an answer (USED_FILE)
        self._vec: Dict[str, Tuple[str, str, array, float]] = {}    # id -> (model, key of its text, embedding, its length): finding by meaning
        self._rev = 0                                      # counts every change of the notes (search builds its index anew)
        self._ix: Optional[Tuple[int, _Index]] = None
        self.epoch = 0                                     # counts changes made outside a conversation (the profile is built anew)

    # -- files ---------------------------------------------------------------------------------------------------------------
    def _file(self, seg: int) -> str:
        return FILE % seg

    def _segments(self) -> List[int]:
        return self._names(_SEG_NAME)

    def _names(self, pattern: "re.Pattern[str]") -> List[int]:
        try:
            names = os.listdir(self.store.data_dir)
        except OSError:
            return []
        out = set()
        for name in names:
            m = pattern.fullmatch(name)
            if m and name.endswith(".enc") == bool(self.store.encrypted):
                out.add(int(m.group(1)))
        return sorted(out)

    def _write_vectors(self, seg: int) -> None:
        """The embeddings of the notes in one file of notes, beside it (none left: the file goes), each with its model. Only
        what is made of the notes as they are: a forgotten note's embedding goes with it (it says something about its text)."""
        mine = {nid: self._vec[nid] for nid in self._by_seg.get(seg) or [] if nid in self._vec}
        if not mine:
            self.store.delete(VEC_FILE % seg)
            return
        self.store.save(VEC_FILE % seg, {"v": FORMAT, "vecs": {nid: [v[1], base64.b64encode(v[2].tobytes()).decode("ascii"), v[0]] for nid, v in mine.items()}})

    def _drop_vector(self, nid: str, seg: Optional[int]) -> None:
        """A note changed: its embedding (of the old text) goes. Raises when its file cannot be written."""
        if self._vec.pop(nid, None) is not None and seg is not None:
            self._write_vectors(seg)

    def _load(self) -> Dict[str, dict]:
        if self._notes is not None:
            return self._notes
        if getattr(self.store, "is_open", True) is False:      # nobody signed in yet: nothing is read (and nothing taken for missing or damaged)
            raise StoreLocked("locked")
        notes: Dict[str, dict] = {}
        self._seg, self._by_seg, self._broken = {}, {}, set()
        for seg in self._segments():
            try:
                raw = self.store.read_bytes(self._file(seg))
                doc = json.loads(raw.decode("utf-8")) if raw is not None else {}
                if not isinstance(doc, dict) or not isinstance(doc.get("notes"), list) or not isinstance(doc.get("v"), int) or doc["v"] > FORMAT:
                    raise ValueError("format")
            except StoreLocked:                          # locked meanwhile: not "damaged" -- read again after the sign-in
                raise
            except Exception as e:                       # damaged, or written by a newer Kontor: left as it is, its notes are missing
                log.warning("Memory: a file of notes is not readable (%s) -- it stays untouched", type(e).__name__)
                self._broken.add(seg)
                continue
            self._by_seg[seg] = []
            for raw_note in doc["notes"]:
                n = _valid(raw_note)
                if n is not None and n["id"] not in notes:
                    notes[n["id"]] = n
                    self._put(n["id"], seg)
        try:                                             # when notes helped an answer: lost, it is only an order (never a reason to fail)
            used = self.store.load(USED_FILE, {})
        except StoreLocked:
            raise
        except Exception as e:
            log.warning("Memory: the file of used notes is not readable (%s) -- written anew", type(e).__name__)
            used = {}
        used = used.get("used") if isinstance(used, dict) and isinstance(used.get("used"), dict) else {}
        self._used = {k: _stamp(v, "") for k, v in used.items() if k in notes and _stamp(v, "")}
        self._vec = {}
        for name in self._names(_VEC_NAME):              # the embeddings: made of the notes, so a file that cannot be read is made anew
            try:
                doc = self.store.load(VEC_FILE % name, {})
                for nid, entry in (doc.get("vecs") or {}).items():
                    key, b64, model = (list(entry) + ["", "", ""])[:3] if isinstance(entry, list) else ("", "", "")
                    if nid in notes and isinstance(key, str) and isinstance(b64, str) and isinstance(model, str) and key and b64:
                        a = array("b", base64.b64decode(b64))
                        if a:
                            self._vec[nid] = (model, key, a, _norm(a))
            except StoreLocked:
                raise
            except Exception as e:
                log.warning("Memory: a file of embeddings is not readable (%s) -- made anew", type(e).__name__)
        self._notes = notes
        self._rev += 1
        self._relink()
        return notes

    def _put(self, nid: str, seg: int) -> None:
        self._seg[nid] = seg
        self._by_seg.setdefault(seg, []).append(nid)

    def _take(self, nid: str) -> int:
        seg = self._seg.pop(nid)
        self._by_seg[seg].remove(nid)
        return seg

    def _relink(self) -> None:
        """Which note is replaced by which (told by the newer one only: one file is written per change, never two)."""
        notes = self._notes or {}
        self._replaced = {old: n["id"] for n in notes.values() for old in n.get("replaces") or [] if old in notes}

    def _write(self, seg: int) -> None:
        self._rev += 1                                   # (also when writing fails: the caller puts it back -- a change either way)
        notes = self._notes or {}
        mine = [notes[i] for i in self._by_seg.get(seg) or []]
        if not mine:
            self.store.delete(self._file(seg))
            self._by_seg.pop(seg, None)
            return
        self.store.write_bytes(self._file(seg), json.dumps({"v": FORMAT, "notes": mine}, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))

    def _free_segment(self) -> int:
        """The file a new note goes into: the last one while it has room, else a new one -- never one that could not be read,
        and never one that Kontor has not read itself (a file put into the folder while Kontor runs is not overwritten)."""
        on_disk = self._segments()
        last = max(list(self._by_seg) + sorted(self._broken) + on_disk + [0])
        mine = last in self._by_seg and last not in self._broken
        return last if last and mine and len(self._by_seg[last]) < SEGMENT else last + 1

    def _tell(self, what: str, note: dict, **more) -> None:
        if self.on_change is not None:
            try:
                self.on_change(what, note, more)
            except Exception as e:  # pragma: no cover - the log must never stop the memory
                log.warning("Memory: change not logged (%s)", type(e).__name__)

    # -- reading -------------------------------------------------------------------------------------------------------------
    def get(self, nid: str) -> Optional[dict]:
        with self.lock:
            n = self._load().get(str(nid))
            return dict(n) if n else None

    def active(self) -> List[dict]:
        """The notes that count (not replaced), the latest first."""
        with self.lock:
            notes = self._load()
            pos = {nid: i for i, nid in enumerate(notes)}      # made in the same second: the later one first
            return sorted((n for n in notes.values() if n["id"] not in self._replaced), key=lambda n: (n["changed"], pos[n["id"]]), reverse=True)

    def stats(self) -> dict:
        with self.lock:
            notes = self._load()
            act = [n for n in notes.values() if n["id"] not in self._replaced]
            size = 0
            for seg in self._segments():
                try:
                    size += os.path.getsize(self.store.path(self._file(seg)))
                except OSError:
                    pass
            return {"notes": len(act), "pinned": sum(1 for n in act if n.get("pinned")), "replaced": len(self._replaced), "bytes": size,
                    "broken": len(self._broken)}

    def view(self, n: dict) -> dict:
        """A note as the page shows it."""
        out = {k: n[k] for k in ("id", "text", "created", "changed", "kind") if k in n}
        out.update(pinned=bool(n.get("pinned")), how=n["source"]["how"], chat=n["source"].get("chat", ""), pasted=bool(n["source"].get("pasted")))
        if n["id"] in self._replaced:
            out["replaced_by"] = self._replaced[n["id"]]
        olds = [self._notes[o]["text"] for o in n.get("replaces") or [] if self._notes and o in self._notes]
        if olds:
            out["replaces"] = olds
        return out

    def listing(self, query: str = "", offset: int = 0, limit: int = 50, replaced: bool = False) -> dict:
        """The notes for the list in the settings: pinned ones first, then the latest; query: every word of it must be in the
        note (folded: Müller finds Mueller). replaced: the replaced ones too. A piece of the list (offset, limit: 200 at most)."""
        words = _fold(query).split()
        with self.lock:
            notes = self._load()
            rows = [n for n in notes.values() if (replaced or n["id"] not in self._replaced)]
            if words:                                    # as typed (a beginning: "Urla"), or a form, a part, a slip of it
                found = [self._hits(w) for w in words]
                rows = [n for n in rows if all(w in _fold(n["text"]) or n["id"] in h for w, h in zip(words, found))]
            pos = {nid: i for i, nid in enumerate(notes)}
            rows.sort(key=lambda n: (n["id"] not in self._replaced, bool(n.get("pinned")), n["changed"], pos[n["id"]]), reverse=True)
            offset, limit = max(0, int(offset)), max(1, min(200, int(limit)))
            return dict(self.stats(), total=len(rows), offset=offset, items=[self.view(n) for n in rows[offset:offset + limit]])

    # -- search ----------------------------------------------------------------------------------------------------------------
    def _index(self) -> _Index:
        with self.lock:
            self._load()
            if self._ix is None or self._ix[0] != self._rev:
                self._ix = (self._rev, _Index(n for n in self._notes.values() if n["id"] not in self._replaced))
            return self._ix[1]

    def _hits(self, word: str) -> Set[str]:
        """The notes that count holding a folded word in one of its forms, as a part or with a slip (for the list's filter)."""
        if len(word) < 3 or word in STOP:
            return set()
        ix = self._index()
        return {nid for t in ix.like(stem(word), inside=False) for nid in ix.post[t]}

    # -- by meaning --------------------------------------------------------------------------------------------------------------
    def vectors_missing(self, model: str, limit: int) -> List[Tuple[str, str]]:
        """(id, text) of notes that count without an embedding of this model made of their text -- the latest first."""
        with self.lock:
            out = []
            for n in self.active():
                v = self._vec.get(n["id"])
                if v is None or v[0] != model or v[1] != _text_key(n["text"]):
                    out.append((n["id"], n["text"]))
                    if len(out) >= limit:
                        break
            return out

    def set_vectors(self, model: str, got: Dict[str, Tuple[str, Iterable[float]]]) -> int:
        """Embeddings made: id -> (the text it was made of, the numbers). Kept only for a note that is still there with that
        very text (changed or forgotten meanwhile: thrown away), written file by file. Returns how many were kept."""
        with self.lock:
            notes = self._load()
            segs: Set[int] = set()
            for nid, (text, vec) in got.items():
                n = notes.get(nid)
                if n is None or n["text"] != text or nid not in self._seg:
                    continue
                a = pack(vec)
                self._vec[nid] = (model, _text_key(text), a, _norm(a))
                segs.add(self._seg[nid])
            for seg in segs:
                self._write_vectors(seg)
            return sum(1 for nid in got if nid in self._vec and self._vec[nid][0] == model)

    def vector_stats(self, model: str) -> Tuple[int, int]:
        """(notes with an embedding of this model, notes that count)."""
        with self.lock:
            act = self.active()
            return sum(1 for n in act if (self._vec.get(n["id"]) or ("",))[0] == model and self._vec[n["id"]][1] == _text_key(n["text"])), len(act)

    def _likeness(self, model: str, q: array) -> Dict[str, float]:
        """How alike each note that counts (with an embedding of this model, of its text as it is) is to a question's embedding:
        -1 ... 1 (the cosine of the angle between them)."""
        qn = _norm(q)
        out = {}
        for nid, n in (self._notes or {}).items():
            v = self._vec.get(nid)
            if v is None or v[0] != model or nid in self._replaced or len(v[2]) != len(q) or v[1] != _text_key(n["text"]):
                continue
            out[nid] = sum(map(operator.mul, q, v[2])) / (qn * v[3])
        return out

    def search(self, query: Any, limit: int = 10, exclude: Iterable[str] = (), more: Any = "", meaning: Optional[Tuple[str, array]] = None) -> List[dict]:
        """The notes that count which fit a query best, each with its score: every word of the query (more: words that count
        half -- the question before, for "and in May?") adds how well a note holds it (like) times how much the word says
        (idf). Only notes holding at least one word that tells them apart (telling: a word in nearly every note finds
        nothing alone), and only those not far behind the best (a quarter of its score). The best first; pinned and later
        ones first among equals. meaning: (model, the query's embedding packed) -- then also by meaning: a note as alike as
        SEM_MIN is found without a word in common, and likeness adds to the score of a note found by its words (both parts
        0 ... 1: words as a share of the best, likeness from SEM_FLOOR up)."""
        with self.lock:
            notes = self._notes if self._notes is not None else self._load()
            like = self._likeness(meaning[0], meaning[1]) if meaning is not None else None
            scored = _rank(self._index(), query, more, set(exclude), notes, like)
            if not scored:
                return []
            pos = {nid: i for i, nid in enumerate(notes)}
            scored.sort(key=lambda x: (round(x[0], 6), bool(notes[x[1]].get("pinned")), notes[x[1]]["changed"], pos[x[1]]), reverse=True)
            return [dict(notes[nid], score=round(s, 3)) for s, nid in scored[:max(1, int(limit))]]

    def recall(self, query: Any, budget_tokens: int = RECALL_TOKENS, exclude: Iterable[str] = (), more: Any = "", meaning: Optional[Tuple[str, array]] = None) -> List[dict]:
        """The notes that fit a question, as many as fit into the budget (counted as the profile counts) -- the best first."""
        room = max(0, int(budget_tokens)) * 3
        out = []
        for n in self.search(query, 40, exclude, more, meaning):
            cost = len(n["text"]) + 16
            if cost <= room:
                out.append(n)
                room -= cost
            elif room < 60:
                break
        return out

    def rested_on(self, notes: Iterable[dict], answer: Any) -> List[dict]:
        """Of the notes an answer was given, those it rests on: it holds enough of their words (two and a third of them, a
        note of one or two words: all) -- the same word in any form, or a part of a compound word. A sign, not a proof (the
        model may say it in other words); what it finds is shown under the answer and counts as used."""
        said = set(terms(answer))
        if not said:
            return []

        def holds(t: str) -> bool:
            if t in said:
                return True
            if any(c.isdigit() for c in t) or len(t) < 5:
                return False
            return any(len(a) >= 5 and (a.startswith(t) or t.startswith(a)) for a in said if not any(c.isdigit() for c in a))
        out = []
        for n in notes:
            mine = set(terms(n.get("text")))
            have = sum(1 for t in mine if holds(t))
            if mine and ((have >= 2 and have * 3 >= len(mine)) or (len(mine) <= 2 and have == len(mine))):
                out.append((have / len(mine), have, n))
        out.sort(key=lambda x: x[:2], reverse=True)
        return [n for _, _, n in out]

    def touch(self, ids: Iterable[str]) -> None:
        """These notes helped an answer just now: the profile takes them as if they were new (USED_FILE; one small file, the
        notes themselves are not written). Not a change the profile of a running conversation follows (no epoch)."""
        with self.lock:
            notes = self._load()
            now = _now()
            fresh = [i for i in ids if i in notes]
            if not fresh:
                return
            for i in fresh:
                self._used[i] = now
            self._used = {k: v for k, v in self._used.items() if k in notes}
            try:
                self.store.save(USED_FILE, {"v": FORMAT, "used": self._used})
            except Exception as e:                       # only an order: the answer stands
                log.warning("Memory: used notes not written (%s)", type(e).__name__)

    def profile(self, budget_tokens: int = PROFILE_TOKENS) -> List[dict]:
        """The notes every question is given: pinned ones first, then the others -- each the latest made, changed or used first
        -- as many as fit into the budget (a token counted as three characters, as everywhere in the assistant: rather too
        few than too many). A note that does not fit any more is left out and the next shorter one tried, so that the room
        is used."""
        room = max(0, int(budget_tokens)) * 3
        out: List[dict] = []
        act = self.active()
        with self.lock:                                  # the latest made, changed or used first (an answer rested on it: it matters)
            used = lambda n: self._used.get(n["id"], "")
            act.sort(key=lambda n: (max(n["changed"], used(n)), used(n) >= n["changed"]), reverse=True)        # (stable: made in the same second as before)
        for n in [n for n in act if n.get("pinned")] + [n for n in act if not n.get("pinned")]:
            cost = len(n["text"]) + 16                  # "- [2026-11-22] " and the line break
            if cost <= room:
                out.append(dict(n))
                room -= cost
            elif room < 60:
                break
        return out

    # -- writing -------------------------------------------------------------------------------------------------------------
    def check(self, text: Any) -> str:
        """A note's text, cleaned -- NoteError if it cannot be kept."""
        t = clean(text)
        if not t:
            raise NoteError(tr("s_ki_g_leer"))
        if len(t) > TEXT_MAX:
            raise NoteError(tr("s_ki_g_zu_lang", TEXT_MAX))
        if secret_problem(t):
            raise NoteError(tr("s_ki_g_zugangsdaten"))
        return t

    def add(self, text: Any, how: str = "manual", chat: str = "", pinned: bool = False, kind: str = "", replaces: Iterable[str] = (),
            pasted: bool = False, names: Iterable[str] = (), quiet: bool = False, by: str = "") -> dict:
        """Remembers a note. replaces: notes it takes the place of (they stay, marked as replaced). The same text as a note
        that counts: that one is returned (known), nothing is added. quiet: not told to the log; by: who asked for it
        ("settings": the user in the settings, "chat": said in a conversation) -- for the log."""
        t = self.check(text)
        with self.lock:
            notes = self._load()
            rep = [r for r in dict.fromkeys(replaces) if r in notes and r not in self._replaced]
            same = next((n for n in notes.values() if n["id"] not in self._replaced and same_text(n["text"]) == same_text(t)), None)
            if same is not None:
                return dict(same, known=True)
            now = _now()
            n = _valid({"id": "n" + secrets.token_hex(5), "text": t, "created": now, "changed": now, "pinned": bool(pinned), "kind": kind, "replaces": rep,
                        "names": list(names), "source": {"how": how if how in HOWS else "manual", "chat": chat, "pasted": bool(pasted)}})
            assert n is not None
            while n["id"] in notes:  # pragma: no cover - 40 random bits
                n["id"] = "n" + secrets.token_hex(5)
            seg = self._free_segment()
            notes[n["id"]] = n
            self._put(n["id"], seg)
            try:
                self._write(seg)
            except Exception:
                notes.pop(n["id"], None)
                self._take(n["id"])
                raise
            self._relink()
            if how != "chat":
                self.epoch += 1
            old = [notes[r]["text"] for r in rep]
            out = dict(n)
        if not quiet:
            self._tell("replace" if rep else "remember", out, old=old, old_ids=rep, by=by)
        return out

    def _change(self, nid: str, fn: Callable[[dict], None]) -> dict:
        with self.lock:
            notes = self._load()
            n = notes.get(str(nid))
            if n is None:
                raise NoteError(tr("s_ki_g_weg"))
            before = json.dumps(n, sort_keys=True)
            fn(n)
            if json.dumps(n, sort_keys=True) != before:
                try:
                    self._write(self._seg[n["id"]])
                except Exception:
                    notes[n["id"]] = json.loads(before)
                    raise
                self.epoch += 1
            return dict(n)

    def edit(self, nid: str, text: Any, by: str = "") -> dict:
        t = self.check(text)
        old = (self.get(nid) or {}).get("text", "")

        def fn(n: dict) -> None:
            if n["text"] != t:
                n["text"], n["changed"] = t, _now()
                n.pop("names", None)                     # the names in it: found anew
        n = self._change(nid, fn)
        if old != n["text"]:
            with self.lock:                              # its embedding was of the old text: made anew (never used again either way: made of another text)
                try:
                    self._drop_vector(n["id"], self._seg.get(n["id"]))
                except Exception as e:
                    log.warning("Memory: a file of embeddings not written (%s)", type(e).__name__)
        if old != n["text"]:
            self._tell("edit", n, old=[old], by=by)
        return n

    def pin(self, nid: str, on: bool) -> dict:
        """Pinned: always in the profile (while it fits)."""
        def fn(n: dict) -> None:
            if on:
                n["pinned"] = True
            else:
                n.pop("pinned", None)
        return self._change(nid, fn)

    def delete(self, nid: str, quiet: bool = False, by: str = "") -> dict:
        """Forgets a note: gone from its file at once. Returns it (the caller may keep it in memory for a while, to bring it
        back with restore). A note it had replaced counts again."""
        with self.lock:
            notes = self._load()
            n = notes.get(str(nid))
            if n is None:
                raise NoteError(tr("s_ki_g_weg"))
            if n["id"] in self._vec:                     # its embedding first: a file that cannot be written leaves the note as it is
                vec = self._vec.pop(n["id"])
                try:
                    self._write_vectors(self._seg[n["id"]])
                except Exception:
                    self._vec[n["id"]] = vec
                    raise
            where = list(notes).index(n["id"])
            notes.pop(n["id"])
            seg = self._seg[n["id"]]
            at = self._by_seg[seg].index(n["id"])
            self._take(n["id"])
            try:
                self._write(seg)
            except Exception:                            # back where it was
                items = list(notes.items())
                items.insert(where, (n["id"], n))
                notes.clear()
                notes.update(items)
                self._seg[n["id"]] = seg
                self._by_seg.setdefault(seg, []).insert(at, n["id"])
                raise
            if self._used.pop(n["id"], None) is not None:          # when it helped an answer goes too
                try:
                    self.store.save(USED_FILE, {"v": FORMAT, "used": self._used})
                except Exception as e:
                    log.warning("Memory: used notes not written (%s)", type(e).__name__)
            self._relink()
            self.epoch += 1
        if not quiet:
            self._tell("forget", n, by=by)
        return dict(n)

    def restore(self, note: dict, quiet: bool = False, by: str = "") -> dict:
        """Brings a note back that was just forgotten (as it was, with its id and date)."""
        n = _valid(note)
        if n is None:
            raise NoteError(tr("s_ki_g_weg"))
        with self.lock:
            notes = self._load()
            new = n["id"] not in notes
            if new:
                seg = self._free_segment()
                notes[n["id"]] = n
                self._put(n["id"], seg)
                try:
                    self._write(seg)
                except Exception:
                    notes.pop(n["id"], None)
                    self._take(n["id"])
                    raise
                self._relink()
                self.epoch += 1
            out = dict(notes[n["id"]])
        if new and not quiet:
            self._tell("restore", out, by=by)
        return out

    def forget_all(self, quiet: bool = False, by: str = "") -> int:
        """Everything remembered is deleted -- every file of notes, also one that cannot be read."""
        with self.lock:
            count = len(self._load())
            folder = self.store.data_dir
            try:
                names = os.listdir(folder)
            except OSError:
                names = []
            for name in names:
                if _SEG_NAME.fullmatch(name) or re.fullmatch(r"memory-(?:notes-\d{4,6}|vectors-\d{4,6}|used)\.json(?:\.enc)?(?:\.tmp|\.renew)?", name):
                    try:
                        os.remove(os.path.join(folder, name))
                    except OSError as e:
                        log.warning("Memory: a file of notes not removed (%s)", e)
            self._notes, self._seg, self._by_seg, self._broken, self._replaced, self._used, self._vec = {}, {}, {}, set(), {}, {}, {}
            self._rev += 1
            self.epoch += 1
        if not quiet:
            self._tell("forget_all", {}, count=count, by=by)
        log.info("Memory: everything forgotten (%d note(s))", count)
        return count

    # -- backup --------------------------------------------------------------------------------------------------------------
    def export(self) -> dict:
        """Every note, for the backup (the backup itself is encrypted with the user's backup password)."""
        with self.lock:
            return {"v": FORMAT, "notes": [dict(n) for n in self._load().values()]}

    def merge(self, data: Any, quiet: bool = False) -> int:
        """Notes of a backup back into the memory: those not there (by their id, or with the same text) are added, nothing
        there is changed or removed. A backup is a file from outside, so what it brings says so (how "backup"), and a note of
        it can replace only another note of the same backup -- never one that was there. Told to the log (how many). Returns
        how many were added; a file that cannot be written ends it there (what was written stays, the rest is not there)."""
        if not isinstance(data, dict) or not isinstance(data.get("notes"), list) or not isinstance(data.get("v"), int) or data["v"] > FORMAT:
            return 0
        added, failed = 0, None
        with self.lock:
            notes = self._load()
            have = {same_text(n["text"]) for n in notes.values()}
            fresh: List[dict] = []
            ids: Set[str] = set()
            for raw in data["notes"][:200000]:
                n = _valid(raw)
                if n is None or n["id"] in notes or n["id"] in ids or same_text(n["text"]) in have or secret_problem(n["text"]):
                    continue
                n["source"]["how"] = "backup"
                have.add(same_text(n["text"]))
                ids.add(n["id"])
                fresh.append(n)
            seg = self._free_segment()
            room = SEGMENT - len(self._by_seg.get(seg) or [])
            parts: List[Tuple[int, List[dict]]] = []
            for n in fresh:
                n["replaces"] = [r for r in n.get("replaces") or [] if r in ids]
                if not n["replaces"]:
                    n.pop("replaces")
                if room <= 0:
                    seg, room = seg + 1, SEGMENT
                if not parts or parts[-1][0] != seg:
                    parts.append((seg, []))
                parts[-1][1].append(n)
                room -= 1
            for seg, part in parts:                      # file by file: one that fails ends it, nothing of it stays in memory
                for n in part:
                    notes[n["id"]] = n
                    self._put(n["id"], seg)
                try:
                    self._write(seg)
                except Exception as e:
                    for n in part:
                        notes.pop(n["id"], None)
                        self._take(n["id"])
                    failed = e
                    break
                added += len(part)
            if added:
                self._relink()
                self.epoch += 1
        if added:
            log.info("Memory: %d note(s) restored from a backup", added)
            if not quiet:
                self._tell("backup", {}, count=added, by="backup")
        if failed is not None:
            raise failed
        return added

    # -- nothing of it into an internet search -------------------------------------------------------------------------------
    def own_words(self, common: Set[str]) -> Tuple[Set[str], Set[str]]:
        """(words, phrases) of the notes that must not go out in an internet search: the names Kontor can tell in them.
        A name is what the note names as one (names); the capitalised words after a form of address (Frau Dr. Ottilie von
        Nebelhorn) or after "heißt", "namens", "called"; a word with a capital inside (a brand) or all in capitals -- the
        last two unless Kontor's own texts use the word (common: no name). Free text has no sure sign of a name, and
        blocking every noun of every note would end all searching: this is the second line -- the first is the card that
        shows every search before it goes out."""
        words: Set[str] = set()
        phrases: Set[str] = set()
        short = {"dr", "prof", "mr", "mrs", "ms", "dipl", "ing", "med", "jur", "rer", "nat"}      # written with a full stop
        address = {"herr", "herrn", "frau", "familie"} | short
        naming = {"heisst", "heissen", "namens", "called", "named"}
        particle = {"von", "van", "de", "der", "den", "zu", "zur", "vom", "la", "le", "di", "del"}

        def telling(tok: str, known: bool) -> str:
            f = _fold(tok).replace(" ", "")
            return f if len(f) >= 3 and f.isalpha() and f not in LEGAL and f not in address and (known or (len(f) >= 4 and f not in GENERIC and f not in common)) else ""

        def take(toks: List[str], known: bool) -> None:
            got = [g for g in (telling(t, known) for t in toks) if g]
            words.update(got)
            if len(got) >= 2:
                phrases.add("".join(got))
        with self.lock:
            notes = list(self._load().values())
        for n in notes:
            for name in n.get("names") or []:
                take(re.findall(r"[^\W\d_]+", name), False)
            found = list(re.finditer(r"[^\W\d_]+", n["text"]))
            toks = [m.group(0) for m in found]
            # two words belong together when only a space, a hyphen or the full stop of an abbreviation (Dr. med.) lies between them
            joined = lambda k: k > 0 and re.fullmatch(r"\s+|-|\.\s*" if _fold(toks[k - 1]) in short else r"\s+|-", n["text"][found[k - 1].end():found[k].start()]) is not None
            i = 0
            while i < len(toks):
                tok, f = toks[i], _fold(toks[i])
                if f in address or f in naming:          # what follows is a name: its capitalised words, particles between them
                    j, run = i + 1, []
                    while j < len(toks) and len(run) < 4 and joined(j) and (_fold(toks[j]) in address or _fold(toks[j]) in particle or toks[j][:1].isupper()):
                        if _fold(toks[j]) not in address and _fold(toks[j]) not in particle:
                            run.append(toks[j])
                        elif _fold(toks[j]) in address and run:      # the next person (Herr Klein, Frau Lange)
                            break
                        j += 1
                    take(run, True)
                    i = j if run else i + 1
                    continue
                if re.search(r"[a-zäöüß][A-ZÄÖÜ]", tok) or (tok.isupper() and len(tok) >= 4):
                    take([tok], False)
                i += 1
        return words, phrases


class Talks:
    """The search index of the saved conversations: for each, its questions and answers as the search needs them (cut, see
    TALK_Q/TALK_A) -- from a conversation with text from the internet or a receipt (or a file given) in it only the user's
    questions (what came from outside never comes back through the search). Encrypted in Kontor's data folder
    (memory-chats-0001.json, ...: a few conversations per file, so that an answer writes one small file; a file that cannot
    be read goes, its conversations are put in again). A conversation deleted leaves it; a turn a forgotten note was made
    from, rested on or says again is hidden for good (by a key of its text, never the text itself), so that forgetting holds
    when the conversation is put in again. With the model for finding by meaning, each turn's embedding is kept with it.
    Never in the backup (as the conversations themselves); a reset deletes it with them."""

    def __init__(self, store):
        self.store = store
        self.lock = threading.RLock()
        self._docs: Optional[Dict[str, dict]] = None        # id of a conversation -> {"day", "items": [...], "hidden": [...]}
        self._seg: Dict[str, int] = {}
        self._rev = 0
        self._ix: Optional[Tuple[int, _Index]] = None
        self._terms: Dict[str, Tuple[str, Set[str]]] = {}    # cid#key -> (its text, its words): the index is built anew quickly
        self._vecs: Dict[str, Tuple[str, array, float]] = {}  # cid#key -> (the embedding as kept, unpacked, its length)

    # -- files ---------------------------------------------------------------------------------------------------------------
    def _names(self) -> List[int]:
        try:
            names = os.listdir(self.store.data_dir)
        except OSError:
            return []
        return sorted({int(m.group(1)) for m in map(_TALK_NAME.fullmatch, names) if m and m.group(0).endswith(".enc") == bool(self.store.encrypted)})

    def _load(self) -> Dict[str, dict]:
        if self._docs is not None:
            return self._docs
        if getattr(self.store, "is_open", True) is False:
            raise StoreLocked("locked")
        docs: Dict[str, dict] = {}
        self._seg = {}
        for seg in self._names():
            try:
                doc = self.store.load(TALKS_FILE % seg, {})
                for cid, d in (doc.get("chats") or {}).items():
                    if _CID.fullmatch(str(cid)) and isinstance(d, dict) and isinstance(d.get("items"), list) and cid not in docs:
                        d = {"day": str(d.get("day") or "")[:10], "hidden": [str(k) for k in d.get("hidden") or [] if isinstance(k, str)][-1000:],
                             "items": [it for it in d["items"] if isinstance(it, dict) and isinstance(it.get("k"), str) and isinstance(it.get("q"), str)]}
                        docs[cid] = d
                        self._seg[cid] = seg
            except StoreLocked:
                raise
            except Exception as e:                       # made of the saved conversations: a file that cannot be read goes, they come in again
                log.warning("Memory: a file of the search in conversations is not readable (%s) -- made anew", type(e).__name__)
                try:
                    self.store.delete(TALKS_FILE % seg)
                except OSError:
                    pass
        self._docs = docs
        self._rev += 1
        return docs

    def _write(self, seg: int) -> None:
        self._rev += 1
        mine = {cid: d for cid, d in (self._docs or {}).items() if self._seg.get(cid) == seg}
        if not mine:
            self.store.delete(TALKS_FILE % seg)
        else:
            self.store.save(TALKS_FILE % seg, {"v": FORMAT, "chats": mine})

    def _writes(self, segs: Iterable[int]) -> None:
        """Files written; one that fails: what is in memory is read anew from the files (so that it is what they say), and the
        failure goes on to the caller."""
        try:
            for seg in sorted(set(segs)):
                self._write(seg)
        except Exception:
            self._docs, self._ix = None, None
            raise

    def _place(self, cid: str) -> int:
        if cid in self._seg:
            return self._seg[cid]
        count = Counter(self._seg.values())
        seg = next((s for s in sorted(count) if count[s] < TALKS_PER_FILE), max(list(count) + self._names() + [0]) + 1)
        self._seg[cid] = seg
        return seg

    # -- what goes in --------------------------------------------------------------------------------------------------------
    @staticmethod
    def key(question: str, answer: str) -> str:
        """A turn by its words (where it stands in its conversation changes when old turns go)."""
        return hashlib.sha256((question + "\0" + answer[:200]).encode("utf-8")).hexdigest()[:12]

    @staticmethod
    def pairs(turns: Iterable[Any]) -> List[Tuple[str, str, List[str], bool]]:
        """(question, answer, ids of the notes made from it, forgotten in it or that it rested on, whether a file was given
        with it) of each turn of a saved conversation."""
        out = []
        last: Optional[dict] = None
        for m in turns:
            if not isinstance(m, dict):
                continue
            if m.get("role") == "user":
                last = m
            elif m.get("role") == "assistant" and last is not None:
                parts = [p for p in m.get("parts") or [] if isinstance(p, dict)]
                answer = "\n\n".join(str(p.get("text") or "") for p in parts if p.get("k") == "text").strip()
                notes = [str(p.get("id") or "") for p in parts if p.get("k") == "memory"] + \
                        [str(x.get("id") or "") for p in parts if p.get("k") == "basis" for x in p.get("notes") or [] if isinstance(x, dict)]
                out.append((str(last.get("text") or ""), answer, [n for n in notes if _NOTE_ID.fullmatch(n)], bool(last.get("files"))))
                last = None
        return out

    def put(self, cid: str, day: str, turns: Iterable[Any], foreign: bool, gone: Optional[Callable[[str], bool]] = None) -> None:
        """A saved conversation as it is now (after each answer). foreign: text from the internet or a receipt came into it --
        only the user's questions are kept (also of the turns before; a file given with a question counts the same, also in
        conversations saved before Kontor said so). gone(id): whether a note is forgotten -- a turn a forgotten note was made
        from, forgotten in or rested on is hidden for good. The same turn twice: once. An embedding is kept for a turn that
        stays the same."""
        if not _CID.fullmatch(cid or ""):
            return
        with self.lock:
            docs = self._load()
            old = docs.get(cid) or {}
            hidden = list(old.get("hidden") or [])
            had = {it["k"]: it for it in old.get("items") or []}
            pairs = self.pairs(turns)
            foreign = foreign or any(f for _, _, _, f in pairs)
            items, seen = [], set()
            for q, a, notes, _ in pairs:
                k = self.key(q, a)
                if gone is not None and any(gone(n) for n in notes) and k not in hidden:
                    hidden.append(k)
                if k in hidden or k in seen or not q.strip():
                    continue
                seen.add(k)
                it = {"k": k, "q": clean(q)[:TALK_Q], "a": "" if foreign else clean(a)[:TALK_A]}
                if notes:
                    it["n"] = list(dict.fromkeys(notes))[:20]
                prev = had.get(k)
                if prev and prev.get("v") and prev.get("q") == it["q"] and prev.get("a") == it["a"]:
                    it["v"], it["m"] = prev["v"], prev.get("m", "")
                items.append(it)
            docs[cid] = {"day": str(day or "")[:10], "items": items, "hidden": hidden[-1000:]}
            self._writes([self._place(cid)])

    def drop(self, cids: Iterable[str] = (), everything: bool = False) -> None:
        """Conversations deleted: gone from the search (everything: every file of it, also one that cannot be read)."""
        with self.lock:
            if everything:
                try:
                    names = os.listdir(self.store.data_dir)
                except OSError:
                    names = []
                for name in names:
                    if re.fullmatch(r"memory-chats-\d{4,6}\.json(?:\.enc)?(?:\.tmp|\.renew)?", name):
                        try:
                            os.remove(os.path.join(self.store.data_dir, name))
                        except OSError as e:
                            log.warning("Memory: a file of the search in conversations not removed (%s)", e)
                self._docs, self._seg, self._ix = None, {}, None
                self._terms, self._vecs = {}, {}
                self._rev += 1
                return
            docs = self._load()
            segs = {self._seg.pop(c) for c in list(cids) if docs.pop(c, None) is not None and c in self._seg}
            self._writes(segs)

    def forget(self, note_ids: Iterable[str] = (), texts: Iterable[str] = (), every_note: bool = False) -> List[str]:
        """Notes were forgotten (their ids and texts): hidden for good -- the turns they were made from, forgotten in or rested
        on, and every turn that says one of them again (all of its words, three quarters of them in a note of more than two;
        a note of one word only where it was made). every_note: every note was forgotten -- every turn a note was made from or
        rested on. Returns the turns hidden (cid#key)."""
        with self.lock:
            docs = self._load()
            ids = set(note_ids)
            sets = [w for w in (set(terms(t)) for t in texts) if len(w) >= 2]
            segs, gone = set(), []
            for cid, d in docs.items():
                keep = []
                for it in d["items"]:
                    made = bool(it.get("n")) and (every_note or bool(ids & set(it["n"])))
                    words = self._words(cid, it)
                    says = any(len(w & words) * 4 >= len(w) * 3 and (len(w) > 2 or w <= words) for w in sets)
                    if made or says:
                        d["hidden"] = (d["hidden"] + [it["k"]])[-1000:]
                        gone.append(cid + "#" + it["k"])
                    else:
                        keep.append(it)
                if len(keep) != len(d["items"]):
                    d["items"] = keep
                    segs.add(self._seg[cid])
            self._writes(segs)
            return gone

    def known(self) -> Dict[str, str]:
        """Conversations in the search: id -> the day of their last turn."""
        with self.lock:
            return {cid: d.get("day", "") for cid, d in self._load().items()}

    # -- search --------------------------------------------------------------------------------------------------------------
    def _words(self, cid: str, it: dict) -> Set[str]:
        text = it["q"] + " " + it.get("a", "")
        hit = self._terms.get(cid + "#" + it["k"])
        if hit is None or hit[0] != text:
            hit = (text, set(terms(text)))
            self._terms[cid + "#" + it["k"]] = hit
        return hit[1]

    def _index(self) -> _Index:
        with self.lock:
            docs = self._load()
            if self._ix is None or self._ix[0] != self._rev:
                self._ix = (self._rev, _Index({"id": cid + "#" + it["k"], "terms": self._words(cid, it)} for cid, d in docs.items() for it in d["items"]))
            return self._ix[1]

    def _items(self) -> Dict[str, Tuple[str, dict, dict]]:
        return {cid + "#" + it["k"]: (cid, d, it) for cid, d in (self._docs or {}).items() for it in d["items"]}

    def _vector(self, i: str, it: dict) -> Optional[Tuple[array, float]]:
        hit = self._vecs.get(i)
        if hit is None or hit[0] != it.get("v"):
            try:
                a = array("b", base64.b64decode(it["v"]))
            except (ValueError, TypeError, KeyError):
                return None
            hit = (it["v"], a, _norm(a))
            self._vecs[i] = hit
        return hit[1], hit[2]

    def search(self, query: Any, limit: int = 4, exclude: Iterable[str] = (), meaning: Optional[Tuple[str, array]] = None) -> List[dict]:
        """Turns of saved conversations that fit a query (ranked as Memory.search ranks notes), not of the conversations in
        exclude: [{"id": cid#key, "chat", "day", "question", "answer", "score"}] -- the best first, the later among equals."""
        with self.lock:
            ix = self._index()
            items = self._items()
            out_of = set(exclude)
            skip = {i for i, (cid, _, _) in items.items() if cid in out_of}
            like = None
            if meaning is not None:
                q, qn, like = meaning[1], _norm(meaning[1]), {}
                for i, (_, _, it) in items.items():
                    if it.get("v") and it.get("m") == meaning[0] and i not in skip:
                        v = self._vector(i, it)
                        if v is not None and len(v[0]) == len(q):
                            like[i] = sum(map(operator.mul, q, v[0])) / (qn * v[1])
            scored = _rank(ix, query, "", skip, items, like)
            scored.sort(key=lambda x: (round(x[0], 6), items[x[1]][1].get("day", "")), reverse=True)
            return [{"id": i, "chat": items[i][0], "day": items[i][1].get("day", ""), "question": items[i][2]["q"],
                     "answer": items[i][2].get("a", ""), "score": round(sc, 3)} for sc, i in scored[:max(1, int(limit))]]

    # -- by meaning --------------------------------------------------------------------------------------------------------------
    def vectors_missing(self, model: str, limit: int) -> List[Tuple[str, str]]:
        """(cid#key, text) of turns without an embedding of this model -- the latest conversations first."""
        with self.lock:
            docs = self._load()
            out = []
            for cid, d in sorted(docs.items(), key=lambda x: x[1].get("day", ""), reverse=True):
                for it in d["items"]:
                    if not it.get("v") or it.get("m") != model:
                        out.append((cid + "#" + it["k"], it["q"] + "\n" + it.get("a", "")))
                        if len(out) >= limit:
                            return out
            return out

    def set_vectors(self, model: str, got: Dict[str, Tuple[str, Iterable[float]]]) -> int:
        """Embeddings made: cid#key -> (the text they were made of, the numbers); kept only for a turn still there as it was."""
        with self.lock:
            items = self._items()
            segs, kept = set(), 0
            for i, (text, vec) in got.items():
                hit = items.get(i)
                if hit is None or hit[2]["q"] + "\n" + hit[2].get("a", "") != text:
                    continue
                hit[2]["v"], hit[2]["m"] = base64.b64encode(pack(vec).tobytes()).decode("ascii"), model
                segs.add(self._seg[hit[0]])
                kept += 1
            self._writes(segs)
            return kept
