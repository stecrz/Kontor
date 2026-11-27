"""The assistant's memory: what is worth remembering about the user -- themselves, their plans, decisions, people, preferences
and how it should answer. A second brain on this Mac, kept beside the model (the model itself never changes or grows):

  notes    short texts, condensed from what the user said or from what the assistant worked out with them (marked so),
           each with its date and where it came from (a conversation, the settings, a backup). Encrypted in Kontor's data folder (memory-notes-0001.json, ...: at most SEGMENT notes per file, so that
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
A backup is a file from outside: what comes back from one says so (how "backup"), is told to the log, is never pinned and can
replace nothing that was there.
Carried elsewhere: export_file writes everything remembered as one text in an open format ("kontor-memory": Markdown to read,
the same as JSON for programs); import_file reads such a file -- or a plain list, a note per line -- checked as a whole first,
all of it or nothing, every note checked like one typed by hand, marked (how "import"), never pinned, replacing nothing there.
Forgotten holds: what was forgotten is kept in a list of its own (Forgotten: ids of notes and keys of turns of saved
conversations, never a text), written before the note goes -- the search in saved conversations (Talks) follows it whatever
happens to its own files.
"""
from __future__ import annotations

import base64
import hashlib
import io
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
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, Iterable, List, Optional, Set, Tuple

import i18n
from i18n import tr, trn
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
GONE_FILE = "memory-forgotten.json"                # what was forgotten, so that it stays forgotten there (Forgotten; encrypted): ids of notes, keys of turns -- never a text
GONE_MAX = 50000                                   # of each at most (the oldest go first)
TALKS_PER_FILE = 10
TALK_Q, TALK_A = 800, 900                          # characters of a question, of an answer kept for searching
LIB_FILE = "memory-%s-%04d.json"                   # embeddings of other texts (Library: kind "help", "tx"), a few files each
LIB_BUCKETS = 8
HOWS = ("chat", "manual", "backup", "import")      # where a note came from: said in a conversation, typed in the settings, restored, read from a file
EXPORT_FORMAT, EXPORT_VERSION = "kontor-memory", 1  # the open format the memory is exported in (export_file) and read from again (import_file)
IMPORT_MAX = 100000                                # notes of one file at most
REPLACED_MAX = 20                                  # earlier wordings told with a note at most (as many as a note can replace)
PROBLEMS_SHOWN, PREVIEW_NOTES = 10, 200            # of what does not fit in a file / of the notes it would bring: as many are told to the page
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
# Words that name a secret, of three kinds (the first part of a hyphenated word may stand before the first two: Depot-Passwort):
#   p  a password by any name: its value can be anything -- a number, a word with digits or a capital inside, what follows "ist" or ":"
#   n  a number that is a secret (PIN, TAN, a card's check number, a door code): its value is digits or a word with digits
#   w  Code, Schlüssel, Key by themselves -- everyday words: only what stands right behind them, or behind "ist" and ":", counts
_SECRET_P = (r"[%s]*(?:passwort(?:e|es|s)?|passw(?:ö|oe)rtern?|passwords?|passphrases?|kennwort(?:e|es|s)?|kennw(?:ö|oe)rtern?)" % _L
             + r"|pw|pwd|passcodes?|secrets?|tokens?|log-?ins?|zugangscodes?|(?:zugangs|anmelde|log-?in)[\s-]?daten|credentials"
             r"|(?:api|private|secret|recovery|security|licen[cs]e|product|activation|master|wi-?fi|wlan)[\s_-]?keys?|(?:recovery|seed)[\s-]?phrases?"
             r"|(?:api[\s_-]?|wiederherstellungs|sicherheits|lizenz|produkt|aktivierungs|zugangs|geheim|privat|master|haupt|wlan-?|netzwerk|entsperr|krypto|verschl(?:ü|ue)sselungs)"
             r"schl(?:ü|ue)ssel[ns]?")
_SECRET_N = (r"(?:(?:karten|handy|sim|konto|online|banking|ec|giro|app|super|telefon|depot|m|i|sms|push|photo|chip|smart|flicker|qr)[\s-]?)?(?:pins?|pin[\s-]?codes?|puks?|tans?)"
             r"|cvv2?|cvc2?|geheimzahl(?:en)?|pr(?:ü|ue)fziffern?|kartenpr(?:ü|ue)fnummern?|(?:kredit|bank|giro|ec-?)?kartennummern?|card[\s-]?numbers?"
             r"|(?:sicherheits|entsperr|freischalt|aktivierungs|best(?:ä|ae)tigungs|t(?:ü|ue)r|tresor|alarm|geheim|master|backup|recovery|log-?in|einmal|sms-?|security|access|unlock|door)"
             r"[\s-]?codes?")
_SECRET = re.compile(r"(?:%s(?:[%s]+-)*(?:(?P<p>%s)|(?P<n>%s))|(?<![%s-])(?P<w>codes?|schl(?:ü|ue)ssel[ns]?|keys?))%s"
                     % (_NOT_IN_A_WORD[0], _L, _SECRET_P, _SECRET_N, _L, _NOT_IN_A_WORD[1]), re.I)
_QUOTE = "\"'„“‚‘«»"
_FILLER = (r"jetzt|nun|neu|neuerdings|ab\s+sofort|aktuell|derzeit|momentan|k(?:ü|ue)nftig|wieder|immer|noch|weiterhin|seit\s+heute|now|currently|still|again"
           r"|die|der|das|the|nr\.?|nummer|number")                    # words between "ist" and the value that say nothing (ist jetzt ..., lautet wieder ...)
_LINK = re.compile(r"(?:[:=]|(?<![%s])(?:lautet|ist|is|war|was|hei(?:ß|ss)t)(?![%s]))(?:\s*(?<![%s])(?:%s)(?![%s])[,:]?)*\s*[%s]?" % (_L, _L, _L, _FILLER, _L, _QUOTE), re.I)
_LINKED = re.compile(r"(?:[:=]|(?<![%s])(?:lautet|ist|is|war|was|hei(?:ß|ss)t))$" % _L, re.I)
_FILLED = re.compile(r"(?<![%s])(?:%s)$" % (_L, _FILLER), re.I)
_TOKEN = re.compile(r"[^\s%s(),;]+" % _QUOTE)
_COUNT = re.compile(r"\d{1,2}(?:-?[%s]+)+|[qQ][1-4](?:[-/]?(?:19|20)?\d\d)?|(?:19|20)\d\der" % _L)       # 4-stellig, 2-Faktor, 30-Tage-Frist, 2x, Q3-2026, 2025er: no value
_NO_VALUE = frozenset("wpa2 wpa3 fido2 u2f oauth2 sha256 aes256 mp3 mp4 3ds a4".split())
# written with a capital inside and no password for all that
_BRANDS = frozenset("paypal iphone ipad imac icloud macbook macos moneymoney filevault youtube whatsapp linkedin github onedrive keepass keepassxc lastpass touchid faceid "
                    "hypovereinsbank diba phototan pushtan chiptan mtan smstan itan datev elster mastercard girocard".split())
_UNIT = re.compile(r"\s*(?:%|€|eur\b|euro\b|uhr\b|stellig|stellen\b|ziffern\b|zeichen\b|digits?\b|characters?\b|jahre?n?\b|monate?n?\b|tage?n?\b|wochen\b|stunden\b|minuten\b|mal\b|x\b"
                   r"|km\b|kg\b|m²|qm\b|years?\b|months?\b|weeks?\b|days?\b|hours?\b|times\b|k\b|mio\b|tsd\b|versuche?n?\b|attempts?\b)", re.I)
_SERVICE = re.compile(r"(?<![%s])(?:f(?:ü|ue)r|bei|beim|von|vom|for|at|of)(?:\s+(?:der|die|das|dem|den|des|the|mein\w*|unser\w*|my|our))?\s+[%s]?$" % (_L, _QUOTE), re.I)
# a password's value after "ist", "lautet", ":" without a digit: a word by itself, a capitalised one or a long one -- not a word
# that tells how it is (Das Passwort ist sicher verwahrt, Passwort: regelmäßig ändern)
_SOFT = frozenset("sicher unsicher lang kurz neu alt gleich anders falsch richtig korrekt stark schwach gut schlecht weg bekannt unbekannt geheim privat "
                  "wichtig egal schwer leicht einfach kompliziert sicherer besser gültig ungültig ok okay sehr zu nirgends überall hier dort "
                  "safe secure strong weak long short new old same different fine good bad unknown known secret private hidden".split())
_ADJ = re.compile(r"(?:ab|an|auf|aus|be|ein|mit|nach|um|vor|weg|zu|zurück|hinter|ver)?ge[a-zäöüß]{2,}(?:t|en)|[a-zäöüß]{3,}(?:lich|ig|bar|sam|los|haft|isch|iert|ed|ly)")
_ALONE = re.compile(r"\s*(?:$|[,.;!?)%s]|(?:und|and|oder|or)(?![%s]))" % (_QUOTE, _L), re.I)
_SAID_AS = re.compile(r"\s*(?:[:=]|lautet|hei(?:ß|ss)t)", re.I)            # links that name the value (Passwort: ..., lautet ..., heißt ...)
_NUMBER_WORDS = re.compile(r"(?<![%s])(?:(?:null|eins?|zwei|drei|vier|f(?:ü|ue)nf|sechs|sieben|acht|neun|zero|one|two|three|four|five|six|seven|eight|nine)"
                           r"(?:[\s,-]+|$)){3,}" % _L, re.I)                  # PIN: vier sieben eins eins
