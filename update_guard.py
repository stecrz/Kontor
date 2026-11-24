"""Before an update is installed: what could the new version do that the installed one cannot?

The installed version reads the files of the new one -- without running any of them -- and compares what both hold of the
things that let a program reach beyond itself:
  - parts of Python outside a list of harmless ones (network, starting programs, loading code, anything unknown);
  - every function that calls such a part, as a whole (so what is handed to the call counts too), the names it uses from its
    file and the functions of its file it calls; ways around a plain call (reaching a module through another one, looking
    names up as text, the insides of Python);
  - Internet addresses written anywhere in the program or its pages, and places on a Mac from which other programs are
    started (LaunchAgents, shell profiles ...) -- also put together from pieces ('Launch' + 'Agents');
  - writing into the program's own folder (a program that changes its own files);
  - what a page could use to send something or to leave Kontor (the pages' security rules are part of the program above);
  - files Kontor cannot read this way (helpers in Swift, scripts, anything that is no text, picture or page) -- of helpers
    and scripts their lines without comments and empty space, with how many lines change and whether calls to the outside
    are among them;
  - files that take the place of a part of the program or of Python (a folder named like a part, a name that differs only
    in its letters' case), or that Python loads by itself;
  - rules that keep Kontor to itself: where it listens, who may install an update and with whose approval, where updates
    and the assistant's downloads come from and that they are checked;
  - the two files of this check themselves -- a change to the check is always shown, since it decides about the update
    after it;
  - in a git clone, where the whole repository arrives and not only the program: every file of it that is no part of the
    program and no ordinary file of its tests and development (ready-made programs, caches, helpers' folders).
Nothing new or changed among these: the update is installed as before, without a word. Each finding is then judged (judge):
critical -- a new or further way out, a looser shield, a file that arrives unread, a change of the check itself; review -- what
goes out over a way there is already is put together differently; plain -- a rule that is only stricter, or one of the
internet search behind its card (RULE_GROUPS). Only plain findings: installed as before, the settings name them in one quiet
line. Otherwise it waits, and the settings show what was found -- each entry in plain words, what it can do, and its lines
-- an update is then installed only after you have seen that and said so. What is not known as less is critical.

This narrows the way for a change slipped into the repository; it cannot close it (a program can be rebuilt in ways no
reader of its text foresees). Only what is new or changed is named, never what the installed version already does.
"""
from __future__ import annotations

