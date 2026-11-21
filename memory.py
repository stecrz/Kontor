"""The assistant's memory: what the user told it to remember -- about themselves, their plans, decisions, people, preferences
and how it should answer. A second brain on this Mac, kept beside the model (the model itself never changes or grows):

  notes    short texts in the user's own words, each with its date and where it came from (a conversation, the settings, a
           backup). Encrypted in Kontor's data folder (memory-notes-0001.json, ...: at most SEGMENT notes per file, so that
           a change writes one small file however much is remembered, and a damaged file loses one file's notes, never
           all). In the backup; never in the log or a package; a reset and removing Kontor delete them.
  profile  the few notes every question is given (pinned ones first, then the latest), within a fixed budget -- so that a
           question costs the same however much is remembered. Everything else is found by searching.

Only Kontor reads and writes here. The model has no way to this file: it runs in a sandbox that cannot read Kontor's data, and
it has no tool that writes a note. What becomes a note is decided outside its answer (assistant.py).

A note that replaces another names it (replaces); the older one stays, marked as replaced, until the user deletes it -- taking
the newer one away brings it back. Forgetting deletes: the note is gone from its file at once.

Never remembered: passwords, PINs, TANs, keys, card numbers (secret_problem) -- Kontor stores no credentials.
A backup is a file from outside: what comes back from one says so (how "backup"), is told to the log, and can replace
nothing that was there.
"""
from __future__ import annotations

import json
import logging
import os
import re
import secrets
import threading
import unicodedata
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, Iterable, List, Optional, Set, Tuple

from i18n import tr
from web_search import GENERIC, LEGAL, _INVISIBLE, _fold

log = logging.getLogger("kontor.memory")

FILE = "memory-notes-%04d.json"                    # in Kontor's data folder, beside its other files (encrypted; a new data key covers every file there)
SEGMENT = 1000                                     # notes in one file at most
FORMAT = 1                                         # of a file of notes (and of the notes in a backup)
TEXT_MAX = 600                                     # characters of one note
PROFILE_TOKENS = 1500                              # the profile at most (less in a small context: profile_budget)
HOWS = ("chat", "manual", "backup")                # where a note came from: said in a conversation, typed in the settings, restored
KINDS = ("", "fact", "preference", "plan", "decision", "person", "reason", "style")       # what it is about ("": not told)
_SEG_NAME = re.compile(r"memory-notes-(\d{4,6})\.json(?:\.enc)?")
_NOTE_ID = re.compile(r"n[0-9a-f]{10}")
_MORE_INVISIBLE = re.compile("[\u180b-\u180d\u2800\U000e0100-\U000e01ef]")      # further characters nobody sees (variation selectors, a blank braille cell)


class NoteError(ValueError):
    """A note that cannot be kept (empty, too long, a credential) -- its text is for the user."""


def profile_budget(context: int) -> int:
    """Tokens the profile may take: PROFILE_TOKENS, in a small context about 4.5 % of it."""
    return max(300, min(PROFILE_TOKENS, int(context) // 22))


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
        self.epoch = 0                                     # counts changes made outside a conversation (the profile is built anew)

    # -- files ---------------------------------------------------------------------------------------------------------------
    def _file(self, seg: int) -> str:
        return FILE % seg

    def _segments(self) -> List[int]:
        try:
            names = os.listdir(self.store.data_dir)
        except OSError:
            return []
        out = set()
        for name in names:
            m = _SEG_NAME.fullmatch(name)
            if m and name.endswith(".enc") == bool(self.store.encrypted):
                out.add(int(m.group(1)))
        return sorted(out)

    def _load(self) -> Dict[str, dict]:
        if self._notes is not None:
            return self._notes
        notes: Dict[str, dict] = {}
        self._seg, self._by_seg, self._broken = {}, {}, set()
        for seg in self._segments():
            try:
                raw = self.store.read_bytes(self._file(seg))
                doc = json.loads(raw.decode("utf-8")) if raw is not None else {}
                if not isinstance(doc, dict) or not isinstance(doc.get("notes"), list) or not isinstance(doc.get("v"), int) or doc["v"] > FORMAT:
                    raise ValueError("format")
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
        self._notes = notes
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
            if words:
                rows = [n for n in rows if all(w in _fold(n["text"]) for w in words)]
            pos = {nid: i for i, nid in enumerate(notes)}
            rows.sort(key=lambda n: (n["id"] not in self._replaced, bool(n.get("pinned")), n["changed"], pos[n["id"]]), reverse=True)
            offset, limit = max(0, int(offset)), max(1, min(200, int(limit)))
            return dict(self.stats(), total=len(rows), offset=offset, items=[self.view(n) for n in rows[offset:offset + limit]])

    def profile(self, budget_tokens: int = PROFILE_TOKENS) -> List[dict]:
        """The notes every question is given: pinned ones first (the latest first), then the latest others -- as many as fit
        into the budget (a token counted as three characters, as everywhere in the assistant: rather too few than too many).
        A note that does not fit any more is left out and the next shorter one tried, so that the room is used."""
        room = max(0, int(budget_tokens)) * 3
        out: List[dict] = []
        act = self.active()
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
            same = next((n for n in notes.values() if n["id"] not in self._replaced and n["id"] not in rep and same_text(n["text"]) == same_text(t)), None)
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
                if _SEG_NAME.fullmatch(name) or re.fullmatch(r"memory-notes-\d{4,6}\.json(?:\.enc)?\.(?:tmp|renew)", name):
                    try:
                        os.remove(os.path.join(folder, name))
                    except OSError as e:
                        log.warning("Memory: a file of notes not removed (%s)", e)
            self._notes, self._seg, self._by_seg, self._broken, self._replaced = {}, {}, {}, set(), {}
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
