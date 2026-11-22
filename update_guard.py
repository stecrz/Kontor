"""Before an update is installed: what could the new version do that the installed one cannot?

The installed version reads the files of the new one -- without running any of them -- and compares what both hold of the
things that let a program reach beyond itself:
  - parts of Python outside a list of harmless ones (network, starting programs, loading code, anything unknown);
  - every function that calls such a part, as a whole (so what is handed to the call counts too), the names it uses from its
    file and the functions of its file it calls; ways around a plain call (reaching a module through another one, looking
    names up as text, the insides of Python);
  - Internet addresses written anywhere in the program or its pages, and places on a Mac from which other programs are
    started (LaunchAgents, shell profiles ...);
  - what a page could use to send something or to leave Kontor (the pages' security rules are part of the program above);
  - files Kontor cannot read this way (helpers in Swift, scripts, anything that is no text, picture or page), and the two
    files of this check themselves -- a change to the check is always shown, since it decides about the update after it.
Nothing new or changed among these: the update is installed as before, without a word. Otherwise it waits, and the settings
show what was found -- an update is then installed only after you have seen that and said so.

This narrows the way for a change slipped into the repository; it cannot close it (a program can be rebuilt in ways no
reader of its text foresees). Only what is new or changed is named, never what the installed version already does.
"""
from __future__ import annotations

import ast
import hashlib
import re
from typing import Dict, Iterable, List, Optional, Set, Tuple

# Parts of Python a program file may import without being asked about (they compute, read and write files, keep time).
# Everything else -- network, processes, loading code, and whatever is not known here -- is named when it is new.
HARMLESS = frozenset("""__future__ abc argparse array ast atexit base64 binascii bisect calendar collections colorsys contextlib copy csv
dataclasses datetime decimal difflib enum errno fcntl fnmatch fractions functools getpass glob gzip hashlib heapq hmac html io itertools
ipaddress json locale logging math mimetypes numbers operator os pathlib platform plistlib queue random re secrets shlex shutil signal
stat statistics string struct sys tarfile tempfile textwrap threading time traceback types typing unicodedata uuid warnings wave weakref
zipfile zlib""".split())
HARMLESS_SUB = frozenset(("collections.abc", "concurrent.futures.thread", "email.utils", "html.parser", "logging.handlers", "os.path",
                          "urllib.parse", "urllib.error", "xml.etree.ElementTree", "xml.sax.saxutils", "http.cookies"))
# (never a whole package here whose other parts reach out: "http" alone would make http.client harmless)
# ... and what in those harmless parts still reaches out
RISKY_IN = {
    "os": ("system", "popen", "fork", "forkpty", "startfile", "kill", "killpg", "putenv", "unsetenv", "environ", "environb", "sys", "abc", "st",
           "execl", "execle", "execlp", "execlpe", "execv", "execve", "execvp", "execvpe", "spawnl", "spawnle", "spawnlp", "spawnlpe", "spawnv",
           "spawnve", "spawnvp", "spawnvpe", "posix_spawn", "posix_spawnp", "plock", "openpty", "login_tty", "register_at_fork", "pipe", "dup2",
           "mkfifo", "mknod", "chroot", "setuid", "seteuid", "fexecve", "add_dll_directory"),
    "sys": ("modules", "meta_path", "path", "path_hooks", "path_importer_cache", "settrace", "setprofile", "addaudithook", "_getframe", "argv",
            "executable", "stdin", "exit", "builtin_module_names", "displayhook", "excepthook", "unraisablehook", "breakpointhook", "__dict__",
            "_current_frames", "call_tracing", "setrecursionlimit", "_xoptions", "flags", "prefix", "base_prefix", "exec_prefix"),
    "logging": ("config",),
    "logging.handlers": ("SocketHandler", "DatagramHandler", "SysLogHandler", "HTTPHandler", "SMTPHandler", "NTEventLogHandler"),
    "shutil": ("register_unpack_format", "register_archive_format"),
    "functools": ("reduce",), "types": ("FunctionType", "CodeType", "ModuleType", "MethodType"), "operator": ("attrgetter", "methodcaller"),
    "signal": ("pthread_kill", "set_wakeup_fd"), "uuid": ("getnode", "uuid1"),
    "typing": ("get_type_hints", "ForwardRef", "_eval_type"),          # turn a text into code
    "threading": ("settrace", "setprofile", "settrace_all_threads", "setprofile_all_threads", "excepthook", "_shutdown"),
    "atexit": ("_run_exitfuncs",), "copy": ("_reconstruct",), "dataclasses": ("make_dataclass",), "ast": ("PyCF_ONLY_AST",),
}
# names that stand for a part of Python wherever they turn up behind a dot (shutil.os.system, logging.handlers.socket ...)
MODULE_NAMES = frozenset("""os sys socket subprocess ssl ctypes importlib builtins urllib pickle marshal pty runpy webbrowser asyncio ftplib
smtplib xmlrpc selectors posix nt _os _sys _socket _ssl _posixsubprocess _thread multiprocessing sqlite3 pydoc inspect gc codeop imp pkgutil
zipimport""".split())
# the insides of Python, reached by name: with them any part can be had without importing it
INSIDES = frozenset("""__globals__ __builtins__ __subclasses__ __import__ __loader__ __spec__ __code__ __closure__ __mro__ __base__
__bases__ __getattribute__ __reduce__ __reduce_ex__ gi_frame cr_frame f_globals f_builtins f_locals f_back tb_frame __wrapped__ __func__
__self__ func_globals""".split())
INSIDES_OF_MODULES = frozenset(("__dict__", "__getattr__", "__file__", "__path__", "__name__", "__package__", "__all__"))     # ... only behind a part of Python
BUILTINS = frozenset("eval exec compile __import__ globals locals vars breakpoint getattr setattr delattr __builtins__ memoryview input".split())
# an attribute read through a name that is fine: the errors and constants of the parts that reach out
PLAIN = re.compile(r"^(subprocess\.(TimeoutExpired|CalledProcessError|SubprocessError|CompletedProcess|PIPE|DEVNULL|STDOUT)"
                   r"|socket\.(timeout|error|gaierror|herror|SHUT_RDWR)|ssl\.(SSLError|CertificateError|SSLSocket)|http\.client\.(HTTPException|IncompleteRead|HTTPResponse)"
                   r"|os\.environ\.get|sys\.(argv|exit|stdin\.isatty)|sqlite3\.(Error|DatabaseError|OperationalError))$")