_SENTENCE = re.compile(r"(?<=[a-zäöüß)\]%s]{2}[.!?])\s+(?=[%s(]?[A-ZÄÖÜ])|\n+" % (_QUOTE, _QUOTE))       # (not after "3." or "Nr.": rather a sentence too long than a value cut off from its word)
_CODE_PART = re.compile(r"[A-Za-z0-9_+=]{20,}")      # a long random code: a part of twenty and more characters with small and capital letters and digits
_DIGITS = re.compile(r"(?<!\w)\d(?:[ .\-]?\d)*(?!\w)")                # a run of digits, also in groups
_CARD_WORD = re.compile(r"(?<![%s])(?:[%s]*karten?|cards?|visa|master(?:card)?|amex|american\s+express|maestro|girocard|giro|discover|diners|jcb|unionpay|debit|kredit\w*)(?![%s])" % (_L, _L, _L), re.I)
# what says that a long number is no card (right before it): Vertragsnummer 1234 ..., Tel. ..., IMEI ...
_NO_CARD = re.compile(r"(?<![%s])(?:vertrag\w*|kunden\w*|z(?:ä|ae)hler\w*|steuer\w*|rechnung\w*|bestell\w*|auftrag\w*|police\w*|versicherung\w*|mandant\w*|personal\w*|serien\w*"
                      r"|ger(?:ä|ae)te\w*|akten\w*|vorgang\w*|buchung\w*|beleg\w*|sendung\w*|paket\w*|tracking\w*|telefon\w*|tel|mobil\w*|handy\w*|fax|imei|isbn|ean|gtin|konto\w*|depot\w*"
                      r"|mitglied\w*|ausweis\w*|invoice\w*|order\w*|contract\w*|customer\w*|account\w*|policy\w*|serial\w*|phone|reference\w*|referenz\w*|flurst(?:ü|ue)ck\w*|grundbuch\w*)"
                      r"(?:[\s-]*(?:nr|no|nummer|number|id))?[\s.:#]*$" % _L, re.I)


def sentences(text: Any) -> List[str]:
    """A text by its sentences -- cut only where one surely ends (a line break; ".", "!" or "?" after a word, a capital
    behind it): not after "3." or "Nr.". Rather a sentence too long than a word cut off from what belongs to it."""
    return [s for s in _SENTENCE.split(str(text or "")) if s.strip()]


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


def _card_number(text: str) -> bool:
    """A card number of any brand: twelve to nineteen digits (in one piece or in groups, with spaces or hyphens) that pass the
    check digit -- as a whole, or its card-shaped part with an expiry date or check number behind it. Not an IBAN, a phone
    number (+49 ...), a row of years, or a number the words before it name as something else (Vertragsnummer ..., unless the
    sentence speaks of a card). Visa, Mastercard and Amex as before: wherever they stand, however they are grouped."""
    for m in _DIGITS.finditer(text):
        before = text[max(0, m.start() - 40):m.start()]
        if re.search(r"[A-Z]{2}\d{2} ?$", before[-6:]):                # (the digits of an IBAN are no card)
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
        if before.rstrip().endswith("+") or (_NO_CARD.search(before) and not _CARD_WORD.search(text)):
            continue
        for part in m.group(0).split("."):               # any other brand: spaces and hyphens only (a full stop: dates, amounts)
            gs = [g for g in re.split(r"[ \-]", part) if g]
            for i in range(len(gs)):
                for j in range(i + 1, len(gs) + 1):
                    run, d = gs[i:j], "".join(gs[i:j])
                    if len(d) > 19:
                        break
                    whole = i == 0 and j == len(gs)
                    shaped = len(run) == 1 or (all(len(g) == 4 for g in run[:-1]) and len(run[-1]) <= 4) or [len(g) for g in run] in ([4, 6, 5], [4, 6, 4])
                    if len(d) >= 12 and (whole or shaped) and not all(re.fullmatch(r"(?:19|20)\d\d", g) for g in run) and _luhn(d):
                        return True
    return False


def _behind(s: str, pos: int, ends: Set[int]) -> bool:
    """Whether what stands at pos comes right behind a secret word or behind "ist", "lautet", ":" (words that say nothing skipped)."""
    head = s[:pos]
    while True:
        head = head.rstrip(" \t" + _QUOTE)
        m = _FILLED.search(head)
        if m is None:
            return len(head) in ends or _LINKED.search(head) is not None
        head = head[:m.start()]


def _secret_value(s: str, found: List[Tuple[int, int, str]]) -> bool:
    """Whether a sentence that names a secret (found: where, and of which kind) also holds its value."""
    ends = {b for _, b, _ in found}
    own = lambda a, b: any(a < y and x < b for x, y, _ in found)       # (a part of the secret word itself: CVV2, FileVault-...)
    code = lambda v: bool(v) and _COUNT.fullmatch(v) is None and v.lower() not in _NO_VALUE and any(c.isdigit() for c in v) and (any(c.isalpha() for c in v) or sum(c.isdigit() for c in v) >= 3)
    if any(k != "w" for _, _, k in found):
        for m in re.finditer(r"\d(?:[ \-]?\d)*", s):     # a number: three digits and more, also in groups -- no amount, date, length
            before, after = s[:m.start()], s[m.end():]
            if own(m.start(), m.end()) or (before[-1:] and (before[-1].isalnum() or before[-1] in ".,/§")) or re.match(r"[%s]|[.,/:]\d|-[%s]" % (_L, _L), after):
                continue
            if sum(c.isdigit() for c in m.group(0)) < 3 or _UNIT.match(after):
                continue
            if re.fullmatch(r"(?:19|20)\d\d", m.group(0)) and not _behind(s, m.start(), ends):      # a year in passing (seit 2024, 2024 geändert) -- "PIN 1987" is none
                continue
            return True
        password = any(k == "p" for _, _, k in found)
        for m in _TOKEN.finditer(s):                     # a word with letters and digits (Sommer2024), for a password also one with a capital inside (xKcdHase)
            tok = m.group(0).strip(".:!?")
            if own(m.start(), m.end()) or _SERVICE.search(s[:m.start()]) or any(p in _BRANDS for p in re.split(r"[-/]", tok.lower())):      # ("für PayPal", "bei N26": the service, not the value)
                continue
            if (any(c.isalpha() for c in tok) and code(tok)) or (password and re.search(r"[a-zäöüß][A-ZÄÖÜ]", tok)):
                return True
        if _NUMBER_WORDS.search(s):                      # digits written as words
            return True
    for a, b, kind in found:                             # what follows "ist", "lautet", ":" or "=" (within the sentence, soon after the word)
        for m in _LINK.finditer(s, b):
            if m.start() - b > 60:
                break
            got = _TOKEN.match(s, m.end())
            v = got.group(0).strip(".:!?") if got else ""
            if len(v) < 3 or _COUNT.fullmatch(v) is not None:
                continue
            if kind != "p":
                if code(v):
                    return True
                continue
            if any(c.isdigit() for c in v):
                return True
            gap = s[b:m.start()]                         # a word only close to its secret word (Passwort für die Bank ist ...; not "Passwort ändern, Termin: Montag")
            if "," in gap or len(gap.split()) > 5 or _fold(v) in STOP:
                continue
            soft = v.lower() in _SOFT or (v[:1].islower() and _ADJ.fullmatch(v.lower()) is not None)
            alone = _ALONE.match(s, got.end()) is not None if got else False
            if _SAID_AS.match(m.group(0)):               # Passwort: geheim, lautet hunter, heißt Tulpe
                if alone or (not soft and (v[:1].isupper() or len(v) >= 8)):
                    return True
            elif not soft and (v[:1].isupper() or len(v) >= 8 or alone):          # ist Tulpe, ist hunter -- not "ist sicher verwahrt"
                return True
        if kind == "w":                                  # Code 4711, Key ABCD-1234
            got = _TOKEN.match(s, len(s) - len(s[b:].lstrip(" \t" + _QUOTE)))
            if got and code(got.group(0).strip(".:!?")):
                return True
    return False


def secret_problem(text: str) -> bool:
    """Whether a text holds a credential: a long random code; a card number of any brand (also with its expiry date or check
    number behind it); or a sentence that names a secret -- a password, PIN, TAN, key, code, a card's number or check number,
    login data -- together with a value: a number of three digits and more (also in groups: 47 11), a word with digits or,
    for a password, with a capital inside, or what follows "ist", "lautet", ":" (also with "jetzt", "wieder" between). A
    sentence without a value ("Passwörter ändere ich jeden Monat") and an IBAN are none. In doubt yes -- the user is told
    and can say it without the value."""
    text = str(text or "")
    for m in _CODE_PART.finditer(text):
        v = m.group(0)
        if all(re.search(p, v) for p in (r"[a-z]", r"[A-Z]", r"\d")):
            return True
    if sum(c.isdigit() for c in text) >= 12 and _card_number(text):
        return True
    if _SECRET.search(text) is None:
        return False
    for s in sentences(text):
        found = [(m.start(), m.end(), m.lastgroup or "") for m in _SECRET.finditer(s)]
        if found and _secret_value(s, found):
            return True
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
    if out["source"]["how"] == "import" and re.fullmatch(r"[0-9a-f]{12}", str(src.get("batch") or "")):
        # which import brought it, when, and a key of its text as it came (to take that import back: only what is unchanged)
        out["source"].update(batch=src["batch"], at=_stamp(src.get("at"), created), **({"as": src["as"]} if re.fullmatch(r"[0-9a-f]{16}", str(src.get("as") or "")) else {}))
    if src.get("answer") is True and out["source"]["how"] == "chat":      # from the assistant's answer in a conversation (not the user's words)
        out["source"]["answer"] = True
    if n.get("pinned") is True:
        out["pinned"] = True
    if n.get("kind") in KINDS and n.get("kind"):
        out["kind"] = n["kind"]
    rep = [r for r in n.get("replaces") or [] if isinstance(r, str) and _NOTE_ID.fullmatch(r) and r != n["id"]] if isinstance(n.get("replaces"), list) else []
    if rep:
        out["replaces"] = rep[:20]
    names = [clean(x)[:60] for x in n.get("names") or [] if isinstance(x, str) and clean(x)] if isinstance(n.get("names"), list) else []
    if names:                                           # only names that stand in the note (whoever named them: a look of the model, a backup)
        inside = " %s " % _fold(text)
        names = [x for x in names if _fold(x) and " %s " % _fold(x) in inside]
    if names:
        out["names"] = names[:12]
    if n.get("named") is True:                          # the model has named the names in it (with the note from a conversation, or later)
        out["named"] = True
    return out