import ast
import base64
import binascii
import difflib
import fnmatch
import hashlib
import re
import unicodedata
from collections import Counter
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
# ... by how the name begins rather than a list: every way of os to start or become another program, also those meant for
# Python itself (os._execvpe, os._spawnvef) and those of a later Python
RISKY_START = {"os": re.compile(r"_*(?:exec|spawn|fork|posix_spawn|popen|system|startfile)")}
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
# ... the same behind a part of Python that keeps the builtins under a name of its own (tarfile.bltn.exec)
CODE_NAMES = BUILTINS - frozenset(("memoryview", "input"))
# kinds of values every Python has: their table of names leads to everything (type.__dict__[...])
TYPE_NAMES = frozenset("""type object str bytes bytearray int float complex bool dict list tuple set frozenset range slice property classmethod
staticmethod super BaseException Exception""".split())
# an attribute read through a name that is fine: the errors and constants of the parts that reach out
PLAIN = re.compile(r"^(subprocess\.(TimeoutExpired|CalledProcessError|SubprocessError|CompletedProcess|PIPE|DEVNULL|STDOUT)"
                   r"|socket\.(timeout|error|gaierror|herror|SHUT_RDWR)|ssl\.(SSLError|CertificateError|SSLSocket)|http\.client\.(HTTPException|IncompleteRead|HTTPResponse)"
                   r"|os\.environ\.get|os\._exit|sys\.(argv|exit|stdin\.isatty)|sqlite3\.(Error|DatabaseError|OperationalError))$")

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
  | [\w$\])]\s*\.\s*(?:click|submit|requestSubmit)\s*(?:[;),\]}]|\.\s*(?:call|apply|bind)\b)[^;\n]{0,40}
  | \blocation\s*\.\s*(?:assign|replace)\b(?!\s*\()[^;\n]{0,60}
  | [\w$\])]\s*(?:\?\.\s*)?\[[^\]\n]{1,60}\]\s*(?:\?\.\s*)?(?:\(|\.\s*(?:call|apply|bind)\b)[^;\n]{0,40}
  | (?:(?<![=!<>])=(?![=>])|[(,\[?:]|\breturn\b|=>)\s*(?:(?:window|self|globalThis|document|top|parent)\s*\.\s*)*
      (?:location|window|document|globalThis|navigator|defaultView)\s*(?=[;,)\]}\n?:]|$)
  | (?<![\w$.])import\s*\([^;\n]{0,40}
  | /api/update/install[^;\n]{0,80}
  | (?:(['"`])approved\1|\bapproved\s*:|\.\s*approved\b|[{,]\s*approved\s*[,}]|\bapproved\s*=(?!=))[^;\n]{0,60}
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
LEAVING = re.compile(r"\blocation\s*(?:\.\s*\w+\s*)?[=(]|\.\s*href\s*=|\.\s*(?:click|submit|requestSubmit)\s*\(|\bopen\s*\(|=\s*open\b"
                     r"|/api/update/install|\bapproved\b")
# pieces of text put together on a page ('htt' + 'ps://'): joined before addresses are looked for
JS_JOIN = re.compile(r"""(['"`])((?:\\.|(?!\1)[^\\\n])*)\1\s*\+\s*(['"`])((?:\\.|(?!\3)[^\\\n])*)\3""")
STYLE = re.compile(r"""(?x) @import\b[^;\n]{0,60} | \burl\s*\(\s*(?!['"]?(?:/(?!/)|\#|data:image/|data:font/))[^)\n]{0,60} """)
PAGE_FILES = (".js", ".mjs", ".html", ".htm", ".css", ".svg", ".webmanifest", ".xml")
# files that hold no program: read by Kontor as text or shown as a picture
PASSIVE = (".md", ".txt", ".png", ".jpg", ".jpeg", ".gif", ".ico", ".icns", ".json", ".pdf", ".csv")
PASSIVE_NAMES = frozenset(("LICENSE", "NOTICE", "VERSION", "CHANGELOG.md", "README.md", "ROADMAP.md", "CLAUDE.md"))
OWN = frozenset(("updates.py", "update_guard.py"))          # this check: any change to it is shown
# ... and what the rest of the program may use of it (anything else of these two files, touched from outside, is shown)
# (updates.install is not among them: it is used in one small function of the service, a rule below -- anywhere else it is shown)
OWN_OPEN = frozenset(("updates.check", "updates.current_version", "updates.changelog", "updates.installed_date",
                      "updates.plist_path", "updates.LABEL", "updates.schedule_restart"))
# rules that decide where Kontor listens, what its pages may reach, which addresses downloads may use and what the assistant's
# model is shut out of -- no call of their own reaches out, so they are named here (a test keeps the list true)
RULES = {"service.py": ("bind_allowed", "_sec_headers", "_host_ok", "_origin_ok", "_static"),
         # the assistant's internet search (a name set at the top of a file counts like a function: the fixed lists and patterns
         # such a rule goes by) -- where its reader may connect (the hosts named, redirects, no address of this Mac or the local
         # network) ...
         "web_reader.py": ("host_ok", "public", "global_address", "inner_addresses", "NAT64", "NAT64_LOCAL", "redirect_request"),
         # ... what Kontor keeps back of your own data and how it compares it, what each source is asked and on which hosts, which
         # websites count as yours, what the reader process is shut out of ...
         "web_search.py": ("privacy_problem", "_own_in", "_not_plain", "_fold", "_name_tokens", "_readings", "_figure", "_iban", "_lei_ok", "own_index",
                           "_INVISIBLE", "_LETTERS", "_SIGNS", "_BASE", "_PERCENT", "LEGAL", "GENERIC", "IBAN_LENGTH", "_IBAN_RUN", "_CODE", "_NO_AMOUNT",
                           "_NO_FIGURES", "_PERIOD", "_NUMBER", "_YEAR", "_RUN", "_CHAIN", "_LEET", "_PLAIN_LEAST",
                           "prepare", "prepare_read", "_q", "_month", "_since", "_last", "_req", "link_hits", "user_agent", "NEUTRAL_AGENT",
                           "SOURCES", "LINK_HOSTS", "FEEDS", "_SERIES", "_DATASET", "_LEI", "_QID",
                           "site", "_ace", "trusted", "trusted_site", "trusted_default", "SHARED", "_SECOND", "HOSTS_MAX",
                           "reader_profile", "command", "python_exe", "READER", "SANDBOX", "HERE",
                           # ... a question to Claude (Anthropic's interface): the text of its POST (on the card, whole), what the reader
                           # is handed beside it, that it is asked every time, and that a page it names is a page on any website
                           "claude_body", "CLAUDE_MODELS", "CLAUDE_TOKENS", "CLAUDE_SEARCHES", "CLAUDE_QUESTION", "CLAUDE_SYSTEM",
                           "claude_request", "CLAUDE_URL", "CLAUDE_SECONDS", "CLAUDE_BYTES", "CLAUDE_SAID", "ASKED_ALWAYS", "ANYWHERE"),
         # ... and in the assistant: the index it is checked against, what goes without a card, no change once web text is there
         "assistant.py": ("_own", "_trusted", "_propose"),
         "llm_local.py": ("sandbox_profile", "host_allowed", "_safe_join"),
         "security_names.py": ("valid_isin",), "mm_bridge.py": (), "receipts.py": ("external_ok", "inside")}
# functions that look themselves at what they are handed before it reaches out (a fixed program, a fixed address, a path that
# is checked): who calls them cannot make them do anything else, so their callers are not followed. Each is kept as a whole.
CHECKED: Dict[str, Tuple[str, ...]] = {
    "storage.py": ("encrypt", "decrypt", "_openssl_run", "_pass_mode"),     # openssl with fixed commands; the key goes in as a value (over a pipe)
    "mm_bridge.py": ("_call",),                                           # one fixed script, only the listed commands of MoneyMoney
    "auth.py": ("touchid_verify", "touchid_unseal", "_helper_line"),     # Kontor's own helper; the text is what its window says, the rest base64/hex Kontor made
    "kontor.py": ("service_answers", "stop_service"),                     # 127.0.0.1 only; launchctl with Kontor's own label
    "llm_local.py": ("_open", "_env", "ensure", "install_runtime"),       # allowed hosts only; program and model from Kontor's own lists
    "mm_history.py": ("_wipe", "decrypt_in_place", "_page1_ok", "receive", "MemDB", "keys_from_dialog", "run"),     # the uploaded bytes, in memory
    "core.py": ("_cached", "refresh_accounts"), "model.py": ("ledger_to_bytes", "without_planned"),     # values copied from one of Kontor's objects to another
    "service.py": ("show_in_finder", "open_document", "choose_on_mac", "timemachine_set", "timemachine_status"),     # a path or a line of text
    "updates.py": ("_get",),                                              # allowed hosts only
    "tls_cert.py": ("setup", "renew_if_due", "cert_expiry", "ask"),       # Tailscale's own program (found by Kontor), paths in Kontor's data folder; fixed questions, read only
    "security_names.py": ("_post", "lookup"),                             # one fixed address; ISINs only
    # Kontor's own Python: the starter runs only the program inside Kontor's own .python/ that the state file names, with
    # Kontor's own kontor.py (or itself anew); a build is tried alone (-I -S -B) and only from inside that folder; Apple's
    # xattr and codesign only on a folder inside it
    "pyboot.py": ("_serve", "_again"), "pyruntime.py": ("run_python", "unmark", "sign"),
    "web_reader.py": ("ask_claude",),                                     # one fixed address (Anthropic's interface), the key in its header; nothing else of the request counts
}
# -- more rules (review before 3.17), kept apart from the lists above: who may install an update and with whose approval (only
# at the Mac; the approval the page sent, never one made up by the program; a backup cannot change where updates come from),
# where the assistant's downloads come from and that nothing is loaded without a SHA-256 that fits. A name stands for a
# function or for a setting at the top of the file. The function that installs an update is also CHECKED: it looks itself
# at where the request comes from, and what it hands on is the approval the page sent.
for _rel, _names in (("service.py", ("_is_local", "_loopback", "_update_install", "restored_config", "_proxied", "PROXIED", "_at_mac")),
                     ("auth.py", ("is_loopback",)),
                     ("llm_local.py", ("_fetch", "pick_asset", "listing", "repo_files", "latest_runtime", "RUNTIME_REPO", "RELEASES_URL")),
                     # Kontor's own Python (3.17.12): the one build that is loaded and from where, with its size and SHA-256; that
                     # it is compared with its archive and tried before the switch, in this order; which program the starter
                     # takes for the service and which one launchd starts; who may ask for it (only at the Mac)
                     ("pyruntime.py", ("REPO", "VERSION", "BUILD", "FILES", "URL", "build", "fetch", "same", "tried", "runnable", "_work")),
                     ("pyboot.py", ("FOLDER", "DIR_RE", "inside", "exe_in", "chosen", "start", "launch_python")),
                     ("service.py", ("_python_do",))):
    RULES[_rel] = tuple(RULES.get(_rel, ())) + _names
CHECKED["service.py"] = CHECKED["service.py"] + ("_update_install",)
# ... on the pages: what the update page shows of the findings and how it sends the approval, each as a whole
PAGE_RULES = {"web/app.js": ("UP_KINDS", "upFinds", "upPlain", "upLines", "upEntry", "upReview", "upInstall")}
# ... words that carry an approval: where one of them turns up in these files (as a text or as the name of an argument), the
# function around it is kept as a whole
WORDS = {"service.py": ("approved",)}
# ... where something is fetched from: a fixed text given to a key or name like this ({"repo": "a/b"}, RUNTIME_REPO = "a/b",
# x.get("repo") or "a/b") is kept as an address -- another one is shown, more of the same (a new model in a repository named
# already) is not
SOURCE = re.compile(r"(?i)(?:^|_)repo(?:s|sitory)?(?:_|$)")

# -- what a finding means to you. Every finding is a risk ("critical": asked about) unless it is known here as something
# less, and the reason why that is safe stands beside it:
#   "review" -- a way out that is there already now carries something put together differently (what feeds a call that
#               reaches out, the call itself changed): asked about as well, but one entry per way, not per function;
#   "plain"  -- nothing that can reach further: a rule that is only stricter (below). Shown as one quiet line, installed
#               without asking.
L_CRITICAL, L_REVIEW, L_PLAIN = "critical", "review", "plain"
# How each rule above is judged (a test keeps every name of RULES, PAGE_RULES and WORDS in here; a rule not in here is a
# risk). Policies:
#   "risk"   -- every change is asked about;
#   "card"   -- what the internet search checks or builds before anything goes out: every lookup stands on a card in the chat
#               first, whole (web_search.SHOWN_MAX: a longer one is not made), with every word and address that goes out, and
#               goes out only after your click -- but in a chat you allowed, without a click (only visibly on the card). Whether
#               a change makes the filter stricter or softer cannot be proven: asked about, as one entry (review) for all of it;
#   "allow"  -- a fixed table of what may be reached: plain when the new one holds nothing the old did not (entries only taken
#               away, nothing else changed) -- fewer places to reach can only be stricter;
#   "deny"   -- a fixed table of what is kept apart: plain when the new one holds everything the old did (entries only added);
#   "shield" -- a profile of macOS' sandbox: plain when the function is the same but for rules "(deny ...)" added -- each a
#               plain text that is one whole rule -- and rules "(allow ...)" taken away. In the sandbox's language a rule
#               more that denies, or one less that allows, never lets anything more through, wherever it stands.
# Each group: (topic, policy, {file: names}) -- the topic names the entry the update page shows (and its explanation).
RULE_GROUPS: Tuple[Tuple[str, str, Dict[str, Tuple[str, ...]]], ...] = (
    # the check itself: who may install an update, with whose approval, what a backup may change of it, what the update page
    # shows of the findings and sends (a change could hide a finding or approve by itself) -- always asked about
    ("check", "risk", {"service.py": ("_update_install", "restored_config"), "web/app.js": PAGE_RULES["web/app.js"]}),
    # where Kontor listens, who counts as "at the Mac", what its pages may load and from where -- a change can open Kontor
    ("access", "risk", {"service.py": ("bind_allowed", "_sec_headers", "_host_ok", "_origin_ok", "_static", "_is_local", "_loopback", "_proxied", "PROXIED", "_at_mac"),
                        "auth.py": ("is_loopback",)}),
    # where the internet search's reader may connect (hosts, redirects, no address of this Mac or the local network), the
    # headers it sends (not on the card), which results the page links -- a change can reach other places unseen
    ("reader", "risk", {"web_reader.py": ("host_ok", "public", "global_address", "inner_addresses", "NAT64", "NAT64_LOCAL", "redirect_request"),
                        "web_search.py": ("_req", "link_hits", "user_agent", "NEUTRAL_AGENT",
                                          # a question to Claude: what the reader is handed beside the card's text -- the address, your
                                          # key, how long and how much, the words an error is looked through for
                                          "claude_request", "CLAUDE_URL", "CLAUDE_SECONDS", "CLAUDE_BYTES", "CLAUDE_SAID")}),
    # ... the sources, their hosts, the hosts results are linked on, the fixed feeds: fewer is stricter
    ("reader", "allow", {"web_search.py": ("SOURCES", "LINK_HOSTS", "FEEDS")}),
    # ... the reader's own process: its sandbox profile (judged by its rules), and which program runs as the reader
    ("reader_shield", "shield", {"web_search.py": ("reader_profile",)}),
    ("reader_shield", "risk", {"web_search.py": ("command", "python_exe", "READER", "SANDBOX", "HERE")}),
    # what goes without a card in a chat you allowed: trusted sources and websites -- a change can let more out unasked
    ("trust", "risk", {"web_search.py": ("site", "_ace", "trusted", "trusted_site", "trusted_default", "HOSTS_MAX"), "assistant.py": ("_trusted",)}),
    # ... domains shared by many websites and second-level names (each subdomain its own website): more is stricter -- so are
    # the sources asked on a card every time (Claude) and those whose results stand on any website (a page there is asked for)
    ("trust", "deny", {"web_search.py": ("SHARED", "_SECOND", "ASKED_ALWAYS", "ANYWHERE")}),
    # the filter that keeps your own data out of a lookup and how a lookup is put together: behind the card (see "card")
    ("filter", "card", {"web_search.py": ("privacy_problem", "_own_in", "_not_plain", "_fold", "_name_tokens", "_readings", "_figure", "_iban", "_lei_ok",
                                          "own_index", "_INVISIBLE", "_LETTERS", "_SIGNS", "_BASE", "_PERCENT", "LEGAL", "GENERIC", "IBAN_LENGTH",
                                          "_IBAN_RUN", "_CODE", "_NO_AMOUNT", "_NO_FIGURES", "_PERIOD", "_NUMBER", "_YEAR", "_RUN", "_CHAIN", "_LEET",
                                          "_PLAIN_LEAST", "prepare", "prepare_read", "_q", "_month", "_since", "_last", "_SERIES", "_DATASET",
                                          "_LEI", "_QID",
                                          # the text of a question to Claude: on its card whole, and that card is clicked every time
                                          "claude_body", "CLAUDE_MODELS", "CLAUDE_TOKENS", "CLAUDE_SEARCHES", "CLAUDE_QUESTION", "CLAUDE_SYSTEM"),
                        "assistant.py": ("_own",)}),
    # no change once text from the internet is in a chat -- not a way out, but what keeps foreign text from acting on your data
    ("web_changes", "risk", {"assistant.py": ("_propose",)}),
    # what the language model is shut out of (judged by its rules)
    ("model_shield", "shield", {"llm_local.py": ("sandbox_profile",)}),
    # where the assistant's programs and models come from and that each file is checked
    ("downloads", "risk", {"llm_local.py": ("host_allowed", "_safe_join", "_fetch", "pick_asset", "listing", "repo_files", "latest_runtime", "RUNTIME_REPO", "RELEASES_URL")}),
    # Kontor's own Python: which build is loaded from where and that it is checked, compared and tried before anything is
    # switched; which program runs the service -- a change can load, start or keep another program. A newer build changes
    # the lines that name it: asked about as well, as one entry
    ("python", "risk", {"pyruntime.py": ("REPO", "VERSION", "BUILD", "FILES", "URL", "build", "fetch", "same", "tried", "runnable", "_work"),
                        "pyboot.py": ("FOLDER", "DIR_RE", "inside", "exe_in", "chosen", "start", "launch_python"),
                        "service.py": ("_python_do",)}),
    # what goes to OpenFIGI (only ISINs) -- after a click, but not shown before
    ("isin", "risk", {"security_names.py": ("valid_isin",)}),
    # which receipt files Kontor hands out or opens
    ("receipts", "risk", {"receipts.py": ("external_ok", "inside")}),
)
# ... the words that carry an approval belong to the check
WORD_TOPIC = "check"
# sandbox profiles that are no rule above but feed a call that reaches out (an "around"): judged by their rules as well
PROFILES = {"receipt_text.py": {"_profile": "receipt_shield"}}
RULE_LEVEL: Dict[str, Dict[str, Tuple[str, str]]] = {}
for _topic, _policy, _files in RULE_GROUPS:
    for _rel, _names in _files.items():
        for _name in _names:
            RULE_LEVEL.setdefault(_rel, {})[_name] = (_topic, _policy)
for _rel, _names in PROFILES.items():
    for _name, _topic in _names.items():
        RULE_LEVEL.setdefault(_rel, {}).setdefault(_name, (_topic, "shield"))
# the entries of the update page: (title, explanation) as keys of web/i18n.js, by topic -- a title takes the entry's {0}
RULE_TOPICS = frozenset([g[0] for g in RULE_GROUPS] + [t for names in PROFILES.values() for t in names.values()] + ["check", "rules"])
TOPIC_TEXT = {t: ("upd_t_" + t, "upd_w_" + t) for t in (
    "check", "access", "reader", "reader_shield", "trust", "filter", "web_changes", "model_shield", "receipt_shield", "downloads", "python", "isin",
    "receipts", "rules", "shadow", "module", "detour", "self", "place", "address", "page", "file", "script", "extra", "unreadable",
    "new_host", "new_program", "new_net", "new_other", "way_host", "way_program", "way_net", "way_other")}
# ... in this order on the page (a topic not named here after them)
TOPIC_ORDER = ("check", "access", "model_shield", "reader_shield", "receipt_shield", "reader", "trust", "web_changes", "downloads", "python", "isin",
               "receipts", "rules", "shadow", "self", "detour", "module", "new_host", "new_program", "new_net", "new_other", "address", "place",
               "page", "script", "file", "extra", "unreadable", "way_host", "way_program", "way_net", "way_other", "filter")
_PY_BREAK = re.compile(r"\r\n|\r|\n")                 # where Python ends a line (splitlines cuts at more)
_ODD_BREAK = re.compile("[\x0b\x0c\x1c\x1d\x1e\x85\u2028\u2029]")       # ... where it does not, but splitlines would
_FILLERS = frozenset("\u00ad\u034f\u061c\u115f\u1160\u17b4\u17b5\u180e\u3164\uffa0")


def _hidden(c: str) -> bool:
    """A character that hides in a line or turns it around: controls (not a tab), format and private characters, separators,
    variation selectors, tags, fillers that look like nothing."""
    o = ord(c)
    return c != "\t" and (unicodedata.category(c) in ("Cc", "Cf", "Co", "Cs", "Cn", "Zl", "Zp") or c in _FILLERS
                          or 0xFE00 <= o <= 0xFE0F or 0xE0000 <= o <= 0xE01EF)
MUTATORS = frozenset("""clear update add discard remove pop popitem setdefault append extend insert sort reverse difference_update
intersection_update symmetric_difference_update __setitem__ __delitem__ __iadd__ __ior__ __isub__ __iand__ __setattr__""".split())
LINES_MOST = 24                     # lines of one finding shown, at most (changed lines with one line around them)
LINES_ALL = 400                     # ... of all findings together (the settings carry them)
LINE_WIDTH = 160                    # characters of one line shown
NET = frozenset("socket urllib http ssl ftplib smtplib poplib imaplib xmlrpc asyncio selectors webbrowser".split())
# what a file of the check holds is part of the check's own finding (its content is all compared there): never its name
INSIDE = frozenset(("call", "around", "detour", "place", "address", "module", "self"))

# names every list, text or table has: a call like x.update() says nothing about whose update it is
COMMON = frozenset(n for t in (dict, list, str, set, bytes, tuple, bytearray, frozenset) for n in dir(t)) | frozenset(
    ("read", "write", "close", "open", "flush", "seek", "run", "start", "send", "recv", "put", "wait", "acquire", "release", "is_set"))
SMALL = 40                  # lines: a function of the file whose result goes into such a call is kept whole up to this size
KINDS = ("guard", "rule", "shadow", "module", "call", "around", "detour", "self", "place", "address", "page", "file", "extra", "unreadable")

# writing files: with a path that leads into the program's own folder it is shown (a program that changes its own files)
WRITERS = {"os": ("rename", "replace", "renames", "remove", "unlink", "rmdir", "removedirs", "makedirs", "mkdir", "chmod", "chown", "symlink",
                  "link", "truncate", "open", "utime"),
           "shutil": ("copy", "copy2", "copyfile", "copytree", "copymode", "copystat", "move", "rmtree", "make_archive", "unpack_archive"),
           "io": ("open", "FileIO"), "gzip": ("open", "GzipFile"), "zipfile": ("ZipFile",), "tarfile": ("open", "TarFile"), "wave": ("open",),
           "logging": ("FileHandler", "basicConfig"), "logging.handlers": ("RotatingFileHandler", "TimedRotatingFileHandler", "WatchedFileHandler"),
           "tempfile": ("NamedTemporaryFile", "mkstemp", "mkdtemp", "TemporaryDirectory", "TemporaryFile", "SpooledTemporaryFile")}
WRITER_MODES = frozenset(("io.open", "io.FileIO", "gzip.open", "gzip.GzipFile", "zipfile.ZipFile", "tarfile.open", "tarfile.TarFile", "wave.open"))
WRITE_METHODS = frozenset(("write_text", "write_bytes", "touch", "rename", "replace", "unlink", "rmdir", "mkdir", "chmod", "symlink_to",
                           "hardlink_to", "link_to", "extractall", "extract", "open"))
READ_MODE = re.compile(r"^[rbtU]{0,3}$")
HOME_NAME = "__file__"
# ... what builds a path from another or hands a value on as it is (the way to the program's folder is followed through these)
PATH_FUNCS = frozenset(("join", "dirname", "abspath", "realpath", "normpath", "normcase", "expanduser", "expandvars", "split", "splitext", "relpath",
                        "commonpath", "commonprefix", "basename"))
PATH_CALLS = frozenset(("str", "bytes", "repr", "format", "min", "max", "sorted", "list", "tuple", "set", "frozenset", "dict", "reversed", "next", "iter",
                        "zip", "map", "filter", "enumerate", "getattr"))
PATH_METHODS = frozenset(("joinpath", "with_name", "with_suffix", "with_stem", "resolve", "absolute", "expanduser", "as_posix", "relative_to",
                          "format", "replace", "strip", "lstrip", "rstrip", "lower", "upper", "decode", "encode", "join", "split", "rsplit",
                          "partition", "rpartition", "removeprefix", "removesuffix", "get", "pop", "setdefault", "copy", "values", "items",
                          "__str__", "__fspath__", "__truediv__", "__add__"))
PATH_ATTRS = frozenset(("parent", "parents", "anchor"))
PROGRAM_FILE = re.compile(r"(?i)\.(?:py|pyc|pyo|pth|swift|jxa|sh|command|js|mjs|html?)$")

# helpers and scripts Kontor cannot follow like Python: compared by their lines without comments and empty space
SCRIPTS = (".swift", ".jxa", ".sh", ".command")
# ... and what in them reaches out, as far as fixed patterns can tell (a shell script does so in every line)
OUT = {".swift": re.compile(r"\b(?:Process|NSTask|URLSession|URLRequest|URLComponents|NSURL|URL|NWConnection|NWListener|NWEndpoint|CFSocket\w*|CFStream\w*"
                            r"|socket|connect|bind|listen|dlopen|dlsym|system|popen|posix_spawn\w*|exec[lv]\w*|fork|NSAppleScript|OSAScript\w*"
                            r"|NSUserAppleScriptTask|NSWorkspace|NSXPC\w+|DistributedNotificationCenter|NSPasteboard|FileManager|FileHandle|FileWrapper"
                            r"|write|contentsOf|contentsOfFile|SecItem\w+|SecKey\w+|SecAccess\w+|LAContext|getenv|setenv|ProcessInfo|UserDefaults|import"
                            r"|WKWebView\w*|WKWebsiteDataStore|WKUserScript|evaluateJavaScript|AVCapture\w+|CGWindowList\w+|SCStream\w*|CGEvent\w*"
                            r"|NSEvent|open|openURL|Bundle|NSClassFromString|NSSelectorFromString|perform|unsafeBitCast|withUnsafe\w+)\b"),
       ".jxa": re.compile(r"\b(?:Application|doShellScript|ObjC|Library|Path|currentApplication|includeStandardAdditions|openLocation|open|eval"
                          r"|Function|require|run|delay|[A-Z][A-Z0-9_]{2,})\b|\$\s*[.(]|\[[^\]\n]+\]\s*\(|:\s*true\b"),
       ".sh": re.compile(r"\S"), ".command": re.compile(r"\S")}

# a git clone holds the whole repository: these folders and files of it are no part of the program (an update from an archive
# leaves them out), and what they ordinarily hold -- tests, rules for GitHub and for development -- is not asked about
BESIDE = ("tests", ".github", ".claude", ".githooks")
BESIDE_FILES = (".gitignore", ".gitattributes", ".gitmodules")
BESIDE_ENDS = (".py", ".md", ".txt", ".json", ".yml", ".yaml", ".toml", ".cfg", ".ini", ".sh", ".mjs", ".js", ".html", ".css", ".svg", ".xml",
               ".csv", ".png", ".jpg", ".jpeg", ".gif", ".pdf", ".xlsx", ".xlsm", ".wav", ".swift", ".jxa")
# ... and what a helper or Python itself makes beside the program while it runs: never part of an update, whatever the
# repository's own list (.gitignore) says
MADE_HERE = "__pycache__/\n*.pyc\n*.pyo\n.touchid/\n.receipt_ocr/\n*.app/\n.mac-app-*/\n.mac_app_build\n.old/\nmm_touchid\n.files\n.python/\n"
STARTUP = frozenset(("sitecustomize.py", "usercustomize.py"))       # loaded by Python itself, wherever it finds them
# the parts of Python by name (3.9 to 3.13, also those since removed): a file or folder of that name in the program folder
# is loaded instead
STDLIB = frozenset("""__future__ _abc _aix_support _android_support _apple_support _ast _asyncio _bisect _blake2 _bootlocale _bz2 _codecs _codecs_cn
_codecs_hk _codecs_iso2022 _codecs_jp _codecs_kr _codecs_tw _collections _collections_abc _colorize _compat_pickle _compression
_contextvars _crypt _csv _ctypes _curses _curses_panel _datetime _dbm _decimal _elementtree _frozen_importlib
_frozen_importlib_external _functools _gdbm _hashlib _heapq _imp _interpchannels _interpqueues _interpreters _io _ios_support _json
_locale _lsprof _lzma _markupbase _md5 _msi _multibytecodec _multiprocessing _opcode _opcode_metadata _operator _osx_support
_overlapped _pickle _posixshmem _posixsubprocess _py_abc _pydatetime _pydecimal _pyio _pylong _pyrepl _queue _random _scproxy _sha1
_sha2 _sha256 _sha3 _sha512 _signal _sitebuiltins _socket _sqlite3 _sre _ssl _stat _statistics _string _strptime _struct
_suggestions _symtable _sysconfig _thread _threading_local _tkinter _tokenize _tracemalloc _typing _uuid _warnings _weakref
_weakrefset _winapi _wmi _zoneinfo abc aifc antigravity argparse array ast asynchat asyncio asyncore atexit audioop base64 bdb
binascii binhex bisect builtins bz2 cProfile calendar cgi cgitb chunk cmath cmd code codecs codeop collections colorsys compileall
concurrent configparser contextlib contextvars copy copyreg crypt csv ctypes curses dataclasses datetime dbm decimal difflib dis
distutils doctest email encodings ensurepip enum errno faulthandler fcntl filecmp fileinput fnmatch formatter fractions ftplib
functools gc genericpath getopt getpass gettext glob graphlib grp gzip hashlib heapq hmac html http idlelib imaplib imghdr imp
importlib inspect io ipaddress itertools json keyword lib2to3 linecache locale logging lzma macpath mailbox mailcap marshal math
mimetypes mmap modulefinder msilib msvcrt multiprocessing netrc nis nntplib nt ntpath nturl2path numbers opcode operator optparse os
ossaudiodev parser pathlib pdb pickle pickletools pipes pkgutil platform plistlib poplib posix posixpath pprint profile pstats pty
pwd py_compile pyclbr pydoc pydoc_data pyexpat queue quopri random re readline reprlib resource rlcompleter runpy sched secrets
select selectors shelve shlex shutil signal site sitecustomize smtpd smtplib sndhdr socket socketserver spwd sqlite3 sre_compile
sre_constants sre_parse ssl stat statistics string stringprep struct subprocess sunau symbol symtable sys sysconfig syslog tabnanny
tarfile telnetlib tempfile termios textwrap this threading time timeit tkinter token tokenize tomllib trace traceback tracemalloc
tty turtle turtledemo types typing unicodedata unittest urllib usercustomize uu uuid venv warnings wave weakref webbrowser winreg
winsound wsgiref xdrlib xml xmlrpc zipapp zipfile zipimport zlib zoneinfo""".split())


def installable(rel: str) -> bool:
    """Does an update put this file of the repository into the program folder? (As updates.install copies: not the tests, not
    what starts with a dot, no caches.)"""
    parts = rel.replace("\\", "/").split("/")
    return bool(rel) and not any(p in ("tests", "__pycache__") or p.startswith(".") for p in parts[:-1]) and not parts[-1].startswith(".")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def digest(files: Dict[str, bytes], whole: bool = False) -> str:
    """One value for exactly these files and their content (what an approval is given for). whole: every file, also those
    that are no part of the program (a git clone takes the whole repository)."""
    h = hashlib.sha256()
    for rel in sorted(files):
        if whole or installable(rel):
            h.update(rel.encode("utf-8", "surrogateescape") + b"\0" + hashlib.sha256(files[rel]).digest())
    return h.hexdigest()


def kept() -> Set[str]:
    """The files this check names (itself, rules, checked functions): read from the installed program even when the new
    version no longer has them -- so that one of them gone is seen."""
    return set(OWN) | set(RULES) | set(CHECKED) | set(PAGE_RULES) | set(WORDS)


def _alike(rel: str) -> str:
    """A path as the Mac's disks compare it: without regard to upper and lower case or to how a letter is put together."""
    return unicodedata.normalize("NFD", unicodedata.normalize("NFD", rel).casefold())


def _own(rel: str) -> bool:
    """Is this file (part of) the update check itself -- by the name it is loaded with, whatever kind of file it is?"""
    return _alike(rel) in {_alike(o) for o in OWN} or _alike(rel.split("/")[0]) in {_alike(o[:-3]) for o in OWN}


# ---------------------------------------------------------------------------
# text put together from fixed pieces
# ---------------------------------------------------------------------------

HOLE = "\0"                 # stands for a piece that is not fixed (a name, a call)
_TEXT_METHODS = frozenset(("lower", "upper", "strip", "lstrip", "rstrip", "title", "capitalize", "swapcase", "casefold", "decode", "encode",
                           "replace", "format", "join"))
_DECODERS = {("base64", "b64decode"): base64.b64decode, ("base64", "urlsafe_b64decode"): base64.urlsafe_b64decode,
             ("base64", "b32decode"): base64.b32decode, ("base64", "b16decode"): base64.b16decode, ("base64", "b85decode"): base64.b85decode,
             ("base64", "a85decode"): base64.a85decode, ("binascii", "unhexlify"): binascii.unhexlify, ("binascii", "a2b_hex"): binascii.a2b_hex,
             ("binascii", "a2b_base64"): binascii.a2b_base64, ("bytes", "fromhex"): bytes.fromhex, ("bytearray", "fromhex"): bytes.fromhex}
_FOLD_MAX = 4096


def _value(node: Optional[ast.AST], names: Dict[str, ast.AST], holes: bool = False, depth: int = 0):
    """What a piece of code comes to when it only puts fixed pieces together: 'Launch' + 'Agents', "%s%s" % (...), "".join([...]),
    f"...", 'x'[::-1], b'..'.decode(), base64.b64decode('...'), a name set once to such a text. A text, bytes or a whole
    number -- None when it is not fixed (holes: a HOLE stands for each piece that is not, so that the fixed pieces around it
    still read as one text). Only these fixed operations on fixed values are worked out; nothing of the code is run."""
    def unknown():
        return HOLE if holes else None

    def sized(v):
        return v if not isinstance(v, (str, bytes)) or len(v) <= _FOLD_MAX else unknown()

    def go(x):
        return _value(x, names, holes, depth + 1)

    if node is None or depth > 60:
        return unknown()
    if isinstance(node, ast.Constant):
        v = node.value
        return sized(v) if isinstance(v, (str, bytes)) or type(v) is int else unknown()
    if isinstance(node, ast.Name):
        return go(names[node.id]) if node.id in names and depth < 20 else unknown()
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        v = _value(node.operand, names, False, depth + 1)
        return -v if type(v) is int else unknown()
    if isinstance(node, ast.JoinedStr):
        out = []
        for part in node.values:
            v = go(part.value) if isinstance(part, ast.FormattedValue) and part.format_spec is None and part.conversion == -1 else \
                go(part) if isinstance(part, ast.Constant) else unknown()
            if v is None:
                return None
            out.append(v.decode("utf-8", "replace") if isinstance(v, bytes) else str(v))
        return sized("".join(out))
    if isinstance(node, ast.BinOp):
        a, b = go(node.left), None
        if isinstance(node.op, ast.Add):
            b = go(node.right)
            if a is None or b is None:
                return None
            if holes and type(a) is not type(b):                 # a number and a piece that is not fixed, bytes and a hole ...
                a, b = (x.decode("utf-8", "replace") if isinstance(x, bytes) else HOLE if not isinstance(x, str) else x for x in (a, b))
            if type(a) is type(b) and isinstance(a, (str, bytes)):
                return sized(a + b)
            return unknown()
        if isinstance(node.op, ast.Mod) and isinstance(a, str) and re.fullmatch(r"(?:[^%]|%[sdr%])*", a):
            b = tuple(go(e) for e in node.right.elts) if isinstance(node.right, ast.Tuple) else go(node.right)
            if b is None or isinstance(b, tuple) and any(x is None for x in b):
                return None
            try:
                return sized(a % b)
            except (TypeError, ValueError):
                return unknown()
        if isinstance(node.op, ast.Mult):
            b = go(node.right)
            if isinstance(a, int) and isinstance(b, (str, bytes)):
                a, b = b, a
            if isinstance(a, (str, bytes)) and type(b) is int and 0 <= b <= 64 and HOLE not in (a if isinstance(a, str) else ""):
                return sized(a * b)
        return unknown()
    if isinstance(node, ast.Subscript):
        a = go(node.value)
        if not isinstance(a, (str, bytes)) or (holes and isinstance(a, str) and HOLE in a):
            return unknown()
        sl = node.slice
        try:
            if isinstance(sl, ast.Slice):
                bounds = [None if x is None else _value(x, names, False, depth + 1) for x in (sl.lower, sl.upper, sl.step)]
                if any(x is not None and type(x) is not int for x in bounds) or any(x is None and y is not None for x, y in zip(bounds, (sl.lower, sl.upper, sl.step))):
                    return unknown()
                return a[bounds[0]:bounds[1]:bounds[2]]
            i = _value(sl, names, False, depth + 1)
            return a[i] if type(i) is int else unknown()
        except (IndexError, ValueError):
            return unknown()
    if isinstance(node, ast.Call) and not node.keywords:
        f, args = node.func, node.args
        if isinstance(f, ast.Name):
            if f.id == "chr" and len(args) == 1:
                v = _value(args[0], names, False, depth + 1)
                return chr(v) if type(v) is int and 0 <= v < 0x110000 else unknown()
            if f.id == "str" and len(args) in (1, 2):
                v = go(args[0])
                return v.decode("utf-8", "replace") if isinstance(v, bytes) else str(v) if isinstance(v, (str, int)) else unknown()
            if f.id in ("bytes", "bytearray") and len(args) == 1:
                seq = _values(args[0], names, depth + 1)
                if seq is not None and all(type(x) is int and 0 <= x < 256 for x in seq):
                    return bytes(seq)
                v = go(args[0])
                return v if isinstance(v, bytes) else unknown()
            return unknown()
        if isinstance(f, ast.Attribute):
            if isinstance(f.value, ast.Name) and (f.value.id, f.attr) in _DECODERS and len(args) == 1:
                v = _value(args[0], names, False, depth + 1)
                try:
                    return sized(_DECODERS[(f.value.id, f.attr)](v)) if isinstance(v, (str, bytes)) else unknown()
                except (ValueError, TypeError):
                    return unknown()
            if f.attr == "join" and len(args) >= 1 and isinstance(f.value, ast.Attribute) and f.value.attr == "path":      # os.path.join(a, 'b' + 'c')
                parts = [go(x) for x in args]
                return sized("/".join(x if isinstance(x, str) else HOLE for x in parts)) if holes and None not in parts else unknown()
            recv = go(f.value)
            if not isinstance(recv, (str, bytes)) or f.attr not in _TEXT_METHODS:
                return unknown()
            try:
                if f.attr == "join" and len(args) == 1:
                    seq = _values(args[0], names, depth + 1, holes)
                    return sized(recv.join(seq)) if seq is not None and all(type(x) is type(recv) for x in seq) else unknown()
                if f.attr == "format":
                    vals = [go(x) for x in args]
                    if None in vals or not isinstance(recv, str) or not re.fullmatch(r"(?:[^{}]|\{\d*\}|\{\{|\}\})*", recv):
                        return unknown()
                    return sized(recv.format(*vals))
                if f.attr in ("decode", "encode"):
                    codec = [_value(x, names, False, depth + 1) for x in args[:1]]
                    if codec and not (isinstance(codec[0], str) and codec[0].lower().replace("-", "").replace("_", "") in ("utf8", "ascii", "latin1")):
                        return unknown()
                    return recv.decode(*(codec or ["utf-8"]), "replace") if isinstance(recv, bytes) and f.attr == "decode" else \
                        recv.encode(*(codec or ["utf-8"]), "replace") if isinstance(recv, str) and f.attr == "encode" else unknown()
                vals = [go(x) for x in args]
                if any(type(x) is not type(recv) for x in vals) or len(vals) > 2:
                    return unknown()
                return sized(getattr(recv, f.attr)(*vals))
            except (TypeError, ValueError, LookupError):
                return unknown()
    return unknown()


def _values(node: ast.AST, names: Dict[str, ast.AST], depth: int = 0, holes: bool = False) -> Optional[list]:
    """A fixed row of such values: [..], (..), a text letter by letter, reversed(...), map(chr, [...])."""
    if isinstance(node, (ast.List, ast.Tuple)) and len(node.elts) <= 512:
        out = [_value(e, names, holes, depth + 1) for e in node.elts]
        return None if None in out else out
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and not node.keywords:
        if node.func.id in ("reversed", "list", "tuple") and len(node.args) == 1:
            inner = _values(node.args[0], names, depth + 1, holes)
            return None if inner is None else list(reversed(inner)) if node.func.id == "reversed" else inner
        if node.func.id == "map" and len(node.args) == 2 and isinstance(node.args[0], ast.Name) and node.args[0].id == "chr":
            inner = _values(node.args[1], names, depth + 1)
            return [chr(x) for x in inner] if inner is not None and all(type(x) is int and 0 <= x < 0x110000 for x in inner) else None
    v = _value(node, names, False, depth + 1)
    return list(v) if isinstance(v, str) else None


def _text_of(v) -> Optional[str]:
    return v if isinstance(v, str) else v.decode("utf-8", "replace") if isinstance(v, bytes) else None


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


def _span(node: ast.AST) -> Optional[Tuple[int, int]]:
    """The lines a piece of code stands on (a function with its decorators)."""
    first = getattr(node, "lineno", None)
    if not isinstance(first, int):
        return None
    first = min([first] + [d.lineno for d in getattr(node, "decorator_list", []) if isinstance(getattr(d, "lineno", None), int)])
    return first, max(first, getattr(node, "end_lineno", None) or first)


def _at(node: ast.AST, **more) -> dict:
    """What the page is told of a finding at this piece of code: its lines and whatever else is given."""
    span = _span(node)
    return dict(more, spans=[span] if span else [])


_PLACES_OF_VALUES = (ast.Assign, ast.AnnAssign, ast.AugAssign, ast.NamedExpr, ast.For, ast.AsyncFor, ast.comprehension, ast.With, ast.AsyncWith)
_SOURCE_PLACES = (ast.Dict, ast.Assign, ast.AnnAssign, ast.keyword, ast.arguments, ast.BoolOp)


class _Py:
    """One program file: where it reaches out, and what belongs to those places."""

    def __init__(self, rel: str, tree: ast.Module, local: Set[str], world: Optional[Dict[str, "_Py"]] = None):
        self.rel, self.local = rel, local
        self.world: Dict[str, "_Py"] = world if world is not None else {}      # the program's own parts by the name they are imported with
        self.tree = tree
        self.nodes: List[ast.AST] = []                        # every piece of the file, walked once (with what it stands in)
        self.parents: Dict[int, ast.AST] = {}
        todo: List[ast.AST] = [tree]
        kind: Dict[type, List[ast.AST]] = {}                  # the same pieces by their kind (in the same order)
        while todo:
            p = todo.pop()
            self.nodes.append(p)
            kind.setdefault(type(p), []).append(p)
            body = getattr(p, "body", None)                   # explanations at the start of a function, class or file are no code
            if isinstance(p, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)) and body and isinstance(body[0], ast.Expr) \
                    and isinstance(getattr(body[0], "value", None), ast.Constant) and isinstance(body[0].value.value, str):
                p.body = body[1:] or [ast.Pass()]
            for c in ast.iter_child_nodes(p):
                self.parents[id(c)] = p
                todo.append(c)

        def of(*types: type) -> List[ast.AST]:
            return [n for t in types for n in kind.get(t, [])] if len(types) > 1 else list(kind.get(types[0], []))
        self.chains: List[ast.AST] = [n for n in self.nodes if type(n) in (ast.Name, ast.Attribute) and type(self.parents.get(id(n))) is not ast.Attribute]
        self.out: Dict[Tuple[str, str, str], str] = {}        # (kind, file, what) -> content, to compare
        self.shown: Dict[Tuple[str, str, str], str] = {}      # ... and a line of it to show
        self.info: Dict[Tuple[str, str, str], dict] = {}      # ... and for the page: its lines (spans), name, way out
        self.direct: Dict[int, tuple] = {}                    # ... and of each place that reaches out what it uses (ways_known)
        self.bound: Dict[str, str] = {}                       # a name in this file -> the part of Python behind it
        self.risky_names: Set[str] = set()                    # names that stand for something that reaches out
        self.modules: Set[str] = set()                        # names that stand for a whole part of Python (import x)
        self.assigned: Set[str] = {n.id for n in of(ast.Name) if isinstance(n.ctx, ast.Store)} | {
            a.arg for n in of(ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda) for a in n.args.args + n.args.kwonlyargs}
        self.heads: Dict[int, str] = {}
        self.late: List[Tuple[str, str, ast.AST]] = []        # names taken from the program's own parts: judged when every part is read
        self.exports: Set[str] = set()                        # names of this file (at its top) for something that reaches out
        self.home: Set[str] = set()                           # names of this file (settings, functions) that lead to the program's folder
        self.home_attrs: Set[str] = set()                     # ... and values kept in an object (self.base = HERE)
        self.writers: Dict[int, Tuple[str, List[str], Set[str]]] = {}     # functions that write where they are told: (name, takes, which of it)
        self.echo: Dict[str, Set[int]] = {}                   # functions that give back what they are given: which of it (by place ...
        self.echo_names: Dict[str, Set[str]] = {}             # ... and by name)
        self.spreads: Dict[Tuple[int, frozenset], Set[str]] = {}
        self.assigns: Dict[int, List[Tuple[Set[str], ast.AST]]] = {}
        self.folded: Dict[int, object] = {}
        once: Dict[str, List[ast.AST]] = {}                   # names set exactly once in the file, to something fixed ('Launch'): read as that
        for n in of(ast.Name):
            if isinstance(n.ctx, ast.Store):
                up = self.parents.get(id(n))
                once.setdefault(n.id, []).append(up.value if isinstance(up, (ast.Assign, ast.AnnAssign)) and up.value is not None and
                                                 (up.targets == [n] if isinstance(up, ast.Assign) else up.target is n) else None)
        taken = {a.arg for n in of(ast.arguments) for a in n.posonlyargs + n.args + n.kwonlyargs + [x for x in (n.vararg, n.kwarg) if x]} | {
            nm for n in of(ast.Global, ast.Nonlocal) for nm in n.names}
        self.consts: Dict[str, ast.AST] = {k: v[0] for k, v in once.items() if len(v) == 1 and v[0] is not None and k not in taken
                                           and isinstance(v[0], (ast.Constant, ast.BinOp, ast.JoinedStr, ast.Call, ast.Subscript))}
        self._imports()
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
            if type(n) in (ast.FunctionDef, ast.AsyncFunctionDef):
                self.defs.setdefault(n.name, []).append(n)
                if isinstance(self.parents.get(id(n)), ast.ClassDef):
                    self.methods.add(id(n))
        self.passing: Dict[int, Tuple[str, List[str], Set[str], bool]] = {}     # functions that hand what they are given on to such a
        self.deciding: Dict[int, List[ast.AST]] = {}          # place: (name, what they take, which of it goes there, takes more)
        self.seen_refs: Set[Tuple[int, int]] = set()
        self.top_classes: Set[str] = {st.name for st in self.tree.body if isinstance(st, ast.ClassDef)}
        self.returns: Dict[int, List[ast.AST]] = {}           # of each function: what it hands back
        for n in of(ast.Return):
            if n.value is not None:
                up = self.parents.get(id(n))
                while up is not None and not isinstance(up, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                    up = self.parents.get(id(up))
                if up is not None and not isinstance(up, ast.Lambda):
                    self.returns.setdefault(id(up), []).append(n.value)
        self.calls: List[ast.Call] = of(ast.Call)          # type: ignore[assignment]
        self.self_hits: Set[int] = set()
        self.fns: Dict[int, ast.AST] = {id(d): d for ds in self.defs.values() for d in ds}
        self.aliasing: List[ast.AST] = [n for n in self.nodes if type(n) is ast.ClassDef or type(n) in (ast.Assign, ast.AnnAssign, ast.NamedExpr)
                                        and isinstance(n.value, (ast.Name, ast.Attribute))]

    def find(self) -> None:
        """Every place of this file that reaches out -- asked when all files are read (a name may lead through another one)."""
        for mod, name, node in self.late:
            full = "%s.%s" % (mod, name)
            real, how = self._through(full)
            if how == "name" or how and real.split(".")[0] not in self.local and (how == "whole" or self._risky_path(real)):
                self._note("module", full, show="from %s import %s" % (mod, name), info=_at(node))
        self._find()
        self._writes()

    # -- what is imported -------------------------------------------------------------------------------------------------
    def _note(self, kind: str, what: str, content: str = "1", show: str = "", info: Optional[dict] = None) -> None:
        key = (kind, self.rel, what)
        if key not in self.out:
            self.out[key] = content
        elif content not in self.out[key].split("+"):          # (the same thing reached from two places is still one thing)
            self.out[key] = "+".join(sorted(self.out[key].split("+") + [content]))
        self.shown.setdefault(key, show or what)
        if info:                                              # for the page: where it stands, its name, the way out it belongs to
            have = self.info.setdefault(key, {})
            for k, v in info.items():
                if isinstance(v, list):
                    have.setdefault(k, [])
                    have[k] += [x for x in v if x not in have[k]]
                else:
                    have.setdefault(k, v)

    def _imports(self) -> None:
        for n in self.nodes:
            if isinstance(n, ast.Import):
                for a in n.names:
                    self.bound[a.asname or a.name.split(".")[0]] = a.name if a.asname else a.name.split(".")[0]
                    self.modules.add(a.asname or a.name.split(".")[0])
                    if not _harmless_module(a.name, self.local):
                        self._note("module", a.name, show="import " + a.name, info=_at(n))
            elif isinstance(n, ast.ImportFrom):
                mod = ("." * n.level) + (n.module or "")
                if n.level and not n.module:
                    continue
                for a in n.names:
                    self.bound[a.asname or a.name] = "%s.%s" % (mod, a.name)
                    full = "%s.%s" % (mod, a.name)
                    if a.name == "*" or not (_harmless_module(mod, self.local) or _harmless_module(full, self.local)) or self._risky_path(full):
                        self._note("module", full, show="from %s import %s" % (mod, a.name), info=_at(n))
                    elif mod.split(".")[0] in self.local:
                        self.late.append((mod, a.name, n))

    # -- is this dotted name something that reaches out? ------------------------------------------------------------------
    def _risky_path(self, path: str) -> bool:
        parts = path.split(".")
        if PLAIN.match(path):
            return False
        if parts[0] in self.local:                             # one of the program's own parts: only its insides and the parts of Python behind it
            own = next((i for i in range(len(parts), 0, -1) if ".".join(parts[:i]) in self.world), 1)
            return any(p in MODULE_NAMES or p in INSIDES or p in INSIDES_OF_MODULES for p in parts[own:])
        for i in range(len(parts), 0, -1):                     # the longest known part of Python at its start
            mod = ".".join(parts[:i])
            if mod in RISKY_IN and len(parts) > i and parts[i] in RISKY_IN[mod]:
                return True
            if mod in HARMLESS or mod in HARMLESS_SUB:
                rest = parts[i:]
                return bool(rest) and (rest[0].startswith("_")          # what a part of Python keeps for itself (tempfile._os, os._execvpe)
                                       or bool(mod in RISKY_START and RISKY_START[mod].match(rest[0]))
                                       or any(p in MODULE_NAMES or p in INSIDES or p in INSIDES_OF_MODULES for p in rest)
                                       or any(p in CODE_NAMES for p in rest[1:]))
        return True                                            # not a harmless part at all

    def _through(self, path: str) -> Tuple[str, str]:
        """A dotted name that starts with one of the program's own parts, followed through what that part itself imports or
        keeps under a name: 'storage.subprocess.Popen' is 'subprocess.Popen'. With how it ends: '' (in the program's own
        part), 'part' (in something of another part), 'whole' (it is another part, as a value), 'name' (the own part's name for
        something that reaches out: a class built on such a part, x = subprocess.run)."""
        parts, how = path.split("."), ""
        for _ in range(8):
            i = next((i for i in range(len(parts) - 1, 0, -1) if ".".join(parts[:i]) in self.world), 0)
            if not i:
                break
            other, name = self.world[".".join(parts[:i])], parts[i]
            if name in other.exports:
                return ".".join(parts), "name"
            target = other.bound.get(name)
            if target is None or target.startswith("."):
                break
            how = "whole" if len(parts) == i + 1 and name in other.modules else "part"
            parts = target.split(".") + parts[i + 1:]
        return ".".join(parts), how

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
        if root in TYPE_NAMES and "__dict__" in parts and root not in self.assigned and root not in self.bound:
            return "detour", root + ".__dict__"                # the table of names of a kind of value every Python has
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
            real, how = self._through(path)                    # ... or reached through one of the program's own parts
            if how == "name":
                return "call", path
            if how and real.split(".")[0] not in self.local:
                return ("detour", path) if how == "whole" or self._risky_path(real) else None
            path = real
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

    def aliases(self) -> bool:
        """Other names for what reaches out: a class built on such a part, a name such a part is put into (x = subprocess.run);
        other names for one of the program's own parts (m = storage); names that lead to the program's own folder. True when
        something was added (asked again then, for every file: a name may lead through another file)."""
        added, changed = False, True
        while changed:
            changed = False
            for n in self.aliasing:
                name = None
                if isinstance(n, ast.ClassDef):
                    if any(self._risk(b) for b in n.bases):
                        name = n.name
                elif self._risk(n.value):
                    t = n.targets[0] if isinstance(n, ast.Assign) else n.target
                    name = t.id if isinstance(t, ast.Name) else (t.attr if isinstance(t, ast.Attribute) else None)
                else:
                    root, parts = self._chain(n.value)
                    t = n.targets[0] if isinstance(n, ast.Assign) else n.target
                    if root in self.bound and not self.bound[root].startswith(".") and isinstance(t, ast.Name) and t.id not in self.bound:
                        real, _how = self._through(".".join([self.bound[root]] + parts))
                        if real in self.world:                 # another name for one of the program's own parts
                            self.bound[t.id] = real
                            self.modules.add(t.id)
                            changed = True
                if name and name not in self.risky_names:
                    self.risky_names.add(name)
                    if name in self.tops or name in self.top_classes:
                        self.exports.add(name)
                    changed = True
            seeds = self.home | {HOME_NAME}
            for name, sts in self.tops.items():                # HERE = os.path.dirname(os.path.abspath(__file__)), WEB = os.path.join(HERE, "web")
                if name not in self.home and any(getattr(st, "value", None) is not None and self._leads(st.value, seeds) for st in sts):
                    self.home.add(name)
                    changed = True
            for fid, values in self.returns.items():           # def here(): return os.path.dirname(__file__)
                fn = self.fns[fid]
                if fn.name not in (self.home_attrs if fid in self.methods else self.home):
                    names = self._spread(fn, seeds)
                    if any(self._leads(v, names) for v in values):
                        (self.home_attrs if fid in self.methods else self.home).add(fn.name)
                        changed = True
                if fid not in self.methods:                    # def same(p): return p -- gives back what it is given
                    given = [a.arg for a in fn.args.posonlyargs + fn.args.args]
                    for i, g in enumerate(given):
                        if i not in self.echo.get(fn.name, ()) and any(self._leads(v, self._spread(fn, {g})) for v in values):
                            self.echo.setdefault(fn.name, set()).add(i)
                            self.echo_names.setdefault(fn.name, set()).add(g)
                            changed = True
            added = added or changed
        return added

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
        words = WORDS.get(self.rel, ())
        joins = (ast.BinOp, ast.JoinedStr, ast.Call, ast.Subscript)
        for n in self.nodes:
            if id(n) in notes or isinstance(n, (ast.Name, ast.Attribute)):
                continue
            if isinstance(n, ast.Global):
                self._hit(n, "detour", "global " + ", ".join(n.names))
            elif isinstance(n, ast.Constant) and isinstance(n.value, str):
                self._text(n, n.value)
            elif isinstance(n, ast.keyword) and n.arg in words:
                self._hit(n, "detour", n.arg + "=")
            if isinstance(n, ast.Subscript):
                key = _text_of(self._fixed(n.slice))
                if key is not None and (key in INSIDES or key in MODULE_NAMES):
                    self._hit(n, "detour", "[%r]" % key)
                elif self._table(n.value) and (key is None or key.startswith("__")):
                    self._hit(n, "detour", "__dict__[…]")     # a table of names, asked by a name that is not fixed (or an inner one)
            elif isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in ("get", "pop", "setdefault", "__getitem__") \
                    and self._table(n.func.value) and n.args:
                key = _text_of(self._fixed(n.args[0]))
                if key is None or key.startswith("__"):
                    self._hit(n, "detour", "__dict__.%s(…)" % n.func.attr)
            # text put together from pieces: read as the whole it makes ('Launch' + 'Agents', "%s%s" % ..., f"...", "".join(...))
            if isinstance(n, joins) and not isinstance(self.parents.get(id(n)), (ast.BinOp, ast.JoinedStr, ast.FormattedValue)) \
                    and not isinstance(n, ast.Constant):
                whole = _text_of(_value(n, self.consts, True))
                if whole and whole.strip(HOLE):
                    for piece in whole.split(HOLE) if HOLE * 2 in whole else [whole]:
                        if piece:
                            self._text(n, piece.replace(HOLE, "…"), True)

    def _fixed(self, node: ast.AST):
        """The fixed value of a piece of code (see _value), or None."""
        if id(node) not in self.folded:
            self.folded[id(node)] = _value(node, self.consts)
        return self.folded[id(node)]

    def _table(self, node: ast.AST) -> bool:
        """x.__dict__ or vars(x): the names of something as a table."""
        return isinstance(node, ast.Attribute) and node.attr == "__dict__" or \
            isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "vars"

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

    def _text(self, node: ast.AST, s: str, joined: bool = False) -> None:
        """A text of the program (joined: one put together from pieces): the addresses and places it names; an inner name of
        Python as a text; a word that carries an approval."""
        for a in ADDRESS.findall(s):
            m = HOST.search(a)
            host = (m.group(1) if m else a).lower()
            if host not in NAMESPACES and not OWN_ADDRESSES.match(host) and host != "localhost":
                self._note("address", host, show=a[:80])
        m = PLACES.search(s)
        if m:
            self._hit(node, "place", m.group(0))
        if s in INSIDES:
            self._hit(node, "detour", repr(s))
        if s in WORDS.get(self.rel, ()):
            self._hit(node, "detour", repr(s))

    # -- writing into the program's own folder -------------------------------------------------------------------------------
    @staticmethod
    def _pairs(st: ast.AST) -> List[Tuple[Set[str], ast.AST]]:
        pairs: List[Tuple[ast.AST, ast.AST]] = []
        if isinstance(st, ast.Assign):
            pairs = [(t, st.value) for t in st.targets]
        elif isinstance(st, (ast.AnnAssign, ast.AugAssign, ast.NamedExpr)) and st.value is not None:
            pairs = [(st.target, st.value)]
        elif isinstance(st, (ast.For, ast.AsyncFor, ast.comprehension)):
            pairs = [(st.target, st.iter)]
        elif isinstance(st, (ast.With, ast.AsyncWith)):
            pairs = [(i.optional_vars, i.context_expr) for i in st.items if i.optional_vars is not None]
        out = []
        for t, v in pairs:
            names = {x.id for x in ast.walk(t) if isinstance(x, ast.Name)}
            if names:
                out.append((names, v))
        return out

    def _assigned(self, unit: ast.AST) -> List[Tuple[Set[str], ast.AST]]:
        """Of a function (or a statement): every place a name gets a value -- (the names, what is put into them)."""
        if not self.assigns:                                  # once for the file: each such place under every function around it
            self.assigns[0] = []
            for st in self.nodes:
                if type(st) not in _PLACES_OF_VALUES:
                    continue
                pairs = self._pairs(st)
                up = st if pairs else None
                while up is not None:
                    if isinstance(up, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        self.assigns.setdefault(id(up), []).extend(pairs)
                    up = self.parents.get(id(up))
        if id(unit) not in self.assigns:
            if isinstance(unit, (ast.FunctionDef, ast.AsyncFunctionDef)):
                return []
            self.assigns[id(unit)] = [p for st in ast.walk(unit) for p in self._pairs(st)]
        return self.assigns[id(unit)]

    def _spread(self, unit: ast.AST, seeds: Set[str]) -> Set[str]:
        """The names of a function whose value comes from these names (again and again)."""
        key = (id(unit), frozenset(seeds))
        if key not in self.spreads:
            names, grown = set(seeds), True
            while grown:
                grown = False
                for targets, value in self._assigned(unit):
                    if not targets <= names and self._leads(value, names):
                        names |= targets
                        grown = True
            self.spreads[key] = names
        return self.spreads[key]

    def _leads(self, x: Optional[ast.AST], names: Set[str], depth: int = 0) -> bool:
        """Does the value of this piece of code come from one of these names -- or from something that leads to the program's
        folder: such a name of another part of the program (updates.HERE), a value an object keeps for it (self.base), where
        the program was started from (sys.argv)? Followed through what builds a path or hands a value on (joining, cutting,
        putting into a list and taking out again, a function that gives back what it is given) -- not through a call that
        makes something else of it (reading the file, asking whether it exists)."""
        if x is None or depth > 40:
            return False
        go = lambda y: self._leads(y, names, depth + 1)       # noqa: E731
        if isinstance(x, ast.Name):
            return x.id in names
        if isinstance(x, ast.Attribute):
            if x.attr in self.home_attrs:
                return True
            root, parts = self._chain(x)
            if root in self.bound and not self.bound[root].startswith("."):
                path = ".".join([self.bound[root]] + parts).split(".")
                if path[:2] in (["sys", "argv"], ["sys", "path"]):
                    return True
                for i in range(len(path) - 1, 0, -1):
                    other = self.world.get(".".join(path[:i]))
                    if other is not None:
                        return other is not self and path[i] in other.home
                return False
            return x.attr in PATH_ATTRS and go(x.value)
        if isinstance(x, ast.Call):
            f = x.func
            args = list(x.args) + [k.value for k in x.keywords]
            if isinstance(f, ast.Name):
                if f.id in PATH_CALLS and f.id not in self.defs:
                    return any(go(a) for a in args)
                if f.id in names and f.id in self.defs:          # a function of this file that leads there (def here(): return HERE)
                    return True
                return any(go(a) for i, a in enumerate(x.args) if i in self.echo.get(f.id, ())) or \
                    any(go(k.value) for k in x.keywords if k.arg in self.echo_names.get(f.id, ()))
            if isinstance(f, ast.Lambda):
                return any(go(a) for a in args)
            if isinstance(f, ast.Attribute):
                root, parts = self._chain(f)
                if root in self.bound and not self.bound[root].startswith("."):
                    path = ".".join([self.bound[root]] + parts)
                    if path.startswith("os.path.") and path[8:] in PATH_FUNCS or path in ("os.fspath", "os.fsdecode", "os.fsencode", "pathlib.Path",
                                                                                           "pathlib.PurePath", "pathlib.PosixPath", "pathlib.PurePosixPath"):
                        return any(go(a) for a in args)
                    real = self._through(path)[0].split(".")
                    other = self.world.get(".".join(real[:-1]))
                    if other is not None:                      # a function of another part of the program
                        return real[-1] in other.home or any(go(a) for i, a in enumerate(x.args) if i in other.echo.get(real[-1], ())) or \
                            any(go(k.value) for k in x.keywords if k.arg in other.echo_names.get(real[-1], ()))
                    return False
                if f.attr in self.home_attrs:                  # self.here()
                    return True
                return f.attr in PATH_METHODS and (go(f.value) or any(go(a) for a in args))
            return False
        if isinstance(x, ast.BinOp):
            return go(x.left) or go(x.right)
        if isinstance(x, ast.JoinedStr):
            return any(go(v.value) for v in x.values if isinstance(v, ast.FormattedValue))
        if isinstance(x, (ast.Subscript, ast.Starred, ast.NamedExpr, ast.Await)):
            return go(x.value)
        if isinstance(x, (ast.Tuple, ast.List, ast.Set)):
            return any(go(e) for e in x.elts)
        if isinstance(x, ast.Dict):
            return any(go(e) for e in x.values)
        if isinstance(x, ast.IfExp):
            return go(x.body) or go(x.orelse)
        if isinstance(x, ast.BoolOp):
            return any(go(e) for e in x.values)
        if isinstance(x, (ast.ListComp, ast.GeneratorExp, ast.SetComp)):
            return go(x.elt) or any(go(g.iter) for g in x.generators)
        return False

    def _written(self, call: ast.Call) -> Optional[List[ast.AST]]:
        """Of a call that (may) write a file: the pieces that say where. None: it does not write."""
        f, args = call.func, list(call.args)
        kws = {k.arg: k.value for k in call.keywords if k.arg}

        def reads(mode: Optional[ast.AST]) -> bool:
            if mode is None:
                return True
            v = self._fixed(mode)
            return isinstance(v, str) and bool(READ_MODE.match(v))

        if isinstance(f, ast.Name):
            if f.id == "open" and f.id not in self.bound and f.id not in self.defs:
                return None if reads(args[1] if len(args) > 1 else kws.get("mode")) else args[:1] + [v for k, v in kws.items() if k == "file"]
            return None
        if not isinstance(f, ast.Attribute):
            return None
        root, parts = self._chain(f)
        if root in self.bound and parts and not self.bound[root].startswith("."):
            path = ".".join([self.bound[root]] + parts)
            for mod, names in WRITERS.items():
                if path.startswith(mod + ".") and path[len(mod) + 1:] in names:
                    if path in WRITER_MODES and reads(args[1] if len(args) > 1 else kws.get("mode")):
                        return None
                    return args + [v for k, v in kws.items() if k != "mode"]
            if path.split(".")[0] in HARMLESS and not path.startswith("pathlib."):
                return None                                    # another function of a harmless part (os.path.join, json.dump ...)
        if f.attr not in WRITE_METHODS:
            return None
        if f.attr == "open":                                   # x.open("w"), x.open(name, "w") -- not x.open() or x.open(name)
            modes = [a for a in args[:2] + [kws[k] for k in ("mode",) if k in kws] if isinstance(self._fixed(a), str) and re.fullmatch(r"[rwxabt+U]{1,4}", self._fixed(a))]
            if not modes and not any(self._fixed(a) is None for a in args[:1] + [kws[k] for k in ("mode",) if k in kws]) or modes and all(reads(m) for m in modes):
                return None
        if f.attr in ("replace", "rename") and (len(args) != 1 or kws):
            return None                                        # (a text's replace takes two)
        return [f.value] + args + list(kws.values())

    def _writes(self) -> None:
        seeds = self.home | {HOME_NAME}
        for st in self.nodes:                                  # self.base = HERE: a value an object keeps for the program's folder
            if isinstance(st, ast.Assign) and self._leads(st.value, seeds):
                self.home_attrs.update(t.attr for t in st.targets if isinstance(t, ast.Attribute))
        self.written: List[Tuple[ast.Call, List[ast.AST]]] = []
        for call in self.calls:
            where = self._written(call)
            if where:
                self.written.append((call, where))
        for call, where in self.written:
            self._write_at(call, where, "")

    def _fn(self, node: ast.AST) -> Optional[ast.AST]:
        """The function a piece of code stands in (of functions inside functions the outermost), or None."""
        fn, up = None, self.parents.get(id(node))
        while up is not None:
            if isinstance(up, (ast.FunctionDef, ast.AsyncFunctionDef)):
                fn = up
            up = self.parents.get(id(up))
        return fn

    def _write_at(self, call: ast.Call, where: List[ast.AST], through: str) -> bool:
        """One place that writes (through: by way of a function that writes where it is told): a find when the path leads to
        the program's folder; and when it comes from what the function around it is given, that function writes where it is
        told, too. True when the latter is new."""
        fn = self._fn(call)
        scope: ast.AST = fn if fn is not None else self._unit(call)[0]
        seeds = self.home | {HOME_NAME}
        if id(call) not in self.self_hits and any(self._leads(e, self._spread(scope, seeds)) for e in where):
            self.self_hits.add(id(call))
            self._hit(call, "self", through or "write", [])
        if fn is None:
            return False
        a = fn.args
        given = [x.arg for x in a.posonlyargs + a.args]
        if id(fn) in self.methods and given and given[0] in ("self", "cls"):
            given = given[1:]
        every = given + [x.arg for x in a.kwonlyargs] + [x.arg for x in (a.vararg, a.kwarg) if x]
        goes = {g for g in every if any(self._leads(e, self._spread(scope, {g})) for e in where)}
        old = self.writers.get(id(fn))
        if goes and (old is None or not goes <= old[2]):
            self.writers[id(fn)] = (fn.name, given, goes | (old[2] if old else set()))
            return True
        return False

    def written_through(self, writers: Dict[str, Dict[str, list]], methods: Dict[str, list]) -> bool:
        """Finds where this file calls a function (of any file) that writes where it is told, and treats that call as a place
        that writes there. True when a function of this file turned out to be such a function, too."""
        added = False
        mine = writers.get(self.rel, {})
        for call in self.calls:
            f = call.func
            defs: list = []
            if isinstance(f, ast.Name):
                defs = mine.get(f.id, [])
            elif isinstance(f, ast.Attribute):
                root, parts = self._chain(f)
                if root in self.bound and parts and not self.bound[root].startswith("."):
                    path = self._through(".".join([self.bound[root]] + parts))[0].split(".")
                    if len(path) >= 2:
                        defs = writers.get("/".join(path[:-1]) + ".py", {}).get(path[-1], [])
                elif f.attr in methods:
                    defs = methods[f.attr]
            if not defs:
                continue
            where: List[ast.AST] = []
            for _name, given, goes in defs:
                where += [x for i, x in enumerate(call.args) if isinstance(x, ast.Starred) or i < len(given) and given[i] in goes or i >= len(given)]
                where += [k.value for k in call.keywords if k.arg is None or k.arg in goes]
            if where and self._write_at(call, where, "→ " + defs[0][0]):
                added = True
        return added

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
        places = [st for st in ast.walk(unit) if isinstance(st, (ast.Assign, ast.AnnAssign, ast.AugAssign, ast.For, ast.NamedExpr, ast.With))]
        while grown:
            grown = False
            for st in places:
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
            exprs = [e for n, k, _w in found if k not in ("place", "self") for e in self.deciding.get(id(n), [])]
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
            kind = "detour" if "detour" in kinds else "place" if kinds == ["place"] else "self" if set(kinds) <= {"place", "self"} else "call"
            first = min(found, key=lambda f: (getattr(f[0], "lineno", 0), getattr(f[0], "col_offset", 0)))
            call = first[0]
            while isinstance(self.parents.get(id(call)), (ast.Attribute, ast.Call)) and getattr(self.parents[id(call)], "func", call) is call:
                call = self.parents[id(call)]
            # for the page (nothing of it is compared): the lines, the name, the way out, the places named, whether a detour is
            # only a word that carries an approval
            way = self.way(uid)
            more = {"way": way, "args": sorted({w for _n, k, w in found if k == "place"}),
                    "words": all(w in ["%r" % x for x in WORDS.get(self.rel, ())] + [x + "=" for x in WORDS.get(self.rel, ())]
                                 for _n, k, w in found if k == "detour")}
            if id(unit) in self.heads:
                head = self.parents[id(unit)]                  # its first line: up to where its body begins
                body = getattr(head.body[0], "lineno", head.end_lineno + 1) if head.body else head.end_lineno + 1
                self._note(kind, qual, _same(unit), "%s: %s" % (qual, _show(call, 90)),
                           dict(more, spans=[((_span(head) or (head.lineno, 0))[0], max(head.lineno, body - 1))], name=head.name, where=qual))
            elif isinstance(unit, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._note(kind, qual, _same(unit), "%s: %s" % (qual, _show(call, 90)), _at(unit, name=unit.name, where=qual, **more))
                feeds = {"feeds": [qual], "way": way}
                # what reaches those places from outside the function: names set at the top of the file and small functions of
                # the file whose result goes into them (directly, or through a name of the function) ...
                feeding, names = self._feeding(unit, [n for n, _k, _w in found])
                # ... and what decides whether they are reached at all (if bind_allowed(x): ..., if ext in DOCUMENTS: ...)
                tests = [n.test for n in ast.walk(unit) if isinstance(n, (ast.If, ast.While, ast.IfExp, ast.Assert))]
                names |= {n.id for t in tests for n in ast.walk(t) if isinstance(n, ast.Name)}
                for name in sorted(names):
                    if name in tops and name not in ("log", "logger"):
                        for st in tops[name]:
                            self._note("around", name, _same(st), _show(st), _at(st, name=name, where=name, **feeds))
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
                                    self._note("around", name + "()", _same(d), "%s() → %s" % (name, qual), _at(d, name=name, where=name + "()", **feeds))
                                    todo.append(d)             # and the small functions that one calls in turn
                                    for x in ast.walk(d):      # ... with the names from the top of the file it uses
                                        if isinstance(x, ast.Name) and x.id in tops and x.id not in ("log", "logger"):
                                            for st2 in tops[x.id]:
                                                self._note("around", x.id, _same(st2), _show(st2), _at(st2, name=x.id, where=x.id, **feeds))
            else:
                target = [t.id for st in [unit] if isinstance(st, (ast.Assign, ast.AnnAssign))
                          for t in (st.targets if isinstance(st, ast.Assign) else [st.target]) if isinstance(t, ast.Name)]
                self._note(kind, (qual + " " if qual else "") + _show(unit, 200), show=_show(call if kind != "place" else unit, 100),
                           info=_at(unit, name=(target or [""])[0], where=qual or (target or [""])[0], **more))
        for name in RULES.get(self.rel, ()):                   # rules that keep Kontor to itself: each as a whole
            for d in defs.get(name, []):
                self._note("rule", name, _same(d), "%s()" % name, _at(d, name=name, where=name + "()"))
            for st in tops.get(name, []):                      # ... a setting at the top of the file
                self._note("rule", name, _same(st), _show(st), _at(st, name=name, where=name))
            if name in tops:                                   # ... and what else at the top touches it (NAME.clear(), y = NAME)
                for st in self.tree.body:
                    if st not in tops[name] and not isinstance(st, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Import, ast.ImportFrom)) \
                            and any(isinstance(x, ast.Name) and x.id == name for x in ast.walk(st)):
                        self._note("rule", name, _same(st), _show(st), _at(st, name=name, where=name))
        self._rule_changes()
        self._sources()
        if _own(self.rel):
            self._note("guard", "", _same(self.tree), self.rel)

    def _rule_changes(self) -> None:
        """What changes a rule from anywhere, in this file: NAME.clear(), NAME[k] = v, del NAME[k], NAME += ..., global NAME,
        module.NAME = v or module.NAME.update(...) (also through an import, also of this very file), x.__dict__["NAME"] = v --
        each a finding of that rule (in another file than the rule's own: a rule nobody judged, a risk)."""
        files = {_module(r): r for r in RULES}

        def scope(node: ast.AST) -> Optional[ast.AST]:
            up = self.parents.get(id(node))
            while up is not None and not isinstance(up, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
                up = self.parents.get(id(up))
            return up

        def own(node: ast.Name) -> bool:
            """This file's rule by its name -- not a name of the same spelling that a function keeps for itself."""
            f = scope(node)
            if f is None or isinstance(f, ast.ClassDef):
                return True
            inner = [x for x in ast.walk(f) if x is not f]
            if any(isinstance(x, (ast.Global, ast.Nonlocal)) and node.id in x.names for x in inner):
                return True
            args = f.args if not isinstance(f, ast.ClassDef) else None
            names = {a.arg for a in (args.posonlyargs + args.args + args.kwonlyargs + [x for x in (args.vararg, args.kwarg) if x])} if args else set()
            return node.id not in names and not any(isinstance(x, ast.Name) and x.id == node.id and not isinstance(x.ctx, ast.Load) for x in inner)

        def rule(node: ast.AST) -> Optional[str]:
            if isinstance(node, ast.Name):
                path = self.bound.get(node.id, "").lstrip(".")
                mod, _dot, nm = path.rpartition(".")
                if mod and nm in RULES.get(files.get(mod, ""), ()):
                    return nm
                return node.id if not path and node.id in RULES.get(self.rel, ()) and own(node) else None
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
                mod = self.bound.get(node.value.id, "").lstrip(".")
                if node.attr in RULES.get(files.get(mod, ""), ()):
                    return node.attr
            return None

        def down(x: ast.AST) -> List[ast.AST]:
            """x and what it is part of: NAME["a"]["b"] -> itself, NAME["a"], NAME (each may name a rule)."""
            out = [x]
            while isinstance(x, (ast.Attribute, ast.Subscript)):
                x = x.value
                out.append(x)
            return out

        def changed(n: ast.AST) -> List[ast.AST]:
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in MUTATORS:
                return down(n.func.value)
            if isinstance(n, (ast.Name, ast.Attribute, ast.Subscript)) and isinstance(n.ctx, (ast.Store, ast.Del)) \
                    and isinstance(self.parents.get(id(n)), (ast.Assign, ast.AugAssign, ast.AnnAssign, ast.Delete)):
                return down(n)
            return []

        for n in self.nodes:
            names: List[str] = []
            if isinstance(n, (ast.Global, ast.Nonlocal)):
                names = [x for x in n.names if x in RULES.get(self.rel, ())]
            elif isinstance(n, ast.Subscript) and isinstance(n.ctx, (ast.Store, ast.Del)) and self._table(n.value):
                key = _text_of(self._fixed(n.slice))
                names = [key] if key and any(key in v for v in RULES.values()) else []
            else:
                names = sorted({x for x in (rule(c) for c in changed(n)) if x})
            if not names:
                continue
            st, up = n, self.parents.get(id(n))
            while not isinstance(st, ast.stmt) and up is not None:
                st, up = up, self.parents.get(id(up))
            for name in names:
                if st not in self.tops.get(name, []) or isinstance(st, ast.AugAssign):
                    self._note("rule", name, _same(st), _show(st), _at(st, name=name, where=name))

    def ways_known(self) -> None:
        """For the page, before any file is recorded (see way): of each place that reaches out, the Internet addresses its
        function names, the programs it starts as far as they are fixed, whether it connects, what it hands things on to."""
        for uid, found in self.hits.items():
            unit, _qual = self.units[uid]
            hosts: Set[str] = set()
            programs: Set[str] = set()
            passes: List[str] = []
            net = unknown = False
            for node, kind, what in found:
                if kind in ("place", "self"):
                    continue
                if what.startswith("→ "):
                    passes.append(what[2:])
                    continue
                root = what.split(".")[0]
                net = net or root in NET
                call = self.parents.get(id(node))
                if isinstance(call, ast.Call) and call.func is node and (root == "subprocess" or root in RISKY_START and bool(RISKY_START[root].match(what[len(root) + 1:]))):
                    first = call.args[0] if call.args else None
                    if isinstance(first, (ast.List, ast.Tuple)):
                        first = first.elts[0] if first.elts else None
                    prog = _text_of(self._fixed(first)) if first is not None else None
                    if prog:
                        programs.add(prog.rstrip("/").rsplit("/", 1)[-1][:40])
                    else:
                        unknown = True
            names = {n.id for n in ast.walk(unit) if isinstance(n, ast.Name)}
            texts = [n.value for n in ast.walk(unit) if isinstance(n, ast.Constant) and isinstance(n.value, str)]
            texts += [t for t in (_text_of(self._fixed(self.consts[x])) for x in sorted(names) if x in self.consts) if t]
            for text in texts:
                for a in ADDRESS.findall(text):
                    m = HOST.search(a)
                    host = (m.group(1) if m else "").lower()
                    if host and host not in NAMESPACES and not OWN_ADDRESSES.match(host) and host != "localhost":
                        hosts.add(host)
            self.direct[uid] = (sorted(hosts), sorted(programs), passes, net, unknown)

    def way(self, uid: int, depth: int = 0) -> List[str]:
        """The way out a place uses, for the page: [kind, what] -- "host" (the Internet addresses its function names), "program"
        (the programs it starts, as far as they are fixed; else the file that starts one), "net" (a connection without a fixed
        address), or "other" (the function it hands things on to, followed to that one's way where it can be). Only to say it
        in words: it decides nothing of what is asked about."""
        if uid not in self.direct:
            return ["other", ""]
        hosts, programs, passes, net, unknown = self.direct[uid]
        qual = self.units[uid][1]
        if hosts:
            return ["host", ", ".join(hosts[:3])]
        if programs:
            return ["program", ", ".join(programs[:3])]
        for target in passes:                                  # handed on: the way of the function it goes to
            other, name = self, target
            if "." in target:
                mod, name = target.rsplit(".", 1)
                other = self.world.get(mod.lstrip("."), None) if mod else None
            for p in ([other] if other is not None else list(self.world.values())) if depth < 4 else []:
                for vid, (_u, q) in p.units.items():
                    if vid in p.direct and (q.split(".")[-1] == name or q.endswith("." + name + ".__init__") or q == name + ".__init__"):
                        w = p.way(vid, depth + 1)
                        if w[0] != "other":
                            return w
            return ["other", target.lstrip(".")[:60]]
        if unknown:                                            # a program not fixed in the code: by the file that starts it
            return ["program", self.rel]
        return ["net", qual] if net else ["other", qual]

    def _sources(self) -> None:
        """Where something is fetched from: each fixed text given to a key or a name like "repo" -- in a table ({"repo": ..}), set
        to a name (RUNTIME_REPO = ..), handed over (repo=..), as the default of an argument, or as what stands in for a value
        read under that key (x.get("repo") or ..). Kept as an address: another one is new, the same one again is not."""
        def named(t: Optional[ast.AST]) -> bool:
            if isinstance(t, ast.Name):
                return bool(SOURCE.search(t.id))
            if isinstance(t, ast.Attribute):
                return bool(SOURCE.search(t.attr))
            if isinstance(t, ast.Subscript):
                return bool(SOURCE.search(_text_of(self._fixed(t.slice)) or ""))
            return isinstance(t, ast.Constant) and isinstance(t.value, str) and bool(SOURCE.search(t.value))

        def read(v: ast.AST) -> bool:                        # x.get("repo"), x["repo"]
            if isinstance(v, ast.Call) and isinstance(v.func, ast.Attribute) and v.func.attr in ("get", "pop", "setdefault") and v.args:
                return named(v.args[0]) or bool(SOURCE.search(_text_of(self._fixed(v.args[0])) or ""))
            return isinstance(v, ast.Subscript) and named(v)

        given: List[ast.AST] = []
        for n in self.nodes:
            if type(n) not in _SOURCE_PLACES:
                continue
            if isinstance(n, ast.Dict):
                given += [v for k, v in zip(n.keys, n.values) if k is not None and named(k)]
            elif isinstance(n, (ast.Assign, ast.AnnAssign)) and n.value is not None:
                if any(named(t) for t in (n.targets if isinstance(n, ast.Assign) else [n.target])):
                    given.append(n.value)
            elif isinstance(n, ast.keyword) and n.arg and SOURCE.search(n.arg):
                given.append(n.value)
            elif isinstance(n, ast.arguments):
                pos = n.posonlyargs + n.args
                given += [d for a, d in zip(pos[len(pos) - len(n.defaults):], n.defaults) if SOURCE.search(a.arg)]
                given += [d for a, d in zip(n.kwonlyargs, n.kw_defaults) if d is not None and SOURCE.search(a.arg)]
            elif isinstance(n, ast.BoolOp) and any(read(v) for v in n.values):
                given += [v for v in n.values if not read(v)]
        for v in given:
            for leaf in (v.values if isinstance(v, ast.BoolOp) else [v.body, v.orelse] if isinstance(v, ast.IfExp) else [v]):
                where = _text_of(self._fixed(leaf))
                if where:
                    self._note("address", where, show="repo: " + where)


_CODING = re.compile(rb"^[ \t\f]*#.*?coding[:=][ \t]*([-\w.]+)")


def _py_text(data: bytes) -> str:
    """A Python file's text as Python reads it -- only UTF-8: a declaration of another encoding in its first two lines (which
    Python obeys, utf-7 among them: code hidden in what reads as a comment) makes the file unreadable here (ValueError)."""
    for line in re.split(rb"\r\n|\r|\n", data, maxsplit=2)[:2]:
        m = _CODING.match(line)
        if m and m.group(1).decode("ascii", "replace").lower().replace("_", "-") not in ("utf-8", "utf8"):
            raise ValueError("encoding " + m.group(1).decode("ascii", "replace"))
    return data.decode("utf-8")


def _analyse(files: Dict[str, bytes], names: List[str], local: Set[str]) -> Tuple[List[_Py], List[str], List[str]]:
    """The program files read and followed through: (each file, the files no reader of Python understands, methods that hand
    things on but have a name every list or text has -- those cannot be followed)."""
    parsed: List[_Py] = []
    unreadable: List[str] = []
    common: List[str] = []
    world: Dict[str, _Py] = {}
    for rel in names:
        try:
            parsed.append(_Py(rel, ast.parse(_py_text(files[rel])), local, world))
            world[_module(rel)] = parsed[-1]
        except (SyntaxError, ValueError, UnicodeDecodeError, RecursionError, MemoryError):
            unreadable.append(rel)
    for _ in range(20):                                        # names for what reaches out, also through other files
        if not any([p.aliases() for p in parsed]):
            break
    for p in parsed:
        p.find()
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
    # a function that writes where it is told: a call that tells it the program's own folder is such a place, too
    for _ in range(8):
        writers: Dict[str, Dict[str, list]] = {}
        told: Dict[str, list] = {}
        for p in parsed:
            for fid, entry in p.writers.items():
                if fid in p.methods:
                    if entry[0] not in COMMON:
                        told.setdefault(entry[0], []).append(entry)
                else:
                    writers.setdefault(p.rel, {}).setdefault(entry[0], []).append(entry)
        if not any([p.written_through(writers, told) for p in parsed]):
            break
    return parsed, unreadable, common


def _module(rel: str) -> str:
    """The name a program file is imported with: a.py -> a, pkg/__init__.py -> pkg, pkg/b.py -> pkg.b."""
    parts = rel[:-3].split("/")
    return ".".join(parts[:-1] if parts[-1] == "__init__" and len(parts) > 1 else parts)


def _python(files: Dict[str, bytes], names: List[str], local: Set[str], out: dict, shown: dict, info: Optional[dict] = None) -> None:
    parsed, unreadable, _common = _analyse(files, names, local)
    for rel in unreadable:
        out[("unreadable", rel, "")] = _sha(files[rel])
        shown[("unreadable", rel, "")] = rel
    for p in parsed:                                           # (for the page: what each way out uses, read across files)
        p.ways_known()
    for p in parsed:
        p.record()
        out.update(p.out)
        shown.update(p.shown)
        if info is not None:
            info.update(p.info)


def handing_on(files: Dict[str, bytes]) -> Dict[str, object]:
    """For looking at the program as it is (tests): which functions hand what they are given on to a place that reaches out
    ({file: {name: [what of it]}}), and which of them cannot be followed because of their name."""
    names = sorted(r for r in files if installable(r) and r.lower().endswith(".py"))
    parsed, _unreadable, common = _analyse(files, names, _local(names))
    return {"functions": {p.rel: {e[0]: sorted(e[2]) for e in p.passing.values()} for p in parsed if p.passing}, "common": sorted(common),
            "names": {p.rel: sorted(p.defs) + sorted(n.name for n in p.nodes if isinstance(n, ast.ClassDef)) + sorted(p.tops) for p in parsed},
            "writers": {p.rel: {e[0]: sorted(e[2]) for e in p.writers.values()} for p in parsed if p.writers}}


def _local(names: Iterable[str]) -> Set[str]:
    """The program's own parts by the name they are imported with."""
    return {r.split("/")[0][:-3] if "/" not in r else r.split("/")[0] for r in names if r.endswith(".py")}


# ---------------------------------------------------------------------------
# helpers and scripts: their lines without comments
# ---------------------------------------------------------------------------

class _Unclean(Exception):
    """A helper or script that could not be followed to its end as its language reads it: then its comments stay (every
    line counts -- rather a finding too many than code taken for a comment)."""


class _Lines:
    """The lines of a helper or script as they are compared: code with its spaces put together and without comments, the
    text of a string as it is written (a line inside a text over several lines keeps its indentation)."""

    def __init__(self) -> None:
        self.lines: List[str] = []
        self.cur: List[str] = []
        self.inside = False                                   # the line began inside a text over several lines

    def code(self, c: str) -> None:
        if c == "\n":
            self.end(False)
        elif c.isspace():
            if self.cur and self.cur[-1] != " ":
                self.cur.append(" ")
        else:
            self.cur.append(c)

    def text(self, chars: str) -> None:
        for c in chars:
            if c == "\n":
                self.end(True)
            elif c != "\r":
                self.cur.append(c)

    def end(self, inside: bool) -> None:
        line = "".join(self.cur)
        line = line.rstrip() if self.inside else line.strip()
        if line or self.inside:
            self.lines.append(line)
        self.cur, self.inside = [], inside

    def done(self) -> List[str]:
        self.end(False)
        return self.lines


def _swift_lines(t: str) -> List[str]:
    """Swift: // and /* */ (nested) are comments; texts in quotes (one or three, raw ones with #) are kept as written, with
    what is put into them (a backslash and parentheses) code again."""
    o, i, n = _Lines(), 0, len(t)
    back: List[Tuple[int, bool, int]] = []                    # the texts around an interpolation: (#s, over lines, parentheses)
    mode, hashes, multi, parens = "code", 0, False, 0
    while i < n:
        c = t[i]
        if mode == "code":
            if t.startswith("//", i) and (i == 0 or t[i - 1] != "\\"):
                j = t.find("\n", i)
                i = n if j < 0 else j
                continue
            if t.startswith("/*", i):
                start, depth, i = i, 1, i + 2
                while i < n and depth:
                    if t.startswith("/*", i):
                        depth, i = depth + 1, i + 2
                    elif t.startswith("*/", i):
                        depth, i = depth - 1, i + 2
                    else:
                        i += 1
                if depth:
                    raise _Unclean()
                o.code("\n" if "\n" in t[start:i] else " ")      # (a comment over lines still ends the line)
                continue
            if c in "#\"":
                k = i
                while k < n and t[k] == "#":
                    k += 1
                if k < n and t[k] == '"':
                    hashes, multi = k - i, t.startswith('"""', k)
                    end = k + (3 if multi else 1)
                    o.text(t[i:end])
                    i, mode = end, "text"
                    continue
            if back and c == "(":
                parens += 1
            elif back and c == ")":
                if parens == 0:
                    hashes, multi, parens = back.pop()
                    o.text(c)
                    i, mode = i + 1, "text"
                    continue
                parens -= 1
            o.code(c)
            i += 1
            continue
        close = ('"""' if multi else '"') + "#" * hashes
        if t.startswith(close, i):
            o.text(close)
            i, mode = i + len(close), "code"
            continue
        esc = "\\" + "#" * hashes
        if t.startswith(esc, i):
            j = i + len(esc)
            if j < n and t[j] == "(":
                back.append((hashes, multi, parens))
                o.text(t[i:j + 1])
                i, mode, parens = j + 1, "code", 0
                continue
            if hashes == 0 or j < n:
                o.text(t[i:j + 1])
                i = j + 1
                continue
        if c == "\n" and not multi:
            raise _Unclean()                                 # a text that does not end on its line
        o.text(c)
        i += 1
    if mode != "code" or back:
        raise _Unclean()
    return o.done()


_JS_BEFORE_PATTERN = frozenset("(,=:[!&|?{};+-*%<>~^")
_JS_WORDS = frozenset(("return", "typeof", "case", "do", "else", "in", "of", "new", "delete", "void", "throw", "instanceof", "yield", "await"))


def _js_walk(t: str, i: int = 0):
    """JavaScript, character by character as the language reads it: (position, character, whether it is code). Comments come
    as one space; texts ('..', "..", `..` with ${...} code again inside) and patterns (/../) as they are written."""
    n = len(t)
    open_tpl: List[int] = []                                 # template texts waiting for their ${...} to close: braces then
    braces, last, word = 0, "", ""
    mode, quote = "code", ""
    while i < n:
        c = t[i]
        if mode == "code":
            if t.startswith("//", i) and (i == 0 or t[i - 1] != "\\"):
                j = t.find("\n", i)
                i = n if j < 0 else j
                continue
            if t.startswith("/*", i):
                j = t.find("*/", i + 2)
                if j < 0:
                    raise _Unclean()
                yield i, "\n" if "\n" in t[i:j] else " ", True       # (a comment over lines still ends the line)
                i = j + 2
                continue
            if c in "'\"`":
                mode, quote, word = ("tpl" if c == "`" else "text"), c, ""
                yield i, c, False
                i += 1
                continue
            if c == "/" and (last == "" or last in _JS_BEFORE_PATTERN or last in _JS_WORDS):
                j, inside = i + 1, False
                while j < n:
                    d = t[j]
                    if d == "\\":
                        j += 2
                        continue
                    if d == "\n":
                        raise _Unclean()
                    if d == "[":
                        inside = True
                    elif d == "]":
                        inside = False
                    elif d == "/" and not inside:
                        break
                    j += 1
                if j >= n:
                    raise _Unclean()
                for k in range(i, j + 1):
                    yield k, t[k], False
                i, last, word = j + 1, "x", ""
                continue
            if c == "{":
                braces += 1
            elif c == "}":
                if open_tpl and braces == open_tpl[-1]:
                    open_tpl.pop()
                    mode, quote = "tpl", "`"
                    yield i, c, False
                    i += 1
                    continue
                braces -= 1
            yield i, c, True
            if c.isalnum() or c in "_$":
                word += c
                last = word
            elif not c.isspace():
                word, last = "", c
            else:
                word = ""
            i += 1
        elif c == "\\":
            yield i, c, False
            if i + 1 < n:
                yield i + 1, t[i + 1], False
            i += 2
        elif mode == "text":
            if c == "\n":
                raise _Unclean()
            yield i, c, False
            i += 1
            if c == quote:
                mode, last = "code", "x"
        else:                                                # a template text
            if c == "`":
                yield i, c, False
                i, mode, last = i + 1, "code", "x"
            elif t.startswith("${", i):
                yield i, "$", False
                yield i + 1, "{", False
                open_tpl.append(braces)
                i, mode, last, word = i + 2, "code", "{", ""
            else:
                yield i, c, False
                i += 1
    if mode != "code" or open_tpl:
        raise _Unclean()


def _js_lines(t: str) -> List[str]:
    o = _Lines()
    for _i, c, code in _js_walk(t):
        (o.code if code else o.text)(c)
    return o.done()


def _js_definition(t: str, start: int) -> int:
    """Where the definition starting here ends: a function at the brace that closes its body, anything else (const x = ...)
    at the semicolon after it -- both outside any bracket, text or comment."""
    depth, body = 0, t.startswith("function", start) or t.startswith("async", start)
    for i, c, code in _js_walk(t, start):
        if not code:
            continue
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
            if body and c == "}" and depth == 0:
                return i + 1
        elif c == ";" and depth == 0 and not body:
            return i + 1
    raise _Unclean()


def _page_rules(rel: str, text: str, spans: Optional[Dict[str, list]] = None) -> Dict[str, List[str]]:
    """The functions and settings of a page named in PAGE_RULES: {name: [each definition, without comments and space]}
    (spans: filled with the lines each stands on, for the page)."""
    out: Dict[str, List[str]] = {}
    for name in PAGE_RULES.get(rel, ()):
        for m in re.finditer(r"(?m)^[ \t]*(?:(?:async[ \t]+)?function[ \t]*\*?[ \t]*%s[ \t]*\(|(?:const|let|var)[ \t]+%s[ \t]*=)" % (name, name), text):
            start = m.start() + len(m.group(0)) - len(m.group(0).lstrip())
            try:
                end = _js_definition(text, start)
                body = "\n".join(_js_lines(text[start:end]))
            except _Unclean:
                end = len(text)
                body = text[start:]                          # not to be followed: everything from here on counts
            out.setdefault(name, []).append(body)
            if spans is not None:
                spans.setdefault(name, []).append((text.count("\n", 0, start) + 1, text.count("\n", 0, max(start, end - 1)) + 1))
    return out


def _sh_lines(t: str) -> List[str]:
    """A shell script: # at the start of a word is a comment (not the first line's #!); '..', "..", `..`, $'..', ${..} and the
    text of a here-document (<<WORD ... WORD) are kept as written, $( ... ) inside "..." is code again."""
    o, i, n = _Lines(), 0, len(t)
    if t.startswith("#!"):
        j = t.find("\n")
        j = n if j < 0 else j
        for c in t[:j]:
            o.code(c)
        i = j
    back: List[Tuple[str, str, int]] = []                    # (what was opened, the mode to go back to, parentheses then)
    mode, parens = "code", 0
    later: List[Tuple[str, bool]] = []                       # here-documents that begin after this line: (word, tabs left out)

    def upto(close: str, j: int, escapes: bool = True) -> int:
        while j < n:
            if escapes and t[j] == "\\":
                j += 2
                continue
            if t[j] == close:
                return j
            j += 1
        raise _Unclean()

    def braced(j: int) -> int:                               # ${ ... } with what is nested in it
        depth = 0
        while j < n:
            if t[j] == "\\":
                j += 2
                continue
            if t.startswith("${", j):
                depth, j = depth + 1, j + 2
                continue
            if t[j] in "'\"":
                j = upto(t[j], j + 1, t[j] == '"') + 1
                continue
            if t[j] == "}":
                depth -= 1
                if depth == 0:
                    return j
            j += 1
        raise _Unclean()

    while i < n:
        c = t[i]
        if mode == "code":
            if c == "\n":
                o.code(c)
                i += 1
                for word, tabs in later:                     # the here-documents, kept as they are
                    while True:
                        if i >= n:
                            raise _Unclean()
                        j = t.find("\n", i)
                        j = n if j < 0 else j
                        line = t[i:j]
                        i = j + 1
                        if (line.lstrip("\t") if tabs else line) == word:
                            for d in line + "\n":
                                o.code(d)
                            break
                        o.text(line + "\n")
                later = []
                continue
            if c == "#" and (i == 0 or t[i - 1] in " \t\n;&|()<>"):
                j = t.find("\n", i)
                i = n if j < 0 else j
                continue
            if c == "\\":
                o.text(t[i:i + 2])
                i += 2
                continue
            if c == "'" or t.startswith("$'", i):
                k = i + (2 if c == "$" else 1)
                j = upto("'", k, c == "$")
                o.text(t[i:j + 1])
                i = j + 1
                continue
            if c == "`":
                j = upto("`", i + 1)
                o.text(t[i:j + 1])
                i = j + 1
                continue
            if t.startswith("${", i):
                j = braced(i)
                o.text(t[i:j + 1])
                i = j + 1
                continue
            if c == '"':
                back.append(('"', "code", parens))
                o.text(c)
                i, mode = i + 1, "dq"
                continue
            if t.startswith("$(", i):
                arith = t.startswith("$((", i)
                back.append(("((" if arith else "(", "code", parens))
                o.text(t[i:i + (3 if arith else 2)])
                i, parens = i + (3 if arith else 2), 1 if arith else 0
                continue
            if c == "(":
                parens += 1
            elif c == ")":
                if parens > 0:
                    parens -= 1
                elif back and back[-1][0] in ("(", "(("):
                    _what, mode, parens = back.pop()
                    o.text(c)
                    i += 1
                    continue
            elif t.startswith("<<", i) and not t.startswith("<<<", i) and not any(b[0] == "((" for b in back):
                j = i + 2
                tabs = t.startswith("-", j)
                j += tabs
                while j < n and t[j] in " \t":
                    j += 1
                if j < n and t[j] in "'\"":
                    k = upto(t[j], j + 1, False)
                    word, j = t[j + 1:k], k + 1
                else:
                    m = re.match(r"[^\s;&|<>()]+", t[j:])
                    if not m:
                        raise _Unclean()
                    word, j = m.group(0).replace("\\", "").replace("'", "").replace('"', ""), j + len(m.group(0))
                later.append((word, tabs))
                for d in t[i:j]:
                    o.code(d)
                i = j
                continue
            o.code(c)
            i += 1
            continue
        # inside "..."
        if c == "\\":
            o.text(t[i:i + 2])
            i += 2
        elif c == '"':
            o.text(c)
            _what, mode, parens = back.pop()
            i += 1
        elif t.startswith("$(", i):
            arith = t.startswith("$((", i)
            back.append(("((" if arith else "(", "dq", parens))
            o.text(t[i:i + (3 if arith else 2)])
            i, mode, parens = i + (3 if arith else 2), "code", 1 if arith else 0
        elif c == "`":
            j = upto("`", i + 1)
            o.text(t[i:j + 1])
            i = j + 1
        elif t.startswith("${", i):
            j = braced(i)
            o.text(t[i:j + 1])
            i = j + 1
        else:
            o.text(c)
            i += 1
    if mode != "code" or back or later:
        raise _Unclean()
    return o.done()


LINES = "lines:"                    # the content kept of a helper or script: its lines (not only a fingerprint), to say what changed


def _script(rel: str, data: bytes) -> str:
    """What is kept of a helper or script: its lines without comments and empty space (LINES first); a file that is no text
    by its fingerprint."""
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return _sha(data)
    low = rel.lower()
    read = _swift_lines if low.endswith(".swift") else _js_lines if low.endswith(".jxa") else _sh_lines
    try:
        lines = read(text)
    except (_Unclean, RecursionError):
        lines = [x.rstrip() for x in text.splitlines() if x.strip()]
    return LINES + "\n" + "\n".join(lines)


def _script_change(rel: str, before: Optional[str], after: str) -> Dict[str, object]:
    """How a helper or script changes: lines added and taken away (in any order), how many of the changed lines reach out as
    far as fixed patterns can tell, and one of them to show (+ new, - taken away)."""
    a = before.split("\n")[1:] if before and before.startswith(LINES) else []
    b = after.split("\n")[1:]
    added, removed = sum((Counter(b) - Counter(a)).values()), sum((Counter(a) - Counter(b)).values())
    now, gone = [], []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag != "equal":
            gone += a[i1:i2]
            now += b[j1:j2]
    out = OUT[next(e for e in SCRIPTS if rel.lower().endswith(e))]
    shown = next(("+ " + x for x in now if out.search(x)), None) or next(("- " + x for x in gone if out.search(x)), None) or \
        next(("+ " + x for x in now), None) or next(("- " + x for x in gone), "")
    return {"added": added, "removed": removed, "out": sum(1 for x in now + gone if out.search(x)), "what": shown[:160]}


# ---------------------------------------------------------------------------
# files that take the place of others, and the rest of a git clone
# ---------------------------------------------------------------------------

LOADED = re.compile(r"(?i)\.(?:py|pyc|pyo|pyw|so|pyd|dylib|pth)$")     # what Python loads as a part, by the name before the first dot


def _shadows(names: Iterable[str], before: Iterable[str] = ()) -> Dict[Tuple[str, str, str], str]:
    """Files and folders that take the place of another part: a folder named like a part of the program or of Python (it is
    loaded instead of the file), a file named like a part of Python, a translated or compiled part beside its text, what
    Python loads by itself (sitecustomize, *.pth, the folder's own __init__/__main__), and names that differ only in their
    letters' case or composition (the Mac's disks take them for one file: one overwrites the other)."""
    names = sorted(names)
    out: Dict[Tuple[str, str, str], str] = {}
    stems = {r[:-3] for r in names if "/" not in r and r.endswith(".py")} | {k[:-3] for k in kept() if "/" not in k and k.endswith(".py")}
    alike_stems = {_alike(x) for x in stems}
    alike_lib = {_alike(x) for x in STDLIB}
    for rel in names:
        parts = rel.split("/")
        base = parts[-1]
        if len(parts) == 1:
            low, stem = base.lower(), base.split(".")[0]
            if low in STARTUP or low.endswith(".pth") or re.match(r"__(?:init|main)__\.", low):
                out[("shadow", rel, "")] = base
            elif LOADED.search(base) and _alike(stem) in alike_lib:
                out[("shadow", rel, "")] = "%s (Python: %s)" % (base, stem)
            elif LOADED.search(base) and not low.endswith(".py") and _alike(stem) in alike_stems:
                out[("shadow", rel, "")] = "%s → %s.py" % (base, stem)
        elif _alike(parts[0]) in alike_stems or _alike(parts[0]) in alike_lib:
            out[("shadow", parts[0] + "/", "")] = "%s/ → %s" % (parts[0], parts[0] + (".py" if _alike(parts[0]) in alike_stems else " (Python)"))
    groups: Dict[str, Set[str]] = {}
    for rel in list(names) + sorted(kept()) + list(before):
        groups.setdefault(_alike(rel), set()).add(rel)
    mine = set(names)
    for group in groups.values():
        if len(group) > 1 and group & mine:
            out[("shadow", min(group & mine), "")] = " = ".join(sorted(group))
    return out


# what a helper or Python itself makes beside the program while it runs, as the repository's list (.gitignore) writes it
def ignored(rel: str, patterns: Iterable[str]) -> bool:
    """Does a list in the manner of .gitignore take in this path? (The last pattern that fits decides; !pattern lets go.)"""
    parts, hit = rel.split("/"), False
    for raw in patterns:
        p = raw.strip()
        if not p or p.startswith("#"):
            continue
        keep = p.startswith("!")
        p = p[1:] if keep else p
        folder = p.endswith("/")
        p = p.strip("/")
        if not p:
            continue
        if "/" in raw.strip().lstrip("!").rstrip("/"):       # with a slash: from the top of the repository
            fits = any(fnmatch.fnmatchcase("/".join(parts[:k]), p) and (k < len(parts) or not folder) for k in range(1, len(parts) + 1))
        else:
            fits = any(fnmatch.fnmatchcase(x, p) and (k < len(parts) - 1 or not folder) for k, x in enumerate(parts))
        if fits:
            hit = not keep
    return hit


def beside(rel: str, data: bytes, patterns: Iterable[str] = ()) -> Optional[str]:
    """A file of a git clone that is no part of the program: None when it is an ordinary file of the repository's tests and
    development (text with an ordinary ending in one of those folders, in .githooks any text -- Kontor never runs it, its own
    git runs without hooks), else what it is (shown). Never ordinary: what a program or helper makes (caches, translated
    Python, apps, the helpers' folders, whatever the repository's own list of such files takes in), anything that is no text.
    The development's hooks (.githooks, .claude/hooks) run only where a developer turns them on, never by Kontor."""
    parts = rel.split("/")
    if ignored(rel, MADE_HERE.splitlines()) or ignored(rel, patterns):
        return "%s (%s)" % (rel, "made by a program")
    if not (parts[0] in BESIDE and len(parts) > 1 or rel in BESIDE_FILES):
        return rel
    if rel not in BESIDE_FILES and not parts[-1].lower().endswith(BESIDE_ENDS) and not (parts[0] == ".githooks" and len(parts) == 2):
        return rel
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return "%s (%s)" % (rel, "no text")
    return "%s (%s)" % (rel, "no text") if "\0" in text else None


# ---------------------------------------------------------------------------
# pages and everything else
# ---------------------------------------------------------------------------

def _joined(text: str) -> str:
    """A page's text with pieces of text put together ('htt' + 'ps://' is read as 'https://')."""
    for _ in range(12):
        more = JS_JOIN.sub(lambda m: '"' + m.group(2) + m.group(4) + '"', text)
        if more == text:
            break
        text = more
    return text


def _page(rel: str, data: bytes, out: dict, shown: dict, info: Optional[dict] = None) -> None:
    info = {} if info is None else info
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        out[("unreadable", rel, "")] = _sha(data)
        shown[("unreadable", rel, "")] = rel
        return
    spans: Dict[str, list] = {}
    for name, bodies in _page_rules(rel, text, spans).items():     # what the update page shows and sends: each as a whole
        out[("rule", rel, name)] = "+".join(_sha(b.encode("utf-8")) for b in bodies)
        shown[("rule", rel, name)] = name
        info[("rule", rel, name)] = {"spans": spans.get(name, []), "name": name, "where": name}
    if rel.lower().endswith((".js", ".mjs", ".html", ".htm")):
        text = _joined(text)
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
    found: List[Tuple[str, int]] = []
    if not low.endswith(".css"):                               # (a style sheet runs nothing)
        for m in PAGE.finditer(text):
            hit = m.group(0)
            if LEAVING.search(hit):                            # where a page leaves or clicks: the whole line, with what guards it
                start, end = text.rfind("\n", 0, m.start()) + 1, text.find("\n", m.end())
                hit = text[start:end if end >= 0 else len(text)].strip()[:600]
            found.append((hit, m.start()))
    if not low.endswith((".js", ".mjs")):
        found += [(m.group(0), m.start()) for m in STYLE.finditer(text)]
    for hit, at in found:
        s = " ".join(hit.split())
        key = ("page", rel, s)
        out[key] = str(int(out.get(key, "0")) + 1)
        shown[key] = s[:110]
        line = text.count("\n", 0, at) + 1                   # (of the page's own text: pieces put together count by the joined one)
        info.setdefault(key, {"spans": [], "name": "", "where": ""})["spans"].append((line, line))


def scan(files: Dict[str, bytes], before: Iterable[str] = ()) -> Tuple[Dict[Tuple[str, str, str], str], Dict[Tuple[str, str, str], str], Dict[Tuple[str, str, str], dict]]:
    """What a set of program files holds of the things named above: ({(kind, file, what): content}, {the same: a line to show},
    {the same: for the update page -- the lines it stands on, its name, the way out it belongs to; never compared}).
    before: the names of the files there are now (a new name that takes the place of one of them is shown)."""
    out: Dict[Tuple[str, str, str], str] = {}
    shown: Dict[Tuple[str, str, str], str] = {}
    info: Dict[Tuple[str, str, str], dict] = {}
    names = [r for r in files if installable(r)]
    local = _local(names)
    _python(files, sorted(r for r in names if r.lower().endswith(".py")), local, out, shown, info)
    for key, what in _shadows(names, [r for r in before if installable(r)]).items():
        out[key], shown[key] = "1", what
    for rel in sorted(names):
        data, low, base = files[rel], rel.lower(), rel.rsplit("/", 1)[-1]
        if low.endswith(".py"):
            continue
        elif low.endswith(PAGE_FILES):
            _page(rel, data, out, shown, info)
        elif low.endswith(PASSIVE) or base in PASSIVE_NAMES:
            continue
        elif low.endswith(SCRIPTS):                            # a helper in Swift, a script: its lines without comments
            out[("file", rel, "")] = _script(rel, data)
            shown[("file", rel, "")] = rel
        else:                                                  # anything else Kontor cannot read this way
            out[("file", rel, "")] = _sha(data)
            shown[("file", rel, "")] = rel
    return out, shown, info


def compare(old_files: Dict[str, bytes], new_files: Dict[str, bytes], limit: int = 200) -> List[Dict[str, object]]:
    """What the new files hold of those things that the old ones do not hold the same way: [{kind, file, what, new}] -- "new":
    it was not there at all (else: it is changed); of a helper or script also how many lines are added and taken away and how
    many of the changed ones reach out ("added", "removed", "out"). With each what it means to you and how the update page
    shows it (judge): "level" (critical, review, plain -- see RULE_GROUPS), "topic" (the entry it belongs to, with "title",
    "why", "arg"), "where" (function or setting) and "lines" (what it concerns: "-" taken away, "+" new, " " beside them, "…"
    left out; "more": lines not shown). Empty: nothing new at all; asked about is what asking() gives."""
    old = scan(old_files)
    new = scan(new_files, set(old_files))
    return judge(_differences(old[0], new, set(new_files)), old_files, new_files, old, new)[:limit]


def differences(old: Dict[Tuple[str, str, str], str], scanned: tuple, new_files: Set[str], limit: int = 200) -> List[Dict[str, object]]:
    return [f for _key, f in _differences(old, scanned, new_files)][:limit]


def _differences(old: Dict[Tuple[str, str, str], str], scanned: tuple, new_files: Set[str]) -> List[Tuple[Tuple[str, str, str], Dict[str, object]]]:
    new, shown = scanned[0], scanned[1]
    known = {k[2] for k in old if k[0] == "address"}           # an address the program names already, written in another file too
    found: List[Tuple[Tuple[str, str, str], Dict[str, object]]] = []
    for key in sorted(new, key=lambda k: (KINDS.index(k[0]) if k[0] in KINDS else 99, k[1], k[2])):
        if old.get(key) == new[key]:
            continue
        kind, rel, what = key
        if kind == "page" and key in old and int(new[key]) <= int(old[key]):
            continue                                           # the same line fewer times
        if kind == "address" and what in known:
            continue
        f: Dict[str, object] = {"kind": kind, "file": rel, "what": shown.get(key, "")[:160], "new": key not in old}
        if kind == "file" and new[key].startswith(LINES):     # a helper or script: what of it changes
            f.update(_script_change(rel, old.get(key), new[key]))
        found.append((key, f))
    for key in sorted(old, reverse=True):                      # a rule, or the check itself, that is no longer there
        if key not in new and key[0] in ("rule", "guard") and (key[0] == "guard" or key[1] in new_files):     # (a rule of a file that is gone: the file tells)
            found.insert(0, (key, {"kind": key[0], "file": key[1], "what": (key[2] + ("" if key[2].isupper() else "()")) if key[0] == "rule" else key[1],
                                   "new": False, "gone": True}))
    return found


def summary(found: Iterable[Dict[str, str]]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for f in found:
        out[f["kind"]] = out.get(f["kind"], 0) + 1
    return out


def asking(found: Iterable[Dict[str, object]]) -> List[Dict[str, object]]:
    """The findings an update waits for your approval for: every one that is not plain -- also one that was not judged (a file
    of a git clone that arrives unread, a check that failed)."""
    return [f for f in found if f.get("level") != L_PLAIN]


# ---------------------------------------------------------------------------
# what each finding means to you, and the lines it concerns
# ---------------------------------------------------------------------------

def judge(pairs: List[Tuple[Tuple[str, str, str], Dict[str, object]]], old_files: Dict[str, bytes], new_files: Dict[str, bytes],
          old_scan: tuple, new_scan: tuple) -> List[Dict[str, object]]:
    """Each finding with its level, the entry of the update page it belongs to and its lines (see compare). Critical unless it
    is known as less: a call that reaches out and is new, a new address, place, part of Python, a detour, a file that takes
    another's place or arrives unread, a change of the check itself and of a rule that is no plain table -- critical; a call
    that was there and is changed, and what feeds such a call -- review, one entry per way out; a rule that is only stricter
    -- plain (RULE_GROUPS). What else a file of the check itself holds is in the check's own finding:
    any change to it is critical anyway, its lines are the file's changes."""
    old_info: dict = old_scan[2] if len(old_scan) > 2 else {}
    new_info: dict = new_scan[2] if len(new_scan) > 2 else {}
    texts: Dict[Tuple[str, str], List[str]] = {}
    trees: Dict[tuple, object] = {}
    proven: Dict[Tuple[str, str], bool] = {}

    def raw(side: str, rel: str) -> Optional[bytes]:
        data = (old_files if side == "old" else new_files).get(rel)
        return data if isinstance(data, bytes) else None

    def lines(side: str, rel: str) -> List[str]:
        """The file's lines as Python counts them (only at \\n, \\r\\n, \\r -- not at a form feed or the like, where
        splitlines would cut and Python reads on: what is shown and judged is what runs)."""
        if (side, rel) not in texts:
            data = raw(side, rel)
            out = _PY_BREAK.split(data.decode("utf-8", "replace")) if data is not None else []
            texts[(side, rel)] = out[:-1] if out and out[-1] == "" else out
        return texts[(side, rel)]

    def tree(side: str, rel: str) -> Optional[ast.Module]:
        """The file as Python reads it -- the same text the scan read (strictly UTF-8), else none (and no proof)."""
        if (side, rel) not in trees:
            data = raw(side, rel)
            try:
                trees[(side, rel)] = ast.parse(_py_text(data)) if data is not None else None
            except (SyntaxError, ValueError, RecursionError, MemoryError, UnicodeDecodeError):
                trees[(side, rel)] = None
        return trees[(side, rel)]                          # type: ignore[return-value]

    def quiet(side: str, rel: str) -> Set[int]:
        """The lines of a file that only explain (comments, a function's explanation): a change there alone is not shown."""
        if (side, rel, "quiet") not in trees:
            text = lines(side, rel)
            out = {i + 1 for i, x in enumerate(text) if x.lstrip().startswith("#" if rel.endswith(".py") else "//")}
            t = tree(side, rel) if rel.endswith(".py") else None
            for n in ast.walk(t) if t is not None else ():
                body = getattr(n, "body", None)
                if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and body and isinstance(body[0], ast.Expr) \
                        and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
                    out.update(range(body[0].lineno, (body[0].end_lineno or body[0].lineno) + 1))
            trees[(side, rel, "quiet")] = out              # type: ignore[index,assignment]
        return trees[(side, rel, "quiet")]                 # type: ignore[index,return-value]

    def stricter(rel: str, name: str, policy: str) -> bool:
        """Only stricter -- and nothing else in the program may change the table: no other file touches it under its name
        (module.NAME, "NAME") differently than before, and no line break Python and the lines see differently."""
        if (rel, name) not in proven:
            try:
                new_raw = raw("new", rel) or b""
                ok = not _ODD_BREAK.search(new_raw.decode("utf-8", "replace")) and _stricter(policy, tree("old", rel), tree("new", rel), name)
                if ok and policy in ("allow", "deny"):
                    py = sorted(r for r in set(old_files) | set(new_files) if r.endswith(".py") and r != rel)
                    ok = all(_uses(tree("old", r), name, None, False) == _uses(tree("new", r), name, None, False) for r in py)
                proven[(rel, name)] = ok
            except (ValueError, TypeError, RecursionError):
                proven[(rel, name)] = False
        return proven[(rel, name)]

    guarded = {key[1] for key, _f in pairs if key[0] == "guard"}
    judged: List[Tuple[Tuple[int, int, int], Dict[str, object], Tuple[str, str, str], str]] = []      # (order, finding, key, name)
    for i, (key, f) in enumerate(pairs):
        kind, rel, what = key
        if kind in INSIDE and _own(rel) and rel in guarded:
            continue                                           # (in the check's own finding: its lines are the file's changes)
        inf = new_info.get(key) or old_info.get(key) or {}
        name = str(inf.get("name") or (what if kind == "rule" else ""))
        rule = RULE_LEVEL.get(rel, {}).get(name) if name else None
        way = list(inf.get("way") or ["other", ""])
        level, topic, arg = L_CRITICAL, kind, rel
        if kind == "guard":
            topic = "check"
        elif kind == "rule" and rule is None:
            topic, arg = "rules", name                         # a rule nobody judged: a risk
        elif rule is not None and (kind == "rule" or kind in ("call", "around") and rule[1] in ("allow", "deny", "shield")):
            # the rule itself -- or the same function or setting as found by what reaches out: a table or a profile is judged
            # as a whole, so what it proves holds for those, too (a filter behind a card is no proof for anything else)
            topic = rule[0]
            if kind == "rule" and rule[1] == "card":
                level = L_REVIEW                               # (one entry: the filter as a whole, its lines below)
            elif rule[1] in ("allow", "deny", "shield") and not f.get("new") and not f.get("gone") and stricter(rel, name, rule[1]):
                level = L_PLAIN
        elif rule is not None and rule[1] != "card":
            topic = rule[0]                                    # what reaches out in a rule's own function: in its entry, a risk
        elif kind == "detour":
            topic = WORD_TOPIC if inf.get("words") and rel in WORDS else "detour"
        elif kind in ("call", "around"):
            new_way = kind == "call" and bool(f.get("new"))   # a new call: a new way out; else what goes over one there is already
            topic, arg = ("new_" if new_way else "way_") + way[0], way[1]
            level = L_CRITICAL if new_way else L_REVIEW
        elif kind == "file":
            topic = "script" if str(new_scan[0].get(key, "")).startswith(LINES) else "file"
        elif kind == "place":
            arg = ", ".join(inf.get("args") or [str(f.get("what", ""))])
        elif kind in ("address", "module"):
            arg = what
        if topic in RULE_TOPICS:
            arg = ""                                           # (one entry for the rules of a topic, named by the topic)
        f["level"] = level
        f["topic"] = topic if topic in RULE_TOPICS else "%s:%s" % (topic, arg)
        f["title"], f["why"] = TOPIC_TEXT.get(topic, ("upd_t_" + kind, "upd_w_" + kind))
        f["arg"] = str(arg)[:80]
        f["where"] = str(inf.get("where") or "")[:80]
        rank = TOPIC_ORDER.index(topic) if topic in TOPIC_ORDER else len(TOPIC_ORDER)
        judged.append(((0 if level == L_CRITICAL else 1 if level == L_REVIEW else 2, rank, i), f, key, name or str(f["where"]).split(".")[-1].rstrip("()") or what))
    judged.sort(key=lambda x: x[0])
    budget = [LINES_ALL]
    seen: Set[Tuple[str, str, str]] = set()
    for _rank, f, key, name in judged:
        place = (str(f["topic"]), key[1], name)
        if place in seen:                                     # the same function or setting found once more (as a rule and as
            f["dup"] = True                                   # what reaches out): one part of its entry, its lines once
            continue
        seen.add(place)
        if f["level"] == L_PLAIN:
            continue
        shown, more = _excerpt(key, f, lines, quiet, old_scan, new_scan, old_info, new_info)
        take = min(len(shown), budget[0])
        budget[0] -= take
        if shown:
            f["lines"] = shown[:take]
            if more + len(shown) - take:
                f["more"] = more + len(shown) - take
    return [f for _rank, f, _key, _name in judged]


def _excerpt(key: Tuple[str, str, str], f: Dict[str, object], lines, quiet, old_scan: tuple, new_scan: tuple, old_info: dict,
             new_info: dict) -> Tuple[List[str], int]:
    """The lines a finding concerns, as the files have them: its function or setting before and after (only what changed, with
    a line around it; a change of comments and explanations alone left out), the lines that name a new address, of a helper
    its lines without comments, of the check its file."""
    kind, rel, what = key
    if kind in ("shadow", "extra", "unreadable") or f.get("gone") and kind == "guard":
        return [], 0
    if kind == "guard":
        return _diff(lines("old", rel), lines("new", rel), LINES_MOST + 8, quiet("old", rel), quiet("new", rel))
    if kind == "file":
        before, after = str(old_scan[0].get(key, "")), str(new_scan[0].get(key, ""))
        if not after.startswith(LINES):
            return [], 0
        return _diff(before.split("\n")[1:] if before.startswith(LINES) else [], after.split("\n")[1:])
    if kind == "address":
        was = set(lines("old", rel))
        return _diff([], [x for x in lines("new", rel) if what.lower() in x.lower() and x not in was][:4])
    if kind == "page":                                         # the line of the page, found by its beginning
        start = " ".join(what.split())[:40]
        hit = [x for x in lines("new", rel) if start and start in " ".join(x.split())][:2]
        if hit:
            return _diff([], hit)

    def cut(side: str, info: dict, scan: tuple) -> Tuple[List[str], Set[int]]:
        if key not in scan[0]:
            return [], set()
        text, explains = lines(side, rel), quiet(side, rel)
        nums = [i for a, b in (info.get(key) or {}).get("spans", []) for i in range(a, min(b, len(text)) + 1)]
        return [text[i - 1] for i in nums], {k + 1 for k, i in enumerate(nums) if i in explains}
    (a, qa), (b, qb) = cut("old", old_info, old_scan), cut("new", new_info, new_scan)
    return _diff(a, b, LINES_MOST, qa, qb)


def _diff(a: List[str], b: List[str], most: int = LINES_MOST, quiet_a: Iterable[int] = (), quiet_b: Iterable[int] = ()) -> Tuple[List[str], int]:
    """What changed from lines a to lines b: "-" taken away, "+" new, " " a line beside them, "…" lines left out -- at most this
    many lines, each cut to LINE_WIDTH, the indentation they all share taken away; a place where only lines that explain
    changed (quiet_a, quiet_b: their numbers, from 1) left out. (lines shown, how many more there are)"""
    out: List[str] = []
    qa, qb = set(quiet_a), set(quiet_b)
    if not a or not b:
        out = ["-" + x for x in a] + ["+" + x for x in b]
    else:
        for group in difflib.SequenceMatcher(None, a, b, autojunk=False).get_grouped_opcodes(1):
            changed = [(tag, i1, i2, j1, j2) for tag, i1, i2, j1, j2 in group if tag != "equal"]
            if all(set(range(i1 + 1, i2 + 1)) <= qa and set(range(j1 + 1, j2 + 1)) <= qb for _t, i1, i2, j1, j2 in changed):
                continue                                       # (nothing changed here, or only what explains)
            if out:
                out.append("…")
            for tag, i1, i2, j1, j2 in group:
                out += [" " + x for x in a[i1:i2]] if tag == "equal" else ["-" + x for x in a[i1:i2]] + ["+" + x for x in b[j1:j2]]
    out = [x if x == "…" else x[0] + x[1:].rstrip() for x in out]
    body = [x[1:] for x in out if x != "…" and x[1:].strip()]
    cut = min((len(x) - len(x.lstrip(" \t")) for x in body), default=0)
    out = [x if x == "…" else x[0] + x[1 + cut:] if x[1:].strip() else x[0] for x in out]
    out = ["".join("⟨U+%04X⟩" % ord(c) if _hidden(c) else c for c in x) for x in out]      # (what would turn a line around or hide in it)
    out = [x if len(x) <= LINE_WIDTH else x[:LINE_WIDTH - 1] + "…" for x in out]
    return out[:most], max(0, len(out) - most)


def _stricter(policy: str, old: Optional[ast.Module], new: Optional[ast.Module], name: str) -> bool:
    """Is the rule of this name only stricter in the new file? (see RULE_GROUPS) -- each side must hold it exactly once, never
    given a value anywhere else (a name set again later, global): else no proof, and a risk."""
    if old is None or new is None or policy not in ("allow", "deny", "shield"):
        return False
    if policy == "shield":
        a, b = _defs(old, name), _defs(new, name)
        return len(a) == len(b) == 1 and _profile_stricter(a[0], b[0]) and _uses(old, name, a[0]) == _uses(new, name, b[0])
    sa, sb = _top_stmt(old, name), _top_stmt(new, name)
    if sa is None or sb is None or type(sa) is not type(sb):
        return False
    if isinstance(sa, ast.AnnAssign) and ast.dump(sa.annotation) != ast.dump(sb.annotation):      # (a type is run, too)
        return False
    if _uses(old, name, sa) != _uses(new, name, sb):
        return False                                   # (the table changed elsewhere, or handed on: no proof)
    if any(_bound(t, b) or _uses(t, b, None, False) for t in (old, new) for b in ("frozenset", "set", "tuple")):
        return False                                   # (frozenset(...) read as the built-in only when no one redefines it)
    va, vb = _literal(sa.value), _literal(sb.value)   # type: ignore[arg-type]
    return _within(vb, va) if policy == "allow" else _within(va, vb)


def _bound(tree: ast.Module, name: str) -> List[ast.AST]:
    """Every place of a file that gives this name a value (also as a function, a class, an import or with global)."""
    out: List[ast.AST] = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Name) and n.id == name and not isinstance(n.ctx, ast.Load) or \
                isinstance(n, (ast.Subscript, ast.Attribute)) and not isinstance(n.ctx, ast.Load) and isinstance(n.value, ast.Name) and n.value.id == name or \
                isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and n.name == name or \
                isinstance(n, (ast.Global, ast.Nonlocal)) and name in n.names or \
                isinstance(n, ast.alias) and (n.asname or n.name.split(".")[0]) == name or \
                isinstance(n, ast.arg) and n.arg == name:
            out.append(n)
    return out


def _defs(tree: ast.Module, name: str) -> List[ast.AST]:
    """The function of this name, when that is all that gives the name a value in its file."""
    bound = _bound(tree, name)
    return bound if all(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) for n in bound) else []


def _top_stmt(tree: ast.Module, name: str) -> Optional[ast.stmt]:
    """The line at the top of the file that gives a setting its value, when that is the only place that gives the name a value."""
    sts = [st for st in tree.body if isinstance(st, (ast.Assign, ast.AnnAssign)) and st.value is not None and
           [t.id for t in (st.targets if isinstance(st, ast.Assign) else [st.target]) if isinstance(t, ast.Name)] == [name] and
           len(st.targets if isinstance(st, ast.Assign) else [st.target]) == 1]
    return sts[0] if len(sts) == 1 and len(_bound(tree, name)) == 1 else None


def _tops(tree: ast.Module, name: str) -> Optional[ast.AST]:
    """The value a setting at the top of the file is given, when that is the only place that gives the name a value."""
    st = _top_stmt(tree, name)
    return st.value if st is not None else None


def _uses(tree: Optional[ast.Module], name: str, skip: Optional[ast.AST], bare: bool = True) -> List[str]:
    """Every place that touches this name (as NAME -- only with bare --, as x.NAME, as the text "NAME"), each as the line
    around it (of a block only its head: what holds the name), the line skip left out; sorted, to compare two versions --
    a table changed after its line (NAME["x"] = ..., NAME.clear(), y = NAME) adds a place."""
    if tree is None:
        return []
    parent: Dict[ast.AST, ast.AST] = {}
    for p in ast.walk(tree):
        for c in ast.iter_child_nodes(p):
            parent[c] = p
    out: List[str] = []
    for n in ast.walk(tree):
        if not (bare and isinstance(n, ast.Name) and n.id == name or isinstance(n, ast.Attribute) and n.attr == name
                or isinstance(n, ast.Constant) and isinstance(n.value, str) and n.value == name):
            continue
        child, st = n, parent.get(n)
        while st is not None and not isinstance(st, ast.stmt):
            child, st = st, parent.get(st)
        if st is None or st is skip:
            continue
        out.append(type(st).__name__ + ":" + ast.dump(child if hasattr(st, "body") else st, annotate_fields=False))
    return sorted(out)


def _literal(node: ast.AST):
    """A table written out as it is: texts, numbers, lists, sets, tables -- else ValueError (nothing of the code is run)."""
    if isinstance(node, ast.Constant) and (node.value is None or isinstance(node.value, (str, bytes, int, float, bool))):
        return node.value
    if isinstance(node, (ast.Tuple, ast.List)):
        return tuple(_literal(e) for e in node.elts)
    if isinstance(node, ast.Set):
        return frozenset(_literal(e) for e in node.elts)
    if isinstance(node, ast.Dict) and None not in node.keys:
        return {_literal(k): _literal(v) for k, v in zip(node.keys, node.values)}     # type: ignore[arg-type]
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ("frozenset", "set", "tuple") and not node.keywords and len(node.args) <= 1:
        inner = _literal(node.args[0]) if node.args else ()
        if not isinstance(inner, (str, tuple, frozenset)):
            raise ValueError("no row")
        return frozenset(inner) if node.func.id != "tuple" else tuple(inner)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "split" and not node.args and not node.keywords:
        text = _literal(node.func.value)
        if isinstance(text, str):
            return tuple(text.split())
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        a, b = _literal(node.left), _literal(node.right)
        if isinstance(a, frozenset) and isinstance(b, frozenset):
            return a | b
    raise ValueError("not written out")


def _within(new, old) -> bool:
    """Does new hold nothing old does not hold -- entries taken away, nothing added or changed?"""
    if isinstance(new, dict):
        return isinstance(old, dict) and all(k in old and _within(v, old[k]) for k, v in new.items())
    if isinstance(new, (tuple, frozenset)):
        return type(old) is type(new) and all(any(type(x) is type(y) and x == y for y in old) for x in new)
    return type(new) is type(old) and new == old


def _sb_kind(e: ast.AST) -> str:
    """"allow" or "deny" when this piece of code is one rule of a sandbox profile written as a text (or a text % values)."""
    t = e.value if isinstance(e, ast.Constant) else e.left.value if isinstance(e, ast.BinOp) and isinstance(e.op, ast.Mod) and isinstance(e.left, ast.Constant) else None
    m = re.match(r"\s*\((allow|deny)[\s)]", t) if isinstance(t, str) else None
    return m.group(1) if m else ""


# The sandbox's language is a Scheme: each part of a rule is run. A rule counts as whole only in this plain form -- the kind,
# operations, then filters of these names with texts, patterns or names as values (also nested in require-any/-all/-not) --
# never a form that defines or runs anything (define, begin, lambda ...), a comment, a quote or a modifier (with ...).
_SB_FILTERS = frozenset("""literal subpath prefix regex path global-name global-name-regex local-name local-name-regex remote local
vnode-type target extension extension-class ipc-posix-name ipc-posix-name-regex xattr xattr-regex file-mode signal-target
process-path iokit-registry-entry-class iokit-user-client-class iokit-property sysctl-name sysctl-name-prefix preference-domain
appleevent-destination""".split())
_SB_FORMS = frozenset("""define begin lambda let let* letrec if cond case quote quasiquote unquote set! allow deny import version
debug trace with param when unless and or not apply eval load string-append""".split())
_SB_ATOM = re.compile(r"[A-Za-z0-9*:._/+-]+")
_SB_OP = re.compile(r"[a-z][a-z0-9-]*\*?")


def _sb_read(t: str):
    """A text of the sandbox's language as nested lists: ("s", text or #"pattern"), ("a", name) -- else ValueError."""
    toks: List[object] = []
    i, n = 0, len(t)
    while i < n:
        c = t[i]
        if c.isspace():
            i += 1
        elif c in "()":
            toks.append(c)
            i += 1
        elif c == '"' or t.startswith('#"', i):
            j = i + (2 if c == "#" else 1)
            while j < n and t[j] != '"':
                if t.startswith('\\"', j):
                    raise ValueError("an escaped quote")    # (read as raw text or not: two readings -- never whole)
                j += 2 if t[j] == "\\" else 1
            if j >= n:
                raise ValueError("open text")
            toks.append(("s", t[i:j + 1]))
            i = j + 1
        else:
            m = _SB_ATOM.match(t, i)
            if not m:
                raise ValueError("not plain: %r" % c)
            toks.append(("a", m.group()))
            i = m.end()

    def form(k: int):
        if k >= len(toks) or toks[k] == ")":
            raise ValueError("unbalanced")
        if toks[k] != "(":
            return toks[k], k + 1
        out, k = [], k + 1
        while k < len(toks) and toks[k] != ")":
            x, k = form(k)
            out.append(x)
        if k >= len(toks):
            raise ValueError("unbalanced")
        return out, k + 1

    whole, k = form(0)
    if k != len(toks):
        raise ValueError("more than one form")
    return whole


def _sb_filter(f) -> bool:
    if not isinstance(f, list) or len(f) < 2 or not isinstance(f[0], tuple) or f[0][0] != "a":
        return False
    head = f[0][1]
    if head in ("require-any", "require-all", "require-not"):
        return all(_sb_filter(x) for x in f[1:])
    return head in _SB_FILTERS and all(isinstance(x, tuple) and (x[0] == "s" or x[1] not in _SB_FORMS) for x in f[1:])


def _sb_whole(t: str, kind: str = "deny") -> bool:
    """Is this text exactly one plain rule "(deny ...)" (or "(allow ...)") of the sandbox's language -- the kind, at least one
    operation, filters (above) and nothing else: no comment, no second form, nothing that defines or runs anything?"""
    try:
        whole = _sb_read(t.strip())
    except (ValueError, RecursionError):
        return False
    if not isinstance(whole, list) or len(whole) < 2 or whole[0] != ("a", kind):
        return False
    k = 1
    while k < len(whole) and isinstance(whole[k], tuple):
        if whole[k][0] != "a" or not _SB_OP.fullmatch(whole[k][1]) or whole[k][1] in _SB_FORMS:
            return False
        k += 1
    return k > 1 and all(_sb_filter(f) for f in whole[k:])


def _skeleton(node, lists: List[list]) -> str:
    """A function without its sandbox rules: how it is built, with the rules of each list kept apart in order (lists) -- so
    that two versions can be compared without them, and their rules list by list."""
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        lists.append([(k, ast.dump(e, annotate_fields=False), e.value if isinstance(e, ast.Constant) else None)
                      for e in node.elts for k in [_sb_kind(e)] if k])
        return "%s[%s]" % (type(node).__name__, ",".join(_skeleton(e, lists) for e in node.elts if not _sb_kind(e)))
    if isinstance(node, ast.AST):
        parts = []
        for field, v in ast.iter_fields(node):
            if field == "body" and isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and v and isinstance(v[0], ast.Expr) \
                    and isinstance(v[0].value, ast.Constant) and isinstance(v[0].value.value, str):
                v = v[1:]                                      # (its explanation is no code)
            parts.append(_skeleton(v, lists))
        return "%s(%s)" % (type(node).__name__, ",".join(parts))
    if isinstance(node, list):
        return "[%s]" % ",".join(_skeleton(x, lists) for x in node)
    return repr(node)


def _profile_stricter(old_fn: ast.AST, new_fn: ast.AST) -> bool:
    """The same function but for rules "(deny ...)" added (each a plain text, one whole rule) and rules "(allow ...)" taken
    away, list by list -- in the sandbox's language neither lets anything more through."""
    a_lists: List[list] = []
    b_lists: List[list] = []
    if _skeleton(old_fn, a_lists) != _skeleton(new_fn, b_lists) or len(a_lists) != len(b_lists):
        return False
    for a, b in zip(a_lists, b_lists):
        for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, [x[1] for x in a], [x[1] for x in b], autojunk=False).get_opcodes():
            if tag == "equal":
                continue
            if any(k != "allow" or not isinstance(t, str) or not _sb_whole(t, "allow") for k, _d, t in a[i1:i2]):
                return False                                   # only whole rules that allow are taken away ...
            if any(k != "deny" or not isinstance(t, str) or not _sb_whole(t) for k, _d, t in b[j1:j2]):
                return False                                   # ... and only whole rules that deny are added
    return True