# places from which macOS or a shell starts other programs, and folders that leave the Mac by themselves
PLACES = re.compile(r"(?i)LaunchAgents|LaunchDaemons|\.zshrc|\.zprofile|\.zshenv|\.zlogin|\.bash_profile|\.bashrc|\.profile\b|crontab|/etc/"
                    r"|\.ssh\b|authorized_keys|Application Scripts|StartupItems|Login ?Items|periodic|\.config/|Mobile Documents|CloudStorage|Dropbox"
                    r"|iCloud|/Volumes/|\.pth\b|sitecustomize|usercustomize|PYTHONSTARTUP|PYTHONPATH|DYLD_|LD_PRELOAD|/dev/tcp|\bcurl\b|\bwget\b"
                    r"|\bnc\b|\bncat\b|\bssh\b|\bscp\b|\bsftp\b|\brsync\b|\bftp\b|\btelnet\b|\bdig\b|\bnslookup\b|do shell script|open location"
                    r"|\bmailto:|\bsmb:|\bafp:|\bdata:text/html|javascript:")
HOST = re.compile(r"(?i)(?:[a-z][a-z0-9+.-]*:)?//((?:[a-z0-9-]+\.)+[a-z0-9-]+|\[[0-9a-f:]+\])")
ADDRESS = re.compile(r"(?i)\b(?:https?|wss?|ftps?|sftp|ssh|smb|afp|telnet|gopher)://[^\s'\"<>`)\\]{1,80}")
OWN_ADDRESSES = re.compile(r"^(127\.\d+\.\d+\.\d+|0\.0\.0\.0|100\.64\.0\.0|255\.255\.255\.\d+)$")
NAMESPACES = frozenset(("www.w3.org", "schemas.openxmlformats.org", "www.apple.com"))     # names of file formats, never opened

# what a page could use to send something, to leave Kontor or to build code from text (each with the start of what follows)
_TAGS = "a|div|span|canvas|input|textarea|template|tr|td|th|li|ul|ol|p|b|i|option|button|label|table|tbody|thead|select|section|details|summary|pre|code|h[1-6]" \
        "|svg|g|rect|path|text|tspan|line|circle|ellipse|title|polyline|polygon|defs|clipPath|linearGradient|stop|style"
_ATTRS = r"role|aria-[\w-]+|class|id|x|y|width|height|d|fill|stroke|stroke-[\w-]+|transform|viewBox|title|tabindex|data-[\w-]+|r|cx|cy|x1|x2|y1|y2|rx|ry" \
         r"|points|opacity|type|value|name|for|lang|dir|hidden|disabled|checked|selected|placeholder|colspan|rowspan|draggable|inputmode" \
         r"|autocomplete|autocapitalize|autocorrect|spellcheck|min|max|step|dx|dy|text-anchor|open|readonly|multiple|accept|size|rows|cols|maxlength"
PAGE = re.compile(r"""(?x)
    \blocation\s*(?:\.\s*(?:href|assign|replace)\s*)?(?:=(?![=>])|\()[^;\n]{0,60}
  | (?<![\w.$])open\((?!\s*\))[^;\n]{0,60}
  | \b(?:window|self|top|parent|globalThis|frames|opener)\s*\.\s*open\b[^;\n]{0,60}
  | (?<![=!<>])=\s*open\s*(?:[;,]|$)
  | [\w$.\])]{0,24}\.\s*(?:click|submit|requestSubmit)\s*\(\s*\) | \bdispatchEvent\s*\([^;\n]{0,40}
  | \b(?:Reflect\s*\.\s*\w+|Object\s*\.\s*(?:defineProperty|defineProperties|getOwnPropertyDescriptors?))\b[^;\n]{0,40}
  | \bObject\s*\.\s*assign\s*\([^;\n]{0,80}?\b(?:href|src|srcdoc|ping|formAction|location)\b[^;\n]{0,40}
  | (?<![\w$.'"`-])(?:href|src|srcdoc)\s*:(?!\s*['"`]\#)[^,;}\n]{0,40}
  | \.\s*(?:href|src|action|formAction|srcdoc|ping|srcset)\s*=(?![=>])[^;\n]{0,60}
  | \bsetAttribute(?:NS)?\s*\(\s*(?:null\s*,\s*)?(?!['"`](?:%(attrs)s)['"`]\s*,)[^;\n]{0,60}
  | \b(?:fetch|importScripts)\s*\(\s*['"`](?!/(?!/))[^;\n]{0,60}
  | \b(?:XMLHttpRequest|WebSocket|EventSource|RTCPeerConnection|webkitRTCPeerConnection|RTCDataChannel|sendBeacon|WebTransport|SharedWorker
      |registerProtocolHandler|execScript)\b
  | \bnew\s+(?:Worker|Function)\b | \beval\s*\(
  | \bcreateElement(?:NS)?\s*\(\s*(?:['"`]http://www\.w3\.org/[\w/]+['"`]\s*,\s*)?(?!['"`](?:%(tags)s)['"`]\s*\))[^;\n]{0,40}
  | \b(?:window|self|top|parent|document|globalThis|navigator|location|history|frames)\s*\[[^;\n]{0,40}
  | \bset(?:Timeout|Interval)\s*\(\s*['"`][^;\n]{0,40}
  | \bnavigator\s*\.\s*(?:share|credentials|geolocation|bluetooth|usb|serial|hid)\b
  | <\s*(?:iframe|frame|object|embed|applet|base|portal)\b[^>\n]{0,40}
  | <\s*(?:script|link)\b[^>\n]{0,100}
  | <\s*form\b[^>\n]{0,80}\baction\b[^>\n]{0,40}
  | http-equiv[^>\n]{0,60} | \b(?:dns-prefetch|preconnect|prerender|modulepreload)\b
""" % {"attrs": _ATTRS, "tags": _TAGS})
LEAVING = re.compile(r"\blocation\s*(?:\.\s*\w+\s*)?[=(]|\.\s*href\s*=|\.\s*(?:click|submit|requestSubmit)\s*\(|\bopen\s*\(|=\s*open\b")
STYLE = re.compile(r"""(?x) @import\b[^;\n]{0,60} | \burl\s*\(\s*(?!['"]?(?:/(?!/)|\#|data:image/|data:font/))[^)\n]{0,60} """)
PAGE_FILES = (".js", ".mjs", ".html", ".htm", ".css", ".svg", ".webmanifest", ".xml")
# files that hold no program: read by Kontor as text or shown as a picture
PASSIVE = (".md", ".txt", ".png", ".jpg", ".jpeg", ".gif", ".ico", ".icns", ".json", ".pdf", ".csv")
PASSIVE_NAMES = frozenset(("LICENSE", "NOTICE", "VERSION", "CHANGELOG.md", "README.md", "ROADMAP.md", "CLAUDE.md"))
OWN = frozenset(("updates.py", "update_guard.py"))          # this check: any change to it is shown
# ... and what the rest of the program may use of it (anything else of these two files, touched from outside, is shown)
OWN_OPEN = frozenset(("updates.check", "updates.install", "updates.current_version", "updates.changelog", "updates.installed_date",
                      "updates.plist_path", "updates.LABEL", "updates.schedule_restart"))