# -- carried elsewhere: one file in an open format (Memory.export_file, Memory.import_file) -----------------------------------
class TransferError(ValueError):
    """A file that cannot be read in as a memory at all (no text, damaged, something else, of a newer Kontor, too many notes)
    -- its text is for the user."""


_TIME = re.compile(r"([0-9]{4})-([0-9]{2})-([0-9]{2})(?:[T ]([0-9]{2}):([0-9]{2})(?::([0-9]{2})(?:[.,][0-9]{1,9})?)?[ ]?(?:([zZ])|([+-])([0-9]{2}):?([0-9]{2}))?)?")


def _iso(stamp: str) -> str:
    """A note's time (this Mac's clock, as kept) as other programs read it: ISO 8601 with the distance to UTC."""
    try:
        return datetime.strptime(stamp, "%Y-%m-%d %H:%M:%S").astimezone().isoformat(timespec="seconds")
    except (ValueError, OverflowError, OSError):         # (a time this Mac's clock cannot place)
        return stamp.replace(" ", "T")


def _when(v: Any, fallback: str) -> str:
    """A time read from a file, as a note keeps it: ISO 8601 (with a distance to UTC: turned to this Mac's clock; a day alone:
    its beginning) or as Kontor writes it -- anything else, and a time that cannot be (the future): the fallback."""
    m = _TIME.fullmatch(v.strip()) if isinstance(v, str) else None
    if m is None:
        return fallback
    try:
        when = datetime(*(int(x or 0) for x in m.groups()[:6]))
        if m.group(7) or m.group(8):
            off = timedelta(0) if m.group(7) else timedelta(hours=int(m.group(9)), minutes=int(m.group(10))) * (1 if m.group(8) == "+" else -1)
            when = (when - off).replace(tzinfo=timezone.utc).astimezone().replace(tzinfo=None)
        return _stamp(when.strftime("%Y-%m-%d %H:%M:%S"), fallback)
    except (ValueError, OverflowError, OSError):
        return fallback


def _day(stamp: str) -> str:
    """A note's day as the pages write it (23.11.2026; in English 23/11/2026)."""
    return ("/" if i18n.lang() == "en" else ".").join((stamp[8:10], stamp[5:7], stamp[:4]))


def _count(n: int) -> str:
    """A number as the pages write it (100.000; in English 100,000)."""
    return "{:,}".format(n) if i18n.lang() == "en" else "{:,}".format(n).replace(",", ".")


_MD_SIGN = re.compile(r"[\\`*_\[\]<~]")
_MD_ENTITY = re.compile(r"&(?=(?:#[0-9]{1,7}|#[xX][0-9a-fA-F]{1,6}|[A-Za-z][A-Za-z0-9]{1,31});)")
_MD_START = re.compile(r"-(?=[ \t-]|$)|\+(?=[ \t]|$)|#(?=[ \t#]|$)|>|[0-9]{1,9}(?=[.)](?:[ \t]|$))")
_MD_LINK = re.compile(r"(?i)(?<=[a-z0-9]):(?=//)|(?<![a-z0-9])www\.")      # where an address begins: the sign that makes it one
_MD_ESCAPED = re.compile(r"\\([!-/:-@\[-`{-~])")
_MD_KEPT = re.compile("[\ue021-\ue07e]")
_MD_MARKED = (re.compile(r"\*\*(?=\S)(.+?)(?<=\S)\*\*"), re.compile(r"(?<![\w*])\*(?=[^\s*])([^*]+?)(?<=[^\s*])\*(?![\w*])"), re.compile(r"`([^`]+)`"))


def _md(text: str) -> str:
    """A note's text for a Markdown list, so that a reader shows it letter for letter: nothing in it is taken for emphasis,
    code, a link (also an address by itself), a picture, HTML, a heading, a quote or a list of its own."""
    t = _MD_ENTITY.sub(r"\\&", _MD_SIGN.sub(lambda m: "\\" + m.group(0), text))
    t = _MD_LINK.sub(lambda m: m.group(0)[:-1] + "\\" + m.group(0)[-1], t).replace("@", "\\@")      # (an address stays text: readers link https://…, www.…, name@host by themselves)
    m = _MD_START.match(t)
    if m is None:
        return t
    return t[:m.end()] + "\\" + t[m.end():] if t[0].isdigit() else "\\" + t


def _unmarked(s: str) -> str:
    """A line of a list as a note's text: cleaned, a sign written with a backslash before it (\\*) as itself, and without the
    marks of **bold**, *emphasis* and `code` around words. Links and everything else stay as written."""
    if len(s) > 100 * TEXT_MAX:                          # (far too long for a note either way: said so, not worked through)
        return s
    t = clean(s)
    if len(t) > 2 * TEXT_MAX:
        return t
    t = _MD_ESCAPED.sub(lambda m: chr(0xE000 + ord(m.group(1))), t)        # (clean leaves no character of that range: free to stand in)
    for marked in _MD_MARKED:
        t = marked.sub(r"\1", t)
    return clean(_MD_KEPT.sub(lambda m: chr(ord(m.group(0)) - 0xE000), t))


def _blocks(text: str) -> List[str]:
    """What stands in the fenced blocks of a Markdown text that are marked as JSON (``` json ... ```); one that never ends is none."""
    out: List[str] = []
    fence, mine, buf = "", False, []
    for line in io.StringIO(text):
        s = line.strip()
        if not fence:
            m = re.fullmatch(r"(`{3,}|~{3,})[ \t]*([A-Za-z]*)[^`]*", s)
            if m:
                fence, mine, buf = m.group(1), m.group(2).lower() == "json", []
        elif s.startswith(fence) and not s.strip(fence[0]):
            if mine:
                out.append("".join(buf))
            fence = ""
        elif mine:
            buf.append(line)
    return out


def _wordings(olds: Any, room: List[int], depth: int = 0) -> List[dict]:
    """The earlier wordings an exported note tells -- each may tell what it had replaced itself --, checked for their form
    (ValueError: not built as an export is); at most REPLACED_MAX of them for one note (room: how many are left)."""
    if not isinstance(olds, list):
        raise ValueError("replaces")
    out = []
    for o in olds:
        o = {"text": o} if isinstance(o, str) else o
        if not isinstance(o, dict) or not isinstance(o.get("text"), str):
            raise ValueError("replaces")
        if room[0] <= 0:
            break
        room[0] -= 1
        out.append({"text": o["text"], "created": o.get("created"), "replaces": _wordings(o.get("replaces", []), room, depth + 1) if depth < REPLACED_MAX else []})
    return out


def _export_notes(doc: dict) -> List[dict]:
    """The notes of an exported memory (the JSON of format "kontor-memory") as import_file takes them -- TransferError when it
    is of a newer format or not built as an export is."""
    damaged = TransferError(tr("s_ki_g_x_beschaedigt"))
    v, raw = doc.get("version"), doc.get("notes")
    if not isinstance(v, int) or isinstance(v, bool) or v < 1 or not isinstance(raw, list):
        raise damaged
    if v > EXPORT_VERSION:
        raise TransferError(tr("s_ki_g_x_neuer", v))
    if len(raw) > IMPORT_MAX:
        raise TransferError(tr("s_ki_g_x_zu_viele", _count(IMPORT_MAX)))
    out, count = [], 0
    for i, e in enumerate(raw, 1):
        if not isinstance(e, dict) or not isinstance(e.get("text"), str):
            raise damaged
        room = [REPLACED_MAX]
        try:
            rep = _wordings(e.get("replaces", []), room)
        except ValueError:
            raise damaged from None
        count += 1 + REPLACED_MAX - room[0]              # (earlier wordings are kept as notes too: they count)
        if count > IMPORT_MAX:
            raise TransferError(tr("s_ki_g_x_zu_viele", _count(IMPORT_MAX)))
        out.append({"at": i, "text": e["text"], "created": e.get("created"), "changed": e.get("changed"), "kind": e.get("kind"),
                    "names": e.get("names"), "replaces": rep})
    return out


_BULLET = re.compile(r"[-*+\u2022\u2023\u25e6\u2013\u2014][ \t]+(?=\S)")
_SURE_BULLET = "\u2022\u2023\u25e6"                    # signs that are nothing but a list's (a hyphen, a plus, a star can be a note's own: "- 3 %")
_NUMBER = re.compile(r"([0-9]{1,9})[.)][ \t]+(?=\S)")
_BOX = re.compile(r"\[[ xX]\][ \t]+(?=\S)")
_NO_NOTE = re.compile(r"#{1,6}(?:[ \t].*)?|(?:-[ \t]*){3,}|(?:\*[ \t]*){3,}|(?:_[ \t]*){3,}|={3,}|`{3,}[^`]*|~{3,}.*|<!--.*-->|(?=[^|]*\|)(?=[^-]*-)[|:\- \t]+")
_QUOTED = re.compile(r"(?:>[ \t]?)+")
_EXPORTED = re.compile(r"(?i)format[\"']?[ \t]*:?[ \t]*[\"']?" + re.escape(EXPORT_FORMAT))      # how an export names its format: in its head line and in its data


def _list_lines(text: str) -> Iterable[Tuple[int, bool, str]]:
    """The lines of a plain list that can be notes: (number of the line, whether it is indented, what it says) -- ("", for a
    line that is none: empty, a heading, a rule, the fence of a block, a comment, the rule under a table's head)."""
    for no, line in enumerate(io.StringIO(text), 1):
        s = line.strip()
        s = s[_QUOTED.match(s).end():].strip() if s.startswith(">") else s
        yield (no, line[:1] == "\t" or line[:2] == "  ", "" if _NO_NOTE.fullmatch(s) else s)


def _list_notes(text: str) -> List[dict]:
    """A plain list read as notes, a note per line: empty lines, headings and rules are none; the sign or number before an
    item goes -- a hyphen, plus or star only where the lines are a list (half of them and more begin so: "- 3 % Rendite" by
    itself keeps its sign), numbers only where they count up from 1 (so "1. Januar: Miete steigt" keeps its day); an
    indented line without a sign right under an item belongs to it. Marks of bold, emphasis and code go (_unmarked)."""
    lines = bullets = 0
    numbers: List[int] = []
    for _, indented, s in _list_lines(text):
        if not s:
            continue
        hit, num = _BULLET.match(s), _NUMBER.match(s)
        if hit or num or not indented:
            lines += 1
        bullets += 1 if hit else 0
        if num:
            numbers.append(int(num.group(1)))
        if lines > 4 * IMPORT_MAX:
            break
    listed = bullets * 2 >= lines
    counted = len(numbers) >= 2 and numbers[0] == 1 and all(b == a + 1 or b == 1 for a, b in zip(numbers, numbers[1:]))
    out: List[dict] = []
    item = False                                         # the line before was an item of a list (or went on with it)
    for no, indented, s in _list_lines(text):
        if not s:
            item = False
            continue
        hit = _BULLET.match(s) if listed or s[0] in _SURE_BULLET else None
        hit = hit or (_NUMBER.match(s) if counted else None)
        if hit:
            s = s[hit.end():]
            box = _BOX.match(s)
            s = s[box.end():] if box else s
        elif item and indented and out:                  # goes on with the item above
            if len(out[-1]["text"]) <= 100 * TEXT_MAX:
                out[-1]["text"] += " " + s
            continue
        item = bool(hit)
        if len(out) >= IMPORT_MAX:
            raise TransferError(tr("s_ki_g_x_zu_viele", _count(IMPORT_MAX)))
        out.append({"at": no, "text": s})
    for e in out:
        e["text"] = _unmarked(e["text"])
    return [e for e in out if any(c.isalnum() for c in e["text"][:4 * TEXT_MAX])]         # (a lone hyphen, dots: no note)


def _some(notes: List[dict]) -> List[dict]:
    if not notes:
        raise TransferError(tr("s_ki_g_x_keine"))
    return notes


def read_file(text: Any) -> Tuple[str, List[dict]]:
    """A file's text as the notes it would bring: ("kontor", ...) for an exported memory -- the JSON by itself or in the
    Markdown file export_file writes -- or ("list", ...) for any other text, a note per line. Each note {"at": its number
    in the file (a list: its line), "text"}, from an export also "created", "changed", "kind", "names", "replaces"
    [{"text", "created"}] -- nothing of it checked yet (Memory.import_file does that). TransferError for what is no such
    file: no text, another kind of file, an export that is damaged (its data cut off or missing) or of a newer format."""
    if not isinstance(text, str) or not text.replace("\ufeff", "").strip():
        raise TransferError(tr("s_ki_g_x_leer"))
    if "\x00" in text or "\ufffd" in text:               # not a text (or not UTF-8): never a note with signs nobody wrote
        raise TransferError(tr("s_ki_g_x_kein_text"))
    text = text.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")       # (its lines stay where they are: a place in it is named by its line)
    start = text.lstrip()[:12]
    if start.lower().startswith(("{\\rtf", "<?xml", "<!doctype", "<html", "%pdf", "pk\x03\x04")):
        raise TransferError(tr("s_ki_g_x_kein_text"))
    mine = _EXPORTED.search(text) is not None            # an export (or what is left of one): only its data count -- never read as a list
    if start[0] in "{[":                                 # JSON: an export by itself -- or something else
        try:
            doc = json.loads(text)
        except (ValueError, RecursionError):
            doc = None
            if mine or re.match(r"\{|\[\s*[\[{\"0-9]", start):     # (not "[ ] Aufgabe": a line of a list that begins with a bracket)
                raise TransferError(tr("s_ki_g_x_beschaedigt" if mine else "s_ki_g_x_fremd")) from None
        if isinstance(doc, dict) and doc.get("format") == EXPORT_FORMAT:
            return "kontor", _some(_export_notes(doc))
        if isinstance(doc, dict) and ("kontor_backup" in doc or "kontor_backup_encrypted" in doc):
            raise TransferError(tr("s_ki_g_x_sicherung"))
        if doc is not None:
            raise TransferError(tr("s_ki_g_x_fremd"))
    if mine:                                             # the Markdown file of an export: only its data count
        for block in _blocks(text):
            try:
                doc = json.loads(block)
            except (ValueError, RecursionError):
                continue
            if isinstance(doc, dict) and doc.get("format") == EXPORT_FORMAT:
                return "kontor", _some(_export_notes(doc))
        raise TransferError(tr("s_ki_g_x_beschaedigt"))
    return "list", _some(_list_notes(text))