# rules that decide where Kontor listens, what its pages may reach, which addresses downloads may use and what the assistant's
# model is shut out of -- no call of their own reaches out, so they are named here (a test keeps the list true)
RULES = {"service.py": ("bind_allowed", "_sec_headers", "_host_ok", "_origin_ok", "_static"),
         "llm_local.py": ("sandbox_profile", "host_allowed", "_safe_join"),
         "security_names.py": ("valid_isin",), "mm_bridge.py": (), "receipts.py": ("external_ok", "inside")}
# functions that look themselves at what they are handed before it reaches out (a fixed program, a fixed address, a path that
# is checked): who calls them cannot make them do anything else, so their callers are not followed. Each is kept as a whole.
CHECKED: Dict[str, Tuple[str, ...]] = {
    "storage.py": ("encrypt", "decrypt", "_kc_read", "_kc_write", "_openssl_run", "_pass_mode"),     # openssl / security with fixed commands; the key goes in as a value (over a pipe)
    "mm_bridge.py": ("_call",),                                           # one fixed script, only the listed commands of MoneyMoney
    "auth.py": ("touchid_verify", "touchid_unseal", "_helper_line"),     # Kontor's own helper; the text is what its window says, the rest base64/hex Kontor made
    "kontor.py": ("service_answers",),                                    # 127.0.0.1 only
    "llm_local.py": ("_open", "_env", "ensure", "install_runtime"),       # allowed hosts only; program and model from Kontor's own lists
    "mm_history.py": ("_wipe", "decrypt_in_place", "_page1_ok", "receive", "MemDB", "keys_from_dialog", "run"),     # the uploaded bytes, in memory
    "core.py": ("_cached", "refresh_accounts"), "model.py": ("ledger_to_bytes", "without_planned"),     # values copied from one of Kontor's objects to another
    "service.py": ("show_in_finder", "open_document", "choose_on_mac", "timemachine_set", "timemachine_status"),     # a path or a line of text
    "updates.py": ("_get",),                                              # allowed hosts only
    "tls_cert.py": ("setup", "renew_if_due", "cert_expiry"),              # Tailscale's own program (found by Kontor), paths in Kontor's data folder
    "security_names.py": ("_post", "lookup"),                             # one fixed address; ISINs only
}
# names every list, text or table has: a call like x.update() says nothing about whose update it is
COMMON = frozenset(n for t in (dict, list, str, set, bytes, tuple, bytearray, frozenset) for n in dir(t)) | frozenset(
    ("read", "write", "close", "open", "flush", "seek", "run", "start", "send", "recv", "put", "wait", "acquire", "release", "is_set"))
SMALL = 40                  # lines: a function of the file whose result goes into such a call is kept whole up to this size
KINDS = ("guard", "rule", "module", "call", "around", "detour", "place", "address", "page", "file", "unreadable")


def installable(rel: str) -> bool:
    """Does an update put this file of the repository into the program folder? (As updates.install copies: not the tests, not
    what starts with a dot, no caches.)"""
    parts = rel.replace("\\", "/").split("/")
    return bool(rel) and not any(p in ("tests", "__pycache__") or p.startswith(".") for p in parts[:-1]) and not parts[-1].startswith(".")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def digest(files: Dict[str, bytes]) -> str:
    """One value for exactly these files and their content (what an approval is given for)."""
    h = hashlib.sha256()
    for rel in sorted(files):
        if installable(rel):
            h.update(rel.encode("utf-8") + b"\0" + hashlib.sha256(files[rel]).digest())
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Python
# ---------------------------------------------------------------------------

def _harmless_module(name: str, local: Set[str]) -> bool:
    return name in HARMLESS or name in HARMLESS_SUB or name.split(".")[0] in local


def _same(node: ast.AST) -> str:
    """The content of a piece of code without its comments, explanations and line numbers."""
    return _sha(ast.dump(node, annotate_fields=False).encode("utf-8"))[:32]


def _show(node: ast.AST, limit: int = 110) -> str:
    try:
        text = " ".join(ast.unparse(node).split())
    except Exception:
        text = type(node).__name__
    return text if len(text) <= limit else text[:limit - 1] + "…"