class Memory:
    """The notes, held in memory once read (lazily: nothing is read before the first use) and written file by file."""

    def __init__(self, store, on_change: Optional[Callable[[str, dict, dict], None]] = None, on_forget: Optional[Callable[[List[dict], bool], None]] = None):
        """on_change(what, note, more): told after "remember", "replace", "edit", "forget", "forget_all", "restore", "backup"
        -- for the log of changes (assistant.py). Called after the memory's lock is released.
        on_forget(notes, everything): called before notes are forgotten (everything: all of them, also what could not be
        read) -- what must hold for good is written there first; when it raises, nothing is forgotten."""
        self.store = store
        self.on_change = on_change
        self.on_forget = on_forget
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

    def whole(self) -> bool:
        """Whether every file of notes could be read: only then a note that is not there is gone -- and not just unreadable now."""
        with self.lock:
            self._load()
            return not self._broken

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
        out.update(pinned=bool(n.get("pinned")), how=n["source"]["how"], chat=n["source"].get("chat", ""), pasted=bool(n["source"].get("pasted")), answer=bool(n["source"].get("answer")))
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
            pasted: bool = False, names: Optional[Iterable[str]] = None, quiet: bool = False, by: str = "", answer: bool = False) -> dict:
        """Remembers a note. replaces: notes it takes the place of (they stay, marked as replaced). The same text as a note
        that counts: that one is returned (known), nothing is added. names: the names in it as the look that made it named
        them (a list, empty too: named; None: not yet -- unnamed). quiet: not told to the log; by: who asked for it
        ("settings": the user in the settings, "chat": said in a conversation) -- for the log. answer: it comes from the
        assistant's answer in that conversation, not from the user's words (shown so)."""
        t = self.check(text)
        with self.lock:
            notes = self._load()
            rep = [r for r in dict.fromkeys(replaces) if r in notes and r not in self._replaced]
            same = next((n for n in notes.values() if n["id"] not in self._replaced and same_text(n["text"]) == same_text(t)), None)
            if same is not None:
                return dict(same, known=True)
            now = _now()
            n = _valid({"id": "n" + secrets.token_hex(5), "text": t, "created": now, "changed": now, "pinned": bool(pinned), "kind": kind, "replaces": rep,
                        "names": list(names or []), "named": names is not None, "source": {"how": how if how in HOWS else "manual", "chat": chat, "pasted": bool(pasted), "answer": bool(answer)}})
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
                n.pop("named", None)
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
        if self.on_forget is not None:                   # first what makes it last (outside the lock: it reads the saved conversations)
            before = self.get(nid)
            if before is None:
                raise NoteError(tr("s_ki_g_weg"))
            self.on_forget([before], False)
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
        if self.on_forget is not None:                   # every note there is, also the replaced ones
            with self.lock:
                every = [dict(n) for n in self._load().values()]
            self.on_forget(every, True)
        with self.lock:
            count = len(self._load())
            folder = self.store.data_dir
            try:
                names = os.listdir(folder)
            except OSError:
                names = []
            with self.store.held():                       # not while the key is renewed: it would write them again
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
        there is changed or removed. A backup is a file from outside, so what it brings says so (how "backup"), is never
        pinned (it would push the user's own notes out of the profile), and a note of it can replace only another note of
        the same backup -- never one that was there. Told to the log (how many). Returns
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
                for k in ("batch", "at", "as"):          # (what an import had noted with it: a backup's notes are no import to take back)
                    n["source"].pop(k, None)
                n.pop("pinned", None)
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

    # -- carried elsewhere ---------------------------------------------------------------------------------------------------
    def export_file(self, version: str) -> dict:
        """Everything remembered as one text to keep, to read and to carry into another system (Einstellungen -> KI-Assistent
        -> Gedächtnis -> Exportieren): Markdown -- a list a person reads, each note with its day, where it came from, whether
        it is pinned and what it replaced -- and under it the same as JSON for programs (format "kontor-memory": the
        format's version, when it was exported, Kontor's version; per note "text", "created" and "changed" as ISO 8601,
        "origin" chat / answer / pasted / manual / backup / import, "pinned", "replaces" -- the earlier wordings it took the place
        of, the latest first, each with "text", "created" and its own "replaces" where it had replaced one itself --, "kind"
        and "names" where known). The notes that count, pinned ones first, then the latest. Never a credential: a
        note the check of today takes for one stays out, and the file says how many (left_out -- notes hold none anyway,
        this is the second line). Returns {"name": a name for the file, "text", "notes": how many, "left_out"}."""
        with self.lock:
            notes = self._load()
            pos = {nid: i for i, nid in enumerate(notes)}
            act = sorted((n for n in notes.values() if n["id"] not in self._replaced), key=lambda n: (bool(n.get("pinned")), n["changed"], pos[n["id"]]), reverse=True)
            by_new: Dict[str, List[str]] = {}
            for old, new in self._replaced.items():
                by_new.setdefault(new, []).append(old)

            def earlier(nid: str, room: List[int], seen: Set[str]) -> List[dict]:
                """What a note replaced -- each with what that had replaced in turn ("olds") --, the latest first; room: how many in all."""
                out = []
                for o in sorted(by_new.get(nid) or [], key=lambda i: (notes[i]["changed"], pos[i]), reverse=True):
                    if o not in seen and room[0] > 0:
                        seen.add(o)
                        room[0] -= 1
                        out.append(dict(notes[o], olds=earlier(o, room, seen)))
                return out
            rows = [dict(n, olds=earlier(n["id"], [REPLACED_MAX], {n["id"]})) for n in act]

        def safe(olds: List[dict]) -> List[dict]:
            """... without what today's check takes for a credential (what such a wording had replaced moves up)."""
            out: List[dict] = []
            for o in olds:
                kept = safe(o["olds"])
                out += kept if secret_problem(o["text"]) else [dict(o, olds=kept)]
            return out
        count = len(rows)
        rows = [dict(n, olds=safe(n["olds"])) for n in rows if not secret_problem(n["text"])]
        origin = lambda n: "answer" if n["source"].get("answer") else "pasted" if n["source"].get("pasted") else n["source"]["how"]
        told = lambda olds: [dict({"text": o["text"], "created": _iso(o["created"])}, **({"replaces": told(o["olds"])} if o["olds"] else {})) for o in olds]
        flat = lambda olds: [x for o in olds for x in [o] + flat(o["olds"])]
        entries = []
        for n in rows:
            e: Dict[str, Any] = {"text": n["text"], "created": _iso(n["created"])}
            if n["changed"] != n["created"]:
                e["changed"] = _iso(n["changed"])
            e.update(origin=origin(n), pinned=bool(n.get("pinned")), replaces=told(n["olds"]))
            if n.get("kind"):
                e["kind"] = n["kind"]
            if n.get("names"):
                e["names"] = list(n["names"])
            entries.append(e)
        now = datetime.now()
        head = (("format", EXPORT_FORMAT), ("version", EXPORT_VERSION), ("exported", _iso(now.strftime("%Y-%m-%d %H:%M:%S"))), ("kontor", str(version)))
        data = ["{"] + [" %s: %s," % (json.dumps(k), json.dumps(v, ensure_ascii=False)) for k, v in head] + [' "notes": [']
        data += ["  " + json.dumps(e, ensure_ascii=False) + ("," if i + 1 < len(entries) else "") for i, e in enumerate(entries)] + [" ]", "}"]
        said = {"answer": "ki_g_h_answer", "pasted": "ki_g_eingefuegt", "chat": "ki_g_h_chat", "manual": "ki_g_h_manual", "backup": "ki_g_h_backup", "import": "ki_g_h_import"}
        out = ["# " + tr("s_ki_g_x_titel"), "",
               tr("s_ki_g_x_kopf", str(version), _day(now.strftime("%Y-%m-%d")), now.strftime("%H:%M"), trn("ki_g_n", len(entries), _count(len(entries))), EXPORT_FORMAT, EXPORT_VERSION),
               "", "## " + tr("s_ki_g_x_notizen"), ""]
        if count > len(rows):                            # (said in the file itself: whoever reads it knows that something is missing)
            out[3:3] = ["", trn("s_ki_g_x_ohne", count - len(rows), _count(count - len(rows)))]
        for n in rows:
            out.append("- " + _md(n["text"]))
            out.append("  - " + " · ".join([_day(n["created"]), tr(said[origin(n)])] + ([tr("s_ki_g_x_angeheftet")] if n.get("pinned") else [])))
            out += ["  - %s (%s)" % (tr("ki_g_ersetzt", _md(o["text"])), _day(o["created"])) for o in flat(n["olds"])]
        if not rows:
            out.append(tr("ki_g_leer"))
        # (a backtick is written as its number there, \u0060: the data never end their own block, whatever a note says)
        out += ["", "## " + tr("s_ki_g_x_daten"), "", tr("s_ki_g_x_daten_text"), "", "```json", "\n".join(data).replace("`", "\\u0060"), "```", ""]
        return {"name": "Kontor-%s-%s.md" % (tr("xf_memory"), now.strftime("%Y-%m-%d")), "text": "\n".join(out), "notes": len(entries), "left_out": count - len(rows)}

    def import_file(self, text: Any, check: bool = False, by: str = "") -> dict:
        """Notes of a file into the memory (Einstellungen -> KI-Assistent -> Gedächtnis -> Importieren): an exported memory
        (export_file) or a plain list, a note per line (read_file). A file from outside, so: the whole of it is checked before
        anything is written, and all of it comes in or nothing -- every note goes through what a note typed by hand goes
        through (invisible characters out, not empty, not longer than a note may be, never a credential), and one that does
        not pass refuses the file (problems: where and why). What comes in says so (how "import"), is never pinned, and
        replaces nothing that was there (a note of the file can replace only earlier wordings the same file brings: they
        come along as replaced, each by what the file says replaced it). A note there already -- the same text, counting or
        replaced -- is left out (known; an earlier wording that is there is not made again: what it had replaced moves up), also
        one the file holds twice. Names a file gives for a note count only where they stand in it, and the model still
        looks at it (never "named" by a file). check: nothing is written -- what would happen is told. Told to the log (how
        many). TransferError for what is no such file. Returns {"ok", "kind", "found": notes in the file, "new": those that
        would come, "known", "problems": the first of them, "problem_count", "preview": the first of the new notes,
        "text_max"} and, when it was to be written and nothing spoke against it, "added"."""
        kind, entries = read_file(text)

        def fits(raw: str) -> Tuple[str, str]:
            """(a note's text as it would be kept, why it cannot: "empty", "long", "secret" -- "" when it can)."""
            if len(raw) > 100 * TEXT_MAX:
                return clean(raw[:200]), "long"
            t = clean(raw)
            return t, "empty" if not t else "long" if len(t) > TEXT_MAX else "secret" if secret_problem(t) else ""
        problems: List[dict] = []
        good: List[dict] = []
        bad: List[Tuple[str, str]] = []

        def wordings(olds: List[dict]) -> List[dict]:
            """A note's earlier wordings, each checked as a note is (an empty one is none: what it had replaced moves up) --
            the first that cannot be kept is told (bad)."""
            out: List[dict] = []
            for o in olds:
                t, why = fits(o["text"])
                kept = wordings(o["replaces"])
                if why and why != "empty" and not bad:
                    bad.append((why, t))
                out += kept if why else [{"text": t, "created": o.get("created"), "replaces": kept}]
            return out
        for e in entries:                                # (outside the lock: thousands of notes take a moment)
            t, why = fits(e["text"])
            del bad[:]
            olds = [] if why else wordings(e.get("replaces") or [])
            why, t = bad[0] if bad else (why, t)
            if why:
                problems.append(dict({"at": e["at"], "why": why}, **({"text": t[:80]} if why == "long" else {})))
            else:
                good.append(dict(e, text=t, replaces=olds))
        added: List[dict] = []
        with self.lock:
            notes = self._load()
            have = {same_text(n["text"]) for n in notes.values()}
            fresh, known = [], 0
            for e in good:                               # first the notes that count: one of them is never lost to an earlier wording of another
                key = same_text(e["text"])
                if key in have:
                    known += 1
                    continue
                have.add(key)
                fresh.append(e)
            out = {"ok": not problems, "kind": kind, "found": len(entries), "new": len(fresh), "known": known, "problems": problems[:PROBLEMS_SHOWN],
                   "problem_count": len(problems), "preview": [e["text"] for e in fresh[:PREVIEW_NOTES]], "text_max": TEXT_MAX}
            if problems or check:
                return out
            if not fresh:
                return dict(out, added=0)
            now = _now()
            ids: Set[str] = set()
            batch = secrets.token_hex(6)                 # this import, named in each of its notes (undo_import)

            def note(text: str, created: Any, changed: Any = None, **more) -> dict:
                made = _when(created, now)
                nid = "n" + secrets.token_hex(5)
                while nid in notes or nid in ids:  # pragma: no cover - 40 random bits
                    nid = "n" + secrets.token_hex(5)
                ids.add(nid)
                n = _valid(dict(more, id=nid, text=text, created=made, changed=_when(changed, made), source={"how": "import", "batch": batch, "at": now, "as": _text_key(text)}))
                assert n is not None
                return n

            def earlier(olds: List[dict]) -> List[str]:
                """The notes made for a note's earlier wordings (their ids), each after what it had replaced itself. One
                that is there -- or comes -- as a note of its own is not made: what it had replaced moves up."""
                made: List[str] = []
                for o in olds:
                    before = earlier(o["replaces"])
                    key = same_text(o["text"])
                    if key in have:
                        made += before
                    else:
                        have.add(key)
                        added.append(note(o["text"], o.get("created"), replaces=before))
                        made.append(added[-1]["id"])
                return made
            for e in reversed(fresh):                    # the last of the file first: so its first is the latest (as a file exported: the latest first)
                olds = earlier(e["replaces"])
                added.append(note(e["text"], e.get("created"), e.get("changed"), kind=e.get("kind"), names=e.get("names"), replaces=olds))
            seg = self._free_segment()
            room = SEGMENT - len(self._by_seg.get(seg) or [])
            old_file = seg if self._by_seg.get(seg) else 0       # the file that was there and takes the first of them: written last
            parts: List[int] = []
            for n in added:
                if room <= 0:
                    seg, room = seg + 1, SEGMENT
                if not parts or parts[-1] != seg:
                    parts.append(seg)
                notes[n["id"]] = n
                self._put(n["id"], seg)
                room -= 1
            written: List[int] = []
            try:                                         # the new files first: a write that fails then leaves nothing of it behind
                for seg in [s for s in parts if s != old_file] + [s for s in parts if s == old_file]:
                    self._write(seg)
                    written.append(seg)
            except Exception:
                for n in added:
                    notes.pop(n["id"], None)
                    self._take(n["id"])
                for seg in parts:
                    if not self._by_seg.get(seg):
                        self._by_seg.pop(seg, None)
                for seg in written:                      # (never the file that was there: it is the last to be written)
                    try:
                        self.store.delete(self._file(seg))
                    except Exception as e:
                        log.warning("Memory: a file of an import that failed not removed (%s)", type(e).__name__)
                self._rev += 1
                raise
            self._relink()
            self.epoch += 1
        log.info("Memory: %d note(s) imported from a file", len(fresh))
        self._tell("import", {}, count=len(fresh), by=by)
        return dict(out, added=len(fresh), batch=batch)

    def _imports(self) -> Dict[str, Tuple[str, List[dict], List[dict]]]:
        """The imports there are notes of: batch -> (when, its notes that can be taken back, its notes that stay). Taken back
        is what is as it came: the same text, not pinned, not replaced by a note from elsewhere -- and with it the earlier
        wordings the file brought for it (those of a note that stays, stay). Called with the lock held."""
        notes = self._notes or {}
        mine: Dict[str, List[dict]] = {}
        for n in notes.values():
            b = n["source"].get("batch")
            if b:
                mine.setdefault(b, []).append(n)
        out = {}
        for b, lst in mine.items():
            ids = {n["id"] for n in lst}
            same = lambda n: n["source"].get("as") == _text_key(n["text"]) and not n.get("pinned")
            go = {n["id"] for n in lst if n["id"] not in self._replaced and same(n)}
            more = True
            while more:                                  # the earlier wordings of what goes, all the way back
                more = False
                for n in lst:
                    if n["id"] not in go and self._replaced.get(n["id"]) in go and self._replaced[n["id"]] in ids and same(n):
                        go.add(n["id"])
                        more = True
            out[b] = (max(n["source"].get("at", "") for n in lst), [n for n in lst if n["id"] in go], [n for n in lst if n["id"] not in go])
        return out                                       # (in the order the imports came: notes are kept in the order they were made)

    def last_import(self) -> Optional[dict]:
        """The latest import of which something can be taken back: {"batch", "at", "notes": how many notes that count would
        go, "stay": how many stay (changed, pinned or replaced since)} -- None: there is none."""
        with self.lock:
            self._load()
            best = None
            for b, (at, go, stay) in self._imports().items():
                if go and (best is None or at >= best["at"]):      # (in one second: the later one)
                    count = lambda lst: sum(1 for n in lst if n["id"] not in self._replaced)
                    best = {"batch": b, "at": at, "notes": count(go), "stay": count(stay)}
            return best

    def undo_import(self, batch: str, by: str = "") -> dict:
        """An import taken back in one step: exactly its notes that are as they came (see _imports) are forgotten -- as any
        note is (first what makes it last: on_forget; their embeddings; gone from their files) --, the others stay and are
        counted. All of it or nothing: a file that cannot be written leaves the notes as the files have them, and raises.
        Told to the log (how many). Returns {"removed": notes that counted, "stay"}; NoteError: no such import (any more)."""
        with self.lock:
            self._load()
            hit = self._imports().get(str(batch))
            gone = [dict(n) for n in hit[1]] if hit else []
        if not gone:
            raise NoteError(tr("s_ki_g_import_weg"))
        if self.on_forget is not None:                   # (outside the lock: it reads the saved conversations)
            self.on_forget(gone, False)
        with self.lock:
            notes = self._load()
            hit = self._imports().get(str(batch))
            ids = {n["id"] for n in gone}
            if not hit or {n["id"] for n in hit[1]} != ids:      # changed meanwhile: asked again
                raise NoteError(tr("s_ki_g_import_weg"))
            removed = sum(1 for i in ids if i not in self._replaced)
            stay = sum(1 for n in hit[2] if n["id"] not in self._replaced)
            segs = {self._seg[i] for i in ids}
            try:
                for i in ids:
                    self._vec.pop(i, None)
                for seg in sorted(segs):                 # the embeddings first, as when one note is forgotten
                    self._by_seg[seg] = [i for i in self._by_seg[seg] if i not in ids]
                    self._write_vectors(seg)
                for i in ids:
                    notes.pop(i)
                    self._seg.pop(i)
                    self._used.pop(i, None)
                for seg in sorted(segs):
                    self._write(seg)
            except Exception:
                self._notes, self._ix = None, None       # as the files have it (read anew with the next use)
                self._rev += 1
                raise
            try:
                self.store.save(USED_FILE, {"v": FORMAT, "used": self._used})
            except Exception as e:
                log.warning("Memory: used notes not written (%s)", type(e).__name__)
            self._relink()
            self.epoch += 1
        log.info("Memory: an import taken back (%d note(s))", removed)
        self._tell("import_undo", {}, count=removed, by=by, notes=gone)
        return {"removed": removed, "stay": stay}

    def unnamed(self, limit: int) -> List[dict]:
        """Notes that count whose names nobody has named yet: typed in the settings or back from a backup (a note from a
        conversation is named when it is made; changed in the settings, its names are gone) -- the latest first."""
        with self.lock:
            return [dict(n) for n in self.active() if not n.get("named")][:max(0, int(limit))]

    def set_names(self, got: Dict[str, Tuple[str, List[str]]]) -> int:
        """Names the model named: id -> (the text it was shown, its names). Kept only for a note still there with that text,
        and only names that stand in it (folded: Müller is Mueller) -- the model's answer is input like any other. Each note
        given counts as named from now on (the caller gives only those the model answered for in full). Not a change the
        profile follows. Returns how many names were kept."""
        with self.lock:
            notes = self._load()
            segs, kept = set(), 0
            for nid, (text, names) in got.items():
                n = notes.get(nid)
                if n is None or n["text"] != text or nid not in self._seg:
                    continue
                inside = " %s " % _fold(n["text"])
                ok = [clean(x)[:60] for x in names if isinstance(x, str) and clean(x) and _fold(x) and " %s " % _fold(x) in inside][:12]
                n["names"] = list(dict.fromkeys((n.get("names") or []) + ok))[:12]
                if not n["names"]:
                    n.pop("names")
                n["named"] = True
                kept += len(ok)
                segs.add(self._seg[nid])
            for seg in segs:
                self._write(seg)
            return kept

    # -- nothing of it into an internet search -------------------------------------------------------------------------------
    def own_words(self, common: Set[str]) -> Tuple[Set[str], Set[str]]:
        """(words, phrases) of the notes that must not go out in an internet search: the names Kontor can tell in them.
        A name is what the note names as one (names: the model named them, each stands in its note); the capitalised words
        after a form of address (Frau Dr. Ottilie von Nebelhorn) or after "heißt", "heiße", "namens", "called", "Name ist",
        "name is"; a word with a capital inside (a brand) or all in capitals. Three letters and more. A name said so (after a
        form of address, "heißt") blocks as a word and as the beginning of one, whatever it is. A name the model named does
        too -- but one of three letters, or one Kontor's own texts use as a word (common: Klein, Mia), only as a whole word
        (phrases), and a word for a kind of thing (GENERIC: Sparkasse) not at all. A brand or a word in capitals only
        unless Kontor's own texts use it. Free text has no sure sign of a name, and blocking every noun of every note would
        end all searching: this is the second line -- the first is the card that shows every search before it goes out."""
        words: Set[str] = set()
        phrases: Set[str] = set()
        short = {"dr", "prof", "mr", "mrs", "ms", "dipl", "ing", "med", "jur", "rer", "nat"}      # written with a full stop
        address = {"herr", "herrn", "frau", "familie"} | short
        naming = {"heisst", "heissen", "heisse", "namens", "called", "named"}
        name_is = {"name", "vorname", "nachname", "familienname", "surname"}, {"ist", "is", "lautet", "war", "was"}       # Mein Name ist ..., my name is ...
        particle = {"von", "van", "de", "der", "den", "zu", "zur", "vom", "la", "le", "di", "del"}

        def take(toks: List[str], how: str) -> None:
            """how: "said" (after a form of address or "heißt"), "named" (by the model), "looks" (a brand, capitals)."""
            got = []
            for tok in toks:
                f = _fold(tok).replace(" ", "")
                if len(f) < 3 or not f.isalpha() or f in LEGAL or f in address or (how != "said" and f in GENERIC):
                    continue
                plain = len(f) < 4 or f in common        # no telling word by itself
                if how == "looks" and plain:
                    continue
                got.append(f)
                (phrases if how == "named" and plain else words).add(f)       # (phrases: found as a whole word only)
            if len(got) >= 2:
                phrases.add("".join(got))
        with self.lock:
            notes = list(self._load().values())
        for n in notes:
            for name in n.get("names") or []:
                take(re.findall(r"[^\W\d_]+", name), "named")
            found = list(re.finditer(r"[^\W\d_]+", n["text"]))
            toks = [m.group(0) for m in found]
            # two words belong together when only a space, a hyphen or the full stop of an abbreviation (Dr. med.) lies between them
            joined = lambda k: k > 0 and re.fullmatch(r"\s+|-|\.\s*" if _fold(toks[k - 1]) in short else r"\s+|-", n["text"][found[k - 1].end():found[k].start()]) is not None
            i = 0
            while i < len(toks):
                tok, f = toks[i], _fold(toks[i])
                first = i + 1
                if f in name_is[0] and i + 2 < len(toks) and _fold(toks[i + 1]) in name_is[1] and joined(i + 1):
                    f, first = "heisst", i + 2
                if f in address or f in naming:          # what follows is a name: its capitalised words, particles between them
                    j, run = first, []
                    while j < len(toks) and len(run) < 4 and joined(j) and (_fold(toks[j]) in address or _fold(toks[j]) in particle or toks[j][:1].isupper()):
                        if f in naming and _fold(toks[j]) in STOP:       # (das heißt Sie ...: no name)
                            break
                        if _fold(toks[j]) not in address and _fold(toks[j]) not in particle:
                            run.append(toks[j])
                        elif _fold(toks[j]) in address and run:      # the next person (Herr Klein, Frau Lange)
                            break
                        j += 1
                    take(run, "said")
                    i = j if run else i + 1
                    continue
                if re.search(r"[a-zäöüß][A-ZÄÖÜ]", tok) or (tok.isupper() and len(tok) >= 4):
                    take([tok], "looks")
                i += 1
        return words, phrases


_MAYBE_SECRET = re.compile(r"(?i)pass|kennw|pin|tan|code|schl(?:ü|ue)ssel|key|cvv|cvc|kart|card|log-?in|zugang|geheim|token|secret|credential|phrase"
                           r"|\d{4}[ .-]?\d{4}[ .-]?\d{4}")


def _answer_ok(text: str) -> bool:
    """Whether an answer may be kept for the search in conversations: none that holds a credential (an answer that repeats
    what the user said in it -- Was war meine PIN? -- is kept without its text). A quick look first: the whole check only
    where a secret's word or a long number stands."""
    return _MAYBE_SECRET.search(text) is None or not secret_problem(text)


class Forgotten:
    """What was forgotten, kept so that it stays forgotten in the search in saved conversations whatever happens to that
    search's own files: the ids of forgotten notes and the keys of the turns hidden for them (Talks.key: a checksum of the
    turn's text) -- never a text. One encrypted file in Kontor's data folder (GONE_FILE), written before a note goes: a
    list that cannot be written means nothing is forgotten (the user is told). Deleted with all saved conversations
    (nothing is left to hide then) and with a reset; never in the backup."""

    def __init__(self, store):
        self.store = store
        self.lock = threading.RLock()
        self._notes: Optional[Dict[str, None]] = None      # ids of forgotten notes, in the order they went
        self._turns: Dict[str, None] = {}                  # keys of hidden turns

    def _load(self) -> None:
        if self._notes is not None:
            return
        if getattr(self.store, "is_open", True) is False:
            raise StoreLocked("locked")
        try:
            doc = self.store.load(GONE_FILE, {})
            if not isinstance(doc, dict):
                raise ValueError("format")
        except StoreLocked:
            raise
        except Exception as e:                           # (the turns hidden so far are in the search's own files too: taken from there, Talks._load)
            log.warning("Memory: the list of what was forgotten is not readable (%s) -- begun anew", type(e).__name__)
            doc = {}
        self._notes = {x: None for x in doc.get("notes") or [] if isinstance(x, str) and _NOTE_ID.fullmatch(x)}
        self._turns = {x: None for x in doc.get("turns") or [] if isinstance(x, str) and re.fullmatch(r"[0-9a-f]{12}", x)}

    def _save(self) -> None:
        self.store.save(GONE_FILE, {"v": FORMAT, "notes": list(self._notes or {})[-GONE_MAX:], "turns": list(self._turns)[-GONE_MAX:]})

    def note(self, nid: str) -> bool:
        """Whether a note was forgotten (and not brought back since)."""
        with self.lock:
            self._load()
            return nid in (self._notes or {})

    def turn(self, key: str) -> bool:
        """Whether a turn of a saved conversation is hidden for good."""
        with self.lock:
            self._load()
            return key in self._turns

    def add(self, notes: Iterable[str] = (), turns: Iterable[str] = ()) -> None:
        """Notes forgotten, turns hidden for them -- written at once; raises when that fails (then nothing was added)."""
        with self.lock:
            self._load()
            assert self._notes is not None
            new_n = [x for x in dict.fromkeys(notes) if _NOTE_ID.fullmatch(str(x)) and x not in self._notes]
            new_t = [x for x in dict.fromkeys(turns) if re.fullmatch(r"[0-9a-f]{12}", str(x)) and x not in self._turns]
            if not new_n and not new_t:
                return
            self._notes.update(dict.fromkeys(new_n))
            self._turns.update(dict.fromkeys(new_t))
            try:
                self._save()
            except Exception:
                for x in new_n:
                    self._notes.pop(x, None)
                for x in new_t:
                    self._turns.pop(x, None)
                raise
            for d in (self._notes, self._turns):
                for x in list(d)[:max(0, len(d) - GONE_MAX)]:
                    d.pop(x)

    def back(self, notes: Iterable[str]) -> None:
        """Notes brought back (taken back right after they were forgotten): they count again -- the turns hidden for them stay
        hidden (they said what was to be forgotten)."""
        with self.lock:
            self._load()
            assert self._notes is not None
            had = [x for x in notes if x in self._notes]
            if had:
                for x in had:
                    self._notes.pop(x)
                self._save()

    def clear(self) -> None:
        """Nothing left to hide (every saved conversation deleted, Kontor reset): the list goes."""
        with self.lock, self.store.held():
            for name in (self.store.path(GONE_FILE), self.store.path(GONE_FILE) + ".tmp", self.store.path(GONE_FILE) + ".renew"):
                try:
                    os.remove(name)
                except FileNotFoundError:
                    pass
                except OSError as e:
                    log.warning("Memory: the list of what was forgotten not removed (%s)", e)
            try:
                self.store.delete(GONE_FILE)             # (and out of the store's own memory of it)
            except (OSError, StoreLocked):
                pass
            self._notes, self._turns = ({}, {}) if getattr(self.store, "is_open", True) else (None, {})


class Talks:
    """The search index of the saved conversations: for each, its questions and answers as the search needs them (cut, see
    TALK_Q/TALK_A) -- from a conversation with text from the internet or a receipt (or a file given) in it only the user's
    questions (what came from outside never comes back through the search). A turn whose question holds a credential
    (secret_problem) never comes in and never out; an answer that holds one, only without it. Encrypted in Kontor's data folder (memory-chats-0001.json, ...: a few
    conversations per file, so that an answer writes one small file; a file that cannot be read goes, its conversations are
    put in again). A conversation deleted leaves it; a turn a forgotten note was made from, rested on or says again when it
    is forgotten is hidden for good (by a key of its text, never the text itself) -- in the list of what was forgotten
    (Forgotten: gone), which holds when this index is lost, cannot be written or is made anew. With the model for finding
    by meaning, each turn's embedding is kept with it. Never in the backup (as the conversations themselves); a reset
    deletes it with them."""

    def __init__(self, store):
        self.store = store
        self.gone = Forgotten(store)
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
        hidden: List[str] = []
        stale: Set[int] = set()
        for seg in self._names():
            try:
                doc = self.store.load(TALKS_FILE % seg, {})
                for cid, d in (doc.get("chats") or {}).items():
                    if _CID.fullmatch(str(cid)) and isinstance(d, dict) and isinstance(d.get("items"), list) and cid not in docs:
                        d = {"day": str(d.get("day") or "")[:10], "hidden": [str(k) for k in d.get("hidden") or [] if isinstance(k, str)][-1000:],
                             "items": [it for it in d["items"] if isinstance(it, dict) and isinstance(it.get("k"), str) and isinstance(it.get("q"), str)]}
                        hidden += d["hidden"]
                        # what must never come out, whoever wrote the file: a turn hidden for good (not taken out then: the file
                        # could not be written), a question with a credential (taken in by a version before 3.17)
                        keep = [it for it in d["items"] if not self.gone.turn(it["k"]) and not secret_problem(it["q"])]
                        for it in keep:                  # ... and an answer that repeats one (Was war meine PIN?): only the question
                            if it.get("a") and not _answer_ok(str(it["a"])):
                                it["a"] = ""
                                it.pop("v", None)
                                stale.add(seg)
                        if len(keep) != len(d["items"]):
                            d["items"] = keep
                            stale.add(seg)
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
        try:                                             # turns hidden by a version before 3.17 (only here until then): into the list that lasts
            self.gone.add(turns=hidden)
            for seg in sorted(stale):
                self._write(seg)
        except StoreLocked:
            raise
        except Exception as e:                           # (tried again with the next start; nothing of it is handed out meanwhile)
            log.warning("Memory: the search in conversations not brought up to date (%s)", type(e).__name__)
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
        conversations saved before Kontor said so). gone(id): whether a note is forgotten (left out: by the list of what was
        forgotten; a note that is only missing -- its file cannot be read -- is not) -- a turn a forgotten note was made from,
        forgotten in or rested on is hidden for good, as is every turn the list of what was forgotten names. A turn whose
        question holds a credential never comes in (one whose answer holds one: without the answer). The same turn twice: once. An embedding is kept for a turn that stays
        the same."""
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
                if k not in hidden and (self.gone.turn(k) or any(gone(n) if gone is not None else self.gone.note(n) for n in notes)):
                    hidden.append(k)
                if k in hidden or k in seen or not q.strip() or secret_problem(q):
                    continue
                seen.add(k)
                it = {"k": k, "q": clean(q)[:TALK_Q], "a": "" if foreign or not _answer_ok(a) else clean(a)[:TALK_A]}
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
                with self.store.held():                   # not while the key is renewed: it would write them again
                    for name in names:
                        if re.fullmatch(r"memory-chats-\d{4,6}\.json(?:\.enc)?(?:\.tmp|\.renew)?", name):
                            try:
                                os.remove(os.path.join(self.store.data_dir, name))
                            except OSError as e:
                                log.warning("Memory: a file of the search in conversations not removed (%s)", e)
                self._docs, self._seg, self._ix = None, {}, None
                self._terms, self._vecs = {}, {}
                self._rev += 1
                self.gone.clear()                        # no conversation left: nothing to hide
                return
            docs = self._load()
            segs = {self._seg.pop(c) for c in list(cids) if docs.pop(c, None) is not None and c in self._seg}
            self._writes(segs)

    @staticmethod
    def _says(words: Set[str], sets: List[Set[str]]) -> bool:
        """Whether a turn of these words says one of the forgotten notes again (sets: the words of each): all of its words,
        three quarters of them in a note of more than two."""
        return any(len(w & words) * 4 >= len(w) * 3 and (len(w) > 2 or w <= words) for w in sets)

    @staticmethod
    def _note_words(texts: Iterable[str]) -> List[Set[str]]:
        return [w for w in (set(terms(t)) for t in texts) if len(w) >= 2]      # (a note of one word: only where it was made)

    def matching(self, turns: Iterable[Any], foreign: bool, note_ids: Iterable[str] = (), texts: Iterable[str] = (), every_note: bool = False) -> List[str]:
        """The keys of the turns of a saved conversation that is not in the search yet (saved by an earlier version, being put
        in right now) which forgetting these notes must hide -- as forget finds them in the search itself."""
        ids, sets, out = set(note_ids), self._note_words(texts), []
        pairs = self.pairs(turns)
        foreign = foreign or any(f for _, _, _, f in pairs)
        for q, a, notes, _ in pairs:
            made = bool(notes) and (every_note or bool(ids & set(notes)))
            if made or self._says(set(terms(clean(q)[:TALK_Q] + " " + ("" if foreign else clean(a)[:TALK_A]))), sets):
                out.append(self.key(q, a))
        return out

    def forget(self, note_ids: Iterable[str] = (), texts: Iterable[str] = (), every_note: bool = False, turns: Iterable[str] = ()) -> List[str]:
        """Notes are forgotten (their ids and texts): hidden for good -- the turns they were made from, forgotten in or rested
        on, and every turn that says one of them again (all of its words, three quarters of them in a note of more than two;
        a note of one word only where it was made). every_note: every note is forgotten -- every turn a note was made from or
        rested on. turns: keys of further turns to hide (of conversations not in the search yet: matching). First into the
        list of what was forgotten (Forgotten) -- that failing, nothing is hidden and the failure goes on to the caller, who
        then forgets nothing; this search's own files after it (one that cannot be written: said in the log, the list holds).
        Returns the turns hidden (cid#key)."""
        with self.lock:
            docs = self._load()
            ids = set(note_ids)
            sets = self._note_words(texts)
            hit = [(cid, it) for cid, d in docs.items() for it in d["items"]
                   if (bool(it.get("n")) and (every_note or bool(ids & set(it["n"])))) or self._says(self._words(cid, it), sets)]
            self.gone.add(notes=ids, turns=[it["k"] for _, it in hit] + list(turns))
            segs, gone = set(), []
            for cid, it in hit:
                d = docs[cid]
                d["hidden"] = (d["hidden"] + [it["k"]])[-1000:]
                d["items"] = [x for x in d["items"] if x is not it]
                gone.append(cid + "#" + it["k"])
                segs.add(self._seg[cid])
            try:
                self._writes(segs)
            except StoreLocked:
                raise
            except Exception as e:                       # never handed out all the same (the list holds); out of the file with its next write
                log.warning("Memory: a file of the search in conversations not written (%s) -- what was forgotten stays hidden by its list", type(e).__name__)
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

    def search(self, query: Any, limit: int = 4, exclude: Iterable[str] = (), meaning: Optional[Tuple[str, array]] = None,
               gone: Optional[Callable[[str], bool]] = None) -> List[dict]:
        """Turns of saved conversations that fit a query (ranked as Memory.search ranks notes), not of the conversations in
        exclude: [{"id": cid#key, "chat", "day", "question", "answer", "score"}] -- the best first, the later among equals.
        Never a turn the list of what was forgotten names, or one made from or resting on a forgotten note (gone(id), as for
        put) -- whatever this search's own files say."""
        with self.lock:
            ix = self._index()
            items = self._items()
            out_of = set(exclude)
            skip = {i for i, (cid, _, it) in items.items() if cid in out_of or self.gone.turn(it["k"])
                    or any(gone(n) if gone is not None else self.gone.note(n) for n in it.get("n") or [])}
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


class Library:
    """Embeddings of texts that are no notes -- the help, the texts of transactions -- each by a key of its text, in a few
    files (memory-help-0001.json, ...; which one: by the key), encrypted like everything in the data folder. Made of what
    Kontor has anyway, in the background (written in batches: flush), made anew with another model, pruned of what is gone;
    a reset deletes them (gen: what was made before is never written after that)."""

    def __init__(self, store, kind: str):
        self.store, self.kind = store, kind
        self.lock = threading.RLock()
        self._vec: Optional[Dict[str, Tuple[str, array, float]]] = None      # key -> (model, embedding, its length)
        self._dirty: Set[int] = set()
        self.gen = 0

    @staticmethod
    def key(text: str) -> str:
        return _text_key(text)

    def _bucket(self, key: str) -> int:
        return int(key[:4], 16) % LIB_BUCKETS + 1

    def _load(self) -> Dict[str, Tuple[str, array, float]]:
        if self._vec is not None:
            return self._vec
        if getattr(self.store, "is_open", True) is False:
            raise StoreLocked("locked")
        vec: Dict[str, Tuple[str, array, float]] = {}
        for b in range(1, LIB_BUCKETS + 1):
            try:
                doc = self.store.load(LIB_FILE % (self.kind, b), {})
                model = str(doc.get("model") or "")
                for k, b64 in (doc.get("vecs") or {}).items():
                    a = array("b", base64.b64decode(b64))
                    if a:
                        vec[str(k)] = (model, a, _norm(a))
            except StoreLocked:
                raise
            except Exception as e:
                log.warning("Memory: a file of embeddings (%s) is not readable (%s) -- made anew", self.kind, type(e).__name__)
        self._vec = vec
        return vec

    def missing(self, model: str, texts: Dict[str, str]) -> List[str]:
        """Of these texts (key -> text), the keys without an embedding of this model."""
        with self.lock:
            have = self._load()
            return [k for k in texts if (have.get(k) or ("",))[0] != model]

    def put(self, model: str, got: Dict[str, Iterable[float]], gen: Optional[int] = None, flush: bool = True) -> bool:
        """Embeddings made (key -> numbers). gen: as when they were begun -- reset since: nothing is kept (False)."""
        with self.lock:
            if gen is not None and gen != self.gen:
                return False
            have = self._load()
            for k, v in got.items():
                a = pack(v)
                have[k] = (model, a, _norm(a))
                self._dirty.add(self._bucket(k))
            for k in [k for k, v in have.items() if v[0] != model]:          # of another model: of no use any more
                have.pop(k)
                self._dirty.add(self._bucket(k))
            if flush:
                self.flush()
            return True

    def prune(self, alive: Set[str], gen: Optional[int] = None) -> None:
        """What is no longer there (keys not in alive) goes."""
        with self.lock:
            if gen is not None and gen != self.gen:
                return
            have = self._load()
            for k in [k for k in have if k not in alive]:
                have.pop(k)
                self._dirty.add(self._bucket(k))
            self.flush()

    def flush(self) -> None:
        with self.lock:
            if self._vec is None:
                self._dirty.clear()
                return
            for b in sorted(self._dirty):
                mine = {k: base64.b64encode(v[1].tobytes()).decode("ascii") for k, v in self._vec.items() if self._bucket(k) == b}
                models = {v[0] for k, v in self._vec.items() if self._bucket(k) == b}
                if mine:
                    self.store.save(LIB_FILE % (self.kind, b), {"v": FORMAT, "model": next(iter(models)), "vecs": mine})
                else:
                    self.store.delete(LIB_FILE % (self.kind, b))
            self._dirty.clear()

    def vectors(self, model: str, keys: Iterable[str]) -> Dict[str, array]:
        """The embeddings of these texts (key -> numbers as kept) made by this model -- only those there are."""
        with self.lock:
            have = self._load()
            out = {}
            for k in keys:
                v = have.get(k)
                if v is not None and v[0] == model:
                    out[k] = v[1]
            return out

    def size(self) -> int:
        """How many embeddings there are (of any model)."""
        with self.lock:
            return len(self._load())

    def likeness(self, model: str, q: array, keys: Iterable[str]) -> Dict[str, float]:
        with self.lock:
            have = self._load()
            qn = _norm(q)
            out = {}
            for k in keys:
                v = have.get(k)
                if v is not None and v[0] == model and len(v[1]) == len(q):
                    out[k] = sum(map(operator.mul, q, v[1])) / (qn * v[2])
            return out

    def drop_all(self) -> None:
        with self.lock:
            self.gen += 1
            try:
                names = os.listdir(self.store.data_dir)
            except OSError:
                names = []
            with self.store.held():                       # not while the key is renewed: it would write them again
                for name in names:
                    if re.fullmatch(r"memory-%s-\d{4,6}\.json(?:\.enc)?(?:\.tmp|\.renew)?" % re.escape(self.kind), name):
                        try:
                            os.remove(os.path.join(self.store.data_dir, name))
                        except OSError as e:
                            log.warning("Memory: a file of embeddings not removed (%s)", e)
            self._vec, self._dirty = None, set()