class _Py:
    """One program file: where it reaches out, and what belongs to those places."""

    def __init__(self, rel: str, tree: ast.Module, local: Set[str]):
        self.rel, self.local = rel, local
        self.tree = tree
        self.nodes: List[ast.AST] = []                        # every piece of the file, walked once (with what it stands in)
        self.parents: Dict[int, ast.AST] = {}
        todo: List[ast.AST] = [tree]
        while todo:
            p = todo.pop()
            self.nodes.append(p)
            body = getattr(p, "body", None)                   # explanations at the start of a function, class or file are no code
            if isinstance(p, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)) and body and isinstance(body[0], ast.Expr) \
                    and isinstance(getattr(body[0], "value", None), ast.Constant) and isinstance(body[0].value.value, str):
                p.body = body[1:] or [ast.Pass()]
            for c in ast.iter_child_nodes(p):
                self.parents[id(c)] = p
                todo.append(c)
        self.chains: List[ast.AST] = [n for n in self.nodes if isinstance(n, (ast.Name, ast.Attribute)) and not isinstance(self.parents.get(id(n)), ast.Attribute)]
        self.out: Dict[Tuple[str, str, str], str] = {}        # (kind, file, what) -> content, to compare
        self.shown: Dict[Tuple[str, str, str], str] = {}      # ... and a line of it to show
        self.bound: Dict[str, str] = {}                       # a name in this file -> the part of Python behind it
        self.risky_names: Set[str] = set()                    # names that stand for something that reaches out
        self.modules: Set[str] = set()                        # names that stand for a whole part of Python (import x)
        self.assigned: Set[str] = {n.id for n in self.nodes if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store)} | {
            a.arg for n in self.nodes if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)) for a in n.args.args + n.args.kwonlyargs}
        self.heads: Dict[int, str] = {}
        self._imports()
        self._aliases()
        self.hits: Dict[int, List[Tuple[ast.AST, str, str]]] = {}     # id of the unit (function, or statement outside one) -> finds
        self.units: Dict[int, Tuple[ast.AST, str]] = {}
        self.tops: Dict[str, List[ast.stmt]] = {}             # names set at the top of the file
        self.defs: Dict[str, List[ast.AST]] = {}              # functions of this file by name (also those inside classes)
        self.methods: Set[int] = set()                        # ... those that belong to a class
        for st in self.tree.body:
            for t in (st.targets if isinstance(st, ast.Assign) else [st.target] if isinstance(st, (ast.AnnAssign, ast.AugAssign)) else []):
                for nm in ast.walk(t):
                    if isinstance(nm, ast.Name):
                        self.tops.setdefault(nm.id, []).append(st)
        for n in self.nodes:
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self.defs.setdefault(n.name, []).append(n)
                if isinstance(self.parents.get(id(n)), ast.ClassDef):
                    self.methods.add(id(n))
        self.passing: Dict[int, Tuple[str, List[str], Set[str], bool]] = {}     # functions that hand what they are given on to such a
        self.deciding: Dict[int, List[ast.AST]] = {}          # place: (name, what they take, which of it goes there, takes more)
        self.seen_refs: Set[Tuple[int, int]] = set()
        self._find()

    # -- what is imported -------------------------------------------------------------------------------------------------
    def _note(self, kind: str, what: str, content: str = "1", show: str = "") -> None:
        key = (kind, self.rel, what)
        if key not in self.out:
            self.out[key] = content
        elif content not in self.out[key].split("+"):          # (the same thing reached from two places is still one thing)
            self.out[key] = "+".join(sorted(self.out[key].split("+") + [content]))
        self.shown.setdefault(key, show or what)

    def _imports(self) -> None:
        for n in self.nodes:
            if isinstance(n, ast.Import):
                for a in n.names:
                    self.bound[a.asname or a.name.split(".")[0]] = a.name if a.asname else a.name.split(".")[0]
                    self.modules.add(a.asname or a.name.split(".")[0])
                    if not _harmless_module(a.name, self.local):
                        self._note("module", a.name, show="import " + a.name)
            elif isinstance(n, ast.ImportFrom):
                mod = ("." * n.level) + (n.module or "")
                if n.level and not n.module:
                    continue
                for a in n.names:
                    self.bound[a.asname or a.name] = "%s.%s" % (mod, a.name)
                    full = "%s.%s" % (mod, a.name)
                    if a.name == "*" or not (_harmless_module(mod, self.local) or _harmless_module(full, self.local)) or self._risky_path(full):
                        self._note("module", full, show="from %s import %s" % (mod, a.name))

    # -- is this dotted name something that reaches out? ------------------------------------------------------------------
    def _risky_path(self, path: str) -> bool:
        parts = path.split(".")
        if PLAIN.match(path):
            return False
        for i in range(len(parts), 0, -1):                     # the longest known part of Python at its start
            mod = ".".join(parts[:i])
            if mod in RISKY_IN and len(parts) > i and parts[i] in RISKY_IN[mod]:
                return True
            if _harmless_module(mod, self.local):
                rest = parts[i:]
                return any(p in MODULE_NAMES or p in INSIDES or p in INSIDES_OF_MODULES for p in rest)
        return True                                            # not a harmless part at all

    def _chain(self, node: ast.AST) -> Tuple[Optional[str], List[str]]:
        parts: List[str] = []
        while isinstance(node, ast.Attribute):
            parts.append(node.attr)
            node = node.value
        return (node.id if isinstance(node, ast.Name) else None), list(reversed(parts))

    def _risk(self, node: ast.AST) -> Optional[Tuple[str, str]]:
        """(kind, what) when this name or dotted name reaches out, else None. Only the outermost of a.b.c is asked."""
        root, parts = self._chain(node)
        inside = [p for p in parts if p in INSIDES]
        if inside:
            return "detour", inside[0]
        if root is None:
            hidden = [p for p in parts if p in MODULE_NAMES]
            return ("detour", hidden[0]) if hidden else None
        if root in self.risky_names:
            up = self.parents.get(id(node))
            if not parts and isinstance(up, ast.Return) and any(isinstance(b, ast.ClassDef) and b.name == root for b in getattr(self.parents.get(id(up)), "body", [])):
                return None                                    # a function handing out the class it has just built (its first line is kept)
            return "call", ".".join([root] + parts)
        if root in self.bound:
            path = ".".join([self.bound[root]] + parts)
            if path.startswith("."):
                return None
            if not parts and root in self.modules and self.bound[root].split(".")[0] not in self.local:
                return "detour", root                          # a part of Python handed on as a value (f(os), x = os)
            own = path.split(".")[0] + ".py"
            if own in OWN and self.rel not in OWN and ".".join(path.split(".")[:2]) not in OWN_OPEN:
                return "detour", path                          # the update check, touched from outside
            if isinstance(getattr(node, "ctx", None), (ast.Store, ast.Del)) and parts and (root in self.modules or path.split(".")[0] in self.local):
                return "detour", path + " ="                   # something of another part of the program replaced from outside
            if self._risky_path(path):
                plain = _harmless_module(self.bound[root], self.local) or _harmless_module(self.bound[root].split(".")[0], self.local)
                listed = any(path == m + "." + x or path.startswith(m + "." + x + ".") for m in RISKY_IN for x in RISKY_IN[m])
                return ("detour" if plain and not listed else "call"), path
            return None
        if root in BUILTINS and not parts:
            if root in ("getattr", "setattr", "delattr"):
                call = self.parents.get(id(node))
                if isinstance(call, ast.Call) and call.func is node and len(call.args) >= 2 and isinstance(call.args[1], ast.Constant) \
                        and isinstance(call.args[1].value, str) and call.args[1].value not in INSIDES and call.args[1].value not in MODULE_NAMES \
                        and not self._names_module(call.args[0]):
                    return None                                # getattr(x, "a fixed, harmless name")
                if isinstance(call, ast.Call) and call.func is node and root == "getattr" and len(call.args) >= 2 and isinstance(call.args[0], ast.Name) \
                        and call.args[0].id == "self" and isinstance(call.args[1], ast.BinOp) and isinstance(call.args[1].op, ast.Add) \
                        and isinstance(call.args[1].left, ast.Constant) and isinstance(call.args[1].left.value, str) \
                        and re.fullmatch(r"[a-z][a-z0-9]*_", call.args[1].left.value):
                    return None                                # getattr(self, "t_" + name): one of its own methods with that beginning
            if root == "memoryview" or root == "input":
                return None
            return "detour", root
        hidden = [p for p in parts if p in MODULE_NAMES]
        if hidden and root not in ("self", "cls"):
            return "detour", "%s.%s" % (root, ".".join(parts))
        if root in MODULE_NAMES and root not in self.assigned:
            return "detour", root                              # a part of Python by its name, though this file does not import it
        return None

    def _names_module(self, node: ast.AST) -> bool:
        root, parts = self._chain(node)
        return root is not None and (root in self.bound and not self.bound[root].startswith(".") or root in MODULE_NAMES or root in self.risky_names)

    def _aliases(self) -> None:
        """Other names for what reaches out: a class built on such a part, a name such a part is put into (x = subprocess.run)."""
        changed = True
        while changed:
            changed = False
            for n in self.nodes:
                name = None
                if isinstance(n, ast.ClassDef) and any(self._risk(b) for b in n.bases):
                    name = n.name
                elif isinstance(n, (ast.Assign, ast.AnnAssign, ast.NamedExpr)) and isinstance(n.value, (ast.Name, ast.Attribute)) and self._risk(n.value):
                    t = n.targets[0] if isinstance(n, ast.Assign) else n.target
                    name = t.id if isinstance(t, ast.Name) else (t.attr if isinstance(t, ast.Attribute) else None)
                if name and name not in self.risky_names:
                    self.risky_names.add(name)
                    changed = True

    # -- where -----------------------------------------------------------------------------------------------------------
    def _unit(self, node: ast.AST) -> Tuple[ast.AST, str]:
        """What a place belongs to, with its name: the function around it (of functions inside functions the outermost); in the
        first line of a function or class (bases, decorators, defaults) that line; outside any function the statement itself."""
        unit: Optional[ast.AST] = None
        child: ast.AST = node
        n = self.parents.get(id(node))
        stmt: Optional[ast.AST] = node if isinstance(node, ast.stmt) else None
        while n is not None and unit is None:
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if not any(child is b for b in n.body):                    # in its first line
                    head = ast.Tuple(elts=[x for x in ast.iter_child_nodes(n) if not any(x is b for b in n.body)], ctx=ast.Load())
                    self.parents[id(head)] = n
                    self.heads[id(head)] = n.name
                    unit = head
                elif isinstance(n, ast.ClassDef):
                    unit = stmt if stmt is not None else child
                else:
                    unit = n
                    up = self.parents.get(id(n))
                    while isinstance(up, (ast.FunctionDef, ast.AsyncFunctionDef, ast.If, ast.Try, ast.With, ast.For, ast.While)):
                        if isinstance(up, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            unit = up
                        up = self.parents.get(id(up))
                break
            if isinstance(n, ast.Module):
                unit = stmt if stmt is not None else child
                break
            if isinstance(n, ast.stmt):
                stmt = n
            child, n = n, self.parents.get(id(n))
        if unit is None:
            unit = stmt if stmt is not None else node
        names: List[str] = [self.heads[id(unit)] + " (…)"] if id(unit) in self.heads else []
        up = unit if isinstance(unit, (ast.FunctionDef, ast.AsyncFunctionDef)) else self.parents.get(id(unit))
        while up is not None:
            if isinstance(up, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and not (names and id(unit) in self.heads and up.name == self.heads[id(unit)] and len(names) == 1):
                names.append(up.name)
            up = self.parents.get(id(up))
        return unit, ".".join(reversed(names))

    def _find(self) -> None:
        notes: Set[int] = set()                                # what only says of which kind a value is (x: Optional[ssl.SSLContext])
        for n in [x for x in self.nodes if isinstance(x, (ast.AnnAssign, ast.arg, ast.FunctionDef, ast.AsyncFunctionDef))]:
            for a in ([n.annotation] if isinstance(n, (ast.AnnAssign, ast.arg)) and n.annotation is not None else []) + (
                    [n.returns] if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.returns is not None else []):
                notes.update(id(x) for x in ast.walk(a))
        for n in self.chains:                                  # (of a.b.c only the whole is asked)
            if id(n) not in notes:
                r = self._risk(n)
                if r:
                    self._hit(n, r[0], r[1])
        for n in self.nodes:
            if id(n) in notes or isinstance(n, (ast.Name, ast.Attribute)):
                continue
            if isinstance(n, ast.Global):
                self._hit(n, "detour", "global " + ", ".join(n.names))
            elif isinstance(n, ast.Constant) and isinstance(n.value, str):
                self._text(n)
            elif isinstance(n, ast.Subscript) and isinstance(n.slice, ast.Constant) and isinstance(n.slice.value, str) \
                    and (n.slice.value in INSIDES or n.slice.value in MODULE_NAMES):
                self._hit(n, "detour", "[%r]" % n.slice.value)

    def _hit(self, node: ast.AST, kind: str, what: str, given: Optional[List[ast.AST]] = None) -> None:
        unit, qual = self._unit(node)
        self.units[id(unit)] = (unit, qual)
        self.hits.setdefault(id(unit), []).append((node, kind, what))
        self.deciding[id(node)] = given if given is not None else self._deciding(node, what)

    def _deciding(self, node: ast.AST, path: str) -> List[ast.AST]:
        """Of a call that reaches out: the parts that decide where it goes or what is started (the program and its arguments, the
        address) -- not what is merely sent along to a fixed place (the text given to a program, the content of a request,
        a time limit). Not a call (the name alone, handed on or kept): the whole statement."""
        call = self.parents.get(id(node))
        if not (isinstance(call, ast.Call) and call.func is node):
            top = node
            while id(top) in self.parents and not isinstance(top, ast.stmt):
                top = self.parents[id(top)]
            return [top]
        plain = ("timeout", "input", "capture_output", "text", "stdout", "stderr", "stdin", "check", "encoding", "errors", "close_fds",
                 "start_new_session", "bufsize", "universal_newlines")
        args, kws = list(call.args), [k for k in call.keywords if k.arg not in plain]
        if path.startswith("subprocess."):
            args = args[:1]
        elif path.startswith("urllib.request.") and path.rsplit(".", 1)[-1] in ("Request", "urlopen"):
            args, kws = args[:1], [k for k in kws if k.arg not in ("data", "method")]
        return args + [k.value for k in kws]

    def _text(self, node: ast.Constant) -> None:
        s = node.value
        for a in ADDRESS.findall(s):
            m = HOST.search(a)
            host = (m.group(1) if m else a).lower()
            if host not in NAMESPACES and not OWN_ADDRESSES.match(host) and host != "localhost":
                self._note("address", host, show=a[:80])
        m = PLACES.search(s)
        if m:
            self._hit(node, "place", m.group(0))

    # -- what reaches a place ------------------------------------------------------------------------------------------------
    def _feeding(self, unit: ast.AST, nodes: List[ast.AST], exact: bool = False) -> Tuple[List[ast.AST], Set[str]]:
        """The expressions of a function that reach these places of it, and the names in them: the statements the places stand
        in (exact: just these expressions), and what is put into the names they use (again and again)."""
        feeding: List[ast.AST] = []
        for node in nodes:
            top = node
            while not exact and id(top) in self.parents and not isinstance(top, ast.stmt):
                top = self.parents[id(top)]
            feeding.append(top)
        names = {n.id for st in feeding for n in ast.walk(st) if isinstance(n, ast.Name)}
        seen: Set[int] = set()
        grown = True
        while grown:
            grown = False
            for st in ast.walk(unit):
                targets = st.targets if isinstance(st, ast.Assign) else [st.target] if isinstance(st, (ast.AnnAssign, ast.AugAssign, ast.For, ast.NamedExpr)) else \
                    [i.optional_vars for i in st.items if i.optional_vars is not None] if isinstance(st, ast.With) else []
                if id(st) not in seen and any(isinstance(x, ast.Name) and x.id in names for t in targets for x in ast.walk(t)):
                    seen.add(id(st))
                    feeding.append(st.value if isinstance(st, (ast.Assign, ast.AnnAssign, ast.AugAssign, ast.NamedExpr)) and st.value is not None else
                                   st.iter if isinstance(st, ast.For) else st)
                    more = {n.id for n in ast.walk(feeding[-1]) if isinstance(n, ast.Name)} - names
                    if more:
                        names |= more
                        grown = True
        return feeding, names

    def pass_on(self) -> bool:
        """Marks the functions that hand something they are given on to where a call that reaches out is decided (so whoever
        calls them decides what is started or where it goes). True when something was added. Functions listed as CHECKED look
        at what they are given themselves."""
        added = False
        for uid, found in self.hits.items():
            unit, qual = self.units[uid]
            if not isinstance(unit, (ast.FunctionDef, ast.AsyncFunctionDef)) or id(unit) in self.heads or unit.name in CHECKED.get(self.rel, ()):
                continue
            exprs = [e for n, k, _w in found if k != "place" for e in self.deciding.get(id(n), [])]
            if not exprs:
                continue
            _feed, names = self._feeding(unit, exprs, exact=True)
            a = unit.args
            given = [x.arg for x in a.posonlyargs + a.args]
            if uid in self.methods and given and given[0] in ("self", "cls"):
                given = given[1:]
            every = given + [x.arg for x in a.kwonlyargs] + [x.arg for x in (a.vararg, a.kwarg) if x]
            goes = {g for g in every if g in names}
            old = self.passing.get(uid)
            if goes and (old is None or not goes <= old[2]):
                name = unit.name
                if name == "__init__" and isinstance(self.parents.get(id(unit)), ast.ClassDef):
                    name = self.parents[id(unit)].name         # called by the name of its class
                    if name in CHECKED.get(self.rel, ()):
                        continue
                self.passing[uid] = (name, given, goes | (old[2] if old else set()), bool(a.vararg and a.vararg.arg in goes) or bool(a.kwarg and a.kwarg.arg in goes))
                added = True
        return added

    def refer(self, passing: Dict[str, Dict[str, list]], methods: Dict[str, list]) -> bool:
        """Finds where this file uses a function (of any file) that hands things on -- by its name here, as module.name, as
        .name() of an object -- and which of what it is called with goes on. True when a new place was found."""
        added = False
        mine = passing.get(self.rel, {})
        for n in self.chains:
            root, parts = self._chain(n)
            what, defs = None, []
            if root is not None and not parts and root in mine and isinstance(n.ctx, ast.Load):
                what, defs = root, mine[root]
            elif root in self.bound and not self.bound[root].startswith("."):
                path = (self.bound[root] + "." + ".".join(parts)).rstrip(".").split(".")
                if len(path) >= 2 and path[1] in passing.get(path[0] + ".py", {}):
                    what, defs = "%s.%s" % (path[0], path[1]), passing[path[0] + ".py"][path[1]]
            if what is None and parts and parts[-1] in methods and not (root in self.bound):
                what, defs = "." + parts[-1], methods[parts[-1]]
            if not what:
                continue
            call = self.parents.get(id(n))
            if isinstance(call, ast.Call) and call.func is n:
                exprs: List[ast.AST] = []
                for _name, given, goes, more in defs:
                    for i, x in enumerate(call.args):
                        if isinstance(x, ast.Starred) or i >= len(given) and more or i < len(given) and given[i] in goes:
                            exprs.append(x)
                    exprs += [k.value for k in call.keywords if k.arg is None or k.arg in goes or more]
            else:
                exprs = [self._deciding(n, "")[0]]
            key = (id(n), len(exprs))
            if key in self.seen_refs:
                continue
            self.seen_refs.add(key)
            if id(n) in self.deciding:
                self.deciding[id(n)] = exprs                   # the same place, more of it goes on now
            else:
                self._hit(n, "call", "→ " + what, exprs)
            added = True
        return added

    # -- what is kept for comparing -----------------------------------------------------------------------------------------
    def record(self) -> None:
        tops, defs = self.tops, self.defs
        around: Set[int] = set()
        for uid, found in self.hits.items():
            unit, qual = self.units[uid]
            kinds = sorted({k for _n, k, _w in found})
            kind = "detour" if "detour" in kinds else "place" if kinds == ["place"] else "call"
            first = min(found, key=lambda f: (getattr(f[0], "lineno", 0), getattr(f[0], "col_offset", 0)))
            call = first[0]
            while isinstance(self.parents.get(id(call)), (ast.Attribute, ast.Call)) and getattr(self.parents[id(call)], "func", call) is call:
                call = self.parents[id(call)]
            if id(unit) in self.heads:
                self._note(kind, qual, _same(unit), "%s: %s" % (qual, _show(call, 90)))
            elif isinstance(unit, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._note(kind, qual, _same(unit), "%s: %s" % (qual, _show(call, 90)))
                # what reaches those places from outside the function: names set at the top of the file and small functions of
                # the file whose result goes into them (directly, or through a name of the function) ...
                feeding, names = self._feeding(unit, [n for n, _k, _w in found])
                # ... and what decides whether they are reached at all (if bind_allowed(x): ..., if ext in DOCUMENTS: ...)
                tests = [n.test for n in ast.walk(unit) if isinstance(n, (ast.If, ast.While, ast.IfExp, ast.Assert))]
                names |= {n.id for t in tests for n in ast.walk(t) if isinstance(n, ast.Name)}
                for name in sorted(names):
                    if name in tops and name not in ("log", "logger"):
                        for st in tops[name]:
                            self._note("around", name, _same(st), _show(st))
                feeding += tests
                todo = list(feeding)
                while todo:
                    st = todo.pop()
                    for n in ast.walk(st):
                        callee = n.func if isinstance(n, ast.Call) else None
                        name = callee.id if isinstance(callee, ast.Name) else callee.attr if isinstance(callee, ast.Attribute) else None
                        if name in defs and not (isinstance(callee, ast.Attribute) and self._chain(callee)[0] in self.bound):
                            for d in defs[name]:
                                if d is not unit and id(d) not in self.hits and id(d) not in around and d.end_lineno - d.lineno < SMALL:
                                    around.add(id(d))
                                    self._note("around", name + "()", _same(d), "%s() → %s" % (name, qual))
                                    todo.append(d)             # and the small functions that one calls in turn
                                    for x in ast.walk(d):      # ... with the names from the top of the file it uses
                                        if isinstance(x, ast.Name) and x.id in tops and x.id not in ("log", "logger"):
                                            for st2 in tops[x.id]:
                                                self._note("around", x.id, _same(st2), _show(st2))
            else:
                self._note(kind, (qual + " " if qual else "") + _show(unit, 200), show=_show(call if kind != "place" else unit, 100))
        for name in RULES.get(self.rel, ()):                   # rules that keep Kontor to itself: each as a whole
            for d in defs.get(name, []):
                self._note("rule", name, _same(d), "%s()" % name)
        if self.rel in OWN:
            self._note("guard", "", _same(self.tree), self.rel)


def _analyse(files: Dict[str, bytes], names: List[str], local: Set[str]) -> Tuple[List[_Py], List[str], List[str]]:
    """The program files read and followed through: (each file, the files no reader of Python understands, methods that hand
    things on but have a name every list or text has -- those cannot be followed)."""
    parsed: List[_Py] = []
    unreadable: List[str] = []
    common: List[str] = []
    for rel in names:
        try:
            parsed.append(_Py(rel, ast.parse(files[rel].decode("utf-8")), local))
        except (SyntaxError, ValueError, UnicodeDecodeError, RecursionError, MemoryError):
            unreadable.append(rel)
    # a function that hands what it is given on to a place that reaches out: whoever uses it is such a place too -- in any
    # file, and so on, until nothing new is found
    for _ in range(40):
        grown = [p.pass_on() for p in parsed]
        passing: Dict[str, Dict[str, list]] = {}
        methods: Dict[str, list] = {}
        common = []
        for p in parsed:
            for uid, entry in p.passing.items():
                unit = p.units[uid][0]
                if uid in p.methods and getattr(unit, "name", "") != "__init__":
                    if entry[0] not in COMMON:                 # .get(), .update() ...: any object has them (a test keeps such names out)
                        methods.setdefault(entry[0], []).append(entry)
                    else:
                        common.append("%s: %s" % (p.rel, entry[0]))
                else:
                    passing.setdefault(p.rel, {}).setdefault(entry[0], []).append(entry)
        found = [p.refer(passing, methods) for p in parsed]
        if not any(grown) and not any(found):
            break
    return parsed, unreadable, common


def _python(files: Dict[str, bytes], names: List[str], local: Set[str], out: dict, shown: dict) -> None:
    parsed, unreadable, _common = _analyse(files, names, local)
    for rel in unreadable:
        out[("unreadable", rel, "")] = _sha(files[rel])
        shown[("unreadable", rel, "")] = rel
    for p in parsed:
        p.record()
        out.update(p.out)
        shown.update(p.shown)


def handing_on(files: Dict[str, bytes]) -> Dict[str, object]:
    """For looking at the program as it is (tests): which functions hand what they are given on to a place that reaches out
    ({file: {name: [what of it]}}), and which of them cannot be followed because of their name."""
    names = sorted(r for r in files if installable(r) and r.lower().endswith(".py"))
    parsed, _unreadable, common = _analyse(files, names, _local(names))
    return {"functions": {p.rel: {e[0]: sorted(e[2]) for e in p.passing.values()} for p in parsed if p.passing}, "common": sorted(common),
            "names": {p.rel: sorted(p.defs) + sorted(n.name for n in p.nodes if isinstance(n, ast.ClassDef)) for p in parsed}}


def _local(names: Iterable[str]) -> Set[str]:
    """The program's own parts by the name they are imported with."""
    return {r.split("/")[0][:-3] if "/" not in r else r.split("/")[0] for r in names if r.endswith(".py")}


# ---------------------------------------------------------------------------
# pages and everything else
# ---------------------------------------------------------------------------

def _page(rel: str, data: bytes, out: dict, shown: dict) -> None:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        out[("unreadable", rel, "")] = _sha(data)
        shown[("unreadable", rel, "")] = rel
        return
    for a in ADDRESS.findall(text):
        m = HOST.search(a)
        host = (m.group(1) if m else a).lower()
        if host not in NAMESPACES and not OWN_ADDRESSES.match(host) and host != "localhost":
            out[("address", rel, host)] = "1"
            shown[("address", rel, host)] = a[:80]
    for m in re.finditer(r"""(?i)['"`(=\s](//(?:[a-z0-9-]+\.)+[a-z]{2,}[^\s'"`)]{0,40})""", text):       # an address without "https:"
        out[("address", rel, m.group(1).lower())] = "1"
        shown[("address", rel, m.group(1).lower())] = m.group(1)[:80]
    low = rel.lower()
    found: List[str] = []
    if not low.endswith(".css"):                               # (a style sheet runs nothing)
        for m in PAGE.finditer(text):
            hit = m.group(0)
            if LEAVING.search(hit):                            # where a page leaves or clicks: the whole line, with what guards it
                start, end = text.rfind("\n", 0, m.start()) + 1, text.find("\n", m.end())
                hit = text[start:end if end >= 0 else len(text)].strip()[:600]
            found.append(hit)
    if not low.endswith((".js", ".mjs")):
        found += [m.group(0) for m in STYLE.finditer(text)]
    for hit in found:
        s = " ".join(hit.split())
        key = ("page", rel, s)
        out[key] = str(int(out.get(key, "0")) + 1)
        shown[key] = s[:110]


def scan(files: Dict[str, bytes]) -> Tuple[Dict[Tuple[str, str, str], str], Dict[Tuple[str, str, str], str]]:
    """What a set of program files holds of the things named above: ({(kind, file, what): content}, {the same: a line to show})."""
    out: Dict[Tuple[str, str, str], str] = {}
    shown: Dict[Tuple[str, str, str], str] = {}
    names = [r for r in files if installable(r)]
    local = _local(names)
    _python(files, sorted(r for r in names if r.lower().endswith(".py")), local, out, shown)
    for rel in sorted(names):
        data, low, base = files[rel], rel.lower(), rel.rsplit("/", 1)[-1]
        if low.endswith(".py"):
            continue
        elif low.endswith(PAGE_FILES):
            _page(rel, data, out, shown)
        elif low.endswith(PASSIVE) or base in PASSIVE_NAMES:
            continue
        else:                                                  # a helper in Swift, a script, anything Kontor cannot read this way
            out[("file", rel, "")] = _sha(data)
            shown[("file", rel, "")] = rel
    return out, shown


def compare(old_files: Dict[str, bytes], new_files: Dict[str, bytes], limit: int = 200) -> List[Dict[str, str]]:
    """What the new files hold of those things that the old ones do not hold the same way: [{kind, file, what, new}] -- "new":
    it was not there at all (else: it is changed). Empty: nothing to ask about."""
    return differences(scan(old_files)[0], scan(new_files), set(new_files), limit)


def differences(old: Dict[Tuple[str, str, str], str], scanned: tuple, new_files: Set[str], limit: int = 200) -> List[Dict[str, str]]:
    new, shown = scanned
    known = {k[2] for k in old if k[0] == "address"}           # an address the program names already, written in another file too
    found: List[Dict[str, str]] = []
    for key in sorted(new, key=lambda k: (KINDS.index(k[0]) if k[0] in KINDS else 99, k[1], k[2])):
        if old.get(key) == new[key]:
            continue
        kind, rel, what = key
        if kind == "page" and key in old and int(new[key]) <= int(old[key]):
            continue                                           # the same line fewer times
        if kind == "address" and what in known:
            continue
        found.append({"kind": kind, "file": rel, "what": shown.get(key, "")[:160], "new": key not in old})
    for key in sorted(old):                                    # a rule that is no longer there
        if key[0] == "rule" and key not in new and (key[1] in new_files):
            found.insert(0, {"kind": "rule", "file": key[1], "what": key[2] + "()", "new": False, "gone": True})
    return found[:limit]


def summary(found: Iterable[Dict[str, str]]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for f in found:
        out[f["kind"]] = out.get(f["kind"], 0) + 1
    return out
