"""Asked on a Mac only -- GitHub's macOS job runs it: python3 tests/mac_sandbox_probe.py. What it prints is read by hand; it
decides nothing by itself (the step may fail without turning the run red).

Today the model's sandbox forbids every connection but those coming in on this Mac: llama.cpp's server listens on 127.0.0.1,
where any program of this Mac could reach it (it would still need the key). The next step: the server listens on a socket file
in its own temporary folder instead, and the sandbox forbids the network altogether, this one file excepted. Before Kontor
does that, this probe asks macOS itself:

  1. the rules: with which wording does the sandbox let a program listen on exactly one socket file -- and on nothing else (no
     address of the network, not even of this Mac; no connection going out; no other socket file)? Asked with a small program
     built here, inside the profile of both levels.
  2. the real thing: llama.cpp's newest release, loaded and tried by Kontor's own code (from GitHub, checked, --version and
     --help inside the sandbox), a tiny model through Kontor's own download (Hugging Face, checked), started as Kontor starts
     it today (127.0.0.1) and answering -- then started on a socket file inside the stricter profile, and asked over the file.
  3. for later (services of other programs by a list instead of all of them): what the model process asks macOS for when it
     may ask for nothing -- only printed.

Needs the network (GitHub, Hugging Face) for 2 and 3; without it they say so and 1 still counts."""
import http.client
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import llm_local as L   # noqa: E402

PROBE_C = r"""
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <unistd.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <netinet/in.h>
#include <arpa/inet.h>

static int fail(const char *what) { printf("%s: %s\n", what, strerror(errno)); fflush(stdout); return 1; }

/* probe listen-unix PATH | listen-tcp PORT | connect-unix PATH | connect-tcp PORT */
int main(int argc, char **argv) {
    if (argc < 3) return 2;
    int un = strstr(argv[1], "unix") != NULL, listening = strncmp(argv[1], "listen", 6) == 0;
    int s = socket(un ? AF_UNIX : AF_INET, SOCK_STREAM, 0);
    if (s < 0) return fail("socket");
    struct sockaddr_un a; struct sockaddr_in b; struct sockaddr *addr; socklen_t len;
    memset(&a, 0, sizeof a); memset(&b, 0, sizeof b);
    if (un) { a.sun_family = AF_UNIX; strncpy(a.sun_path, argv[2], sizeof a.sun_path - 1); addr = (struct sockaddr *)&a; len = sizeof a; }
    else { b.sin_family = AF_INET; b.sin_port = htons(atoi(argv[2])); b.sin_addr.s_addr = htonl(INADDR_LOOPBACK); addr = (struct sockaddr *)&b; len = sizeof b; }
    char buf[16] = {0};
    if (listening) {
        if (bind(s, addr, len) < 0) return fail("bind");
        if (listen(s, 1) < 0) return fail("listen");
        if (!un) { socklen_t l = sizeof b; getsockname(s, (struct sockaddr *)&b, &l); printf("listening %d\n", ntohs(b.sin_port)); }
        else printf("listening\n");
        fflush(stdout);
        int c = accept(s, NULL, NULL);
        if (c < 0) return fail("accept");
        if (read(c, buf, 4) < 0) return fail("read");
        if (write(c, "pong", 4) < 0) return fail("write");
        close(c);
        printf("served\n"); fflush(stdout);
    } else {
        if (connect(s, addr, len) < 0) return fail("connect");
        if (write(s, "ping", 4) < 0) return fail("write");
        if (read(s, buf, 4) < 0) return fail("read");
        printf("got %s\n", buf); fflush(stdout);
    }
    return 0;
}
"""

Q = lambda p: json.dumps(os.path.realpath(p), ensure_ascii=False)
# the wordings to try for "this one socket file" (sock: the file, own: the model's temporary folder of this start)
VARIANTS = {
    "path-literal": lambda sock, own: ["(allow network-bind (local unix-socket (path-literal %s)))" % Q(sock),
                                       "(allow network-inbound (local unix-socket (path-literal %s)))" % Q(sock)],
    "subpath": lambda sock, own: ["(allow network-bind (local unix-socket (subpath %s)))" % Q(own),
                                  "(allow network-inbound (local unix-socket (subpath %s)))" % Q(own)],
    "path-regex": lambda sock, own: ['(allow network-bind (local unix-socket (path-regex #"^/private/var/folders/[^/]+/[^/]+/T/%s[^/]+/")))' % L.TMP_PREFIX,
                                     '(allow network-inbound (local unix-socket (path-regex #"^/private/var/folders/[^/]+/[^/]+/T/%s[^/]+/")))' % L.TMP_PREFIX],
    "literal": lambda sock, own: ["(allow network-bind (literal %s))" % Q(sock), "(allow network-inbound (literal %s))" % Q(sock)],
    "bind-only": lambda sock, own: ["(allow network-bind (local unix-socket (path-literal %s)))" % Q(sock)],
    "none": lambda sock, own: [],
    "today": None,              # the rules as they are: 127.0.0.1 allowed
}


def profile(dirs, level, variant, sock, own, more=()):
    """Kontor's profile of that level with the two rules for 127.0.0.1 replaced by a wording for the socket file."""
    lines = L.sandbox_profile(dirs["data"], dirs["prog"], dirs["base"], level).split("\n")
    if VARIANTS[variant] is not None:
        at = lines.index("(deny network*)") + 1
        lines = lines[:at] + VARIANTS[variant](sock, own) + [x for x in lines[at:] if "localhost" not in x]
    return "\n".join(lines + list(more))


def sealed(prof, cmd, env=None, **kw):
    return subprocess.Popen([L.SANDBOX, "-p", prof] + cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env, **kw)


def first_line(p, seconds=8.0):
    """The first line a process writes ("" if none in time: it is ended)."""
    got = []
    t = threading.Thread(target=lambda: got.append(p.stdout.readline().decode("utf-8", "replace").strip()), daemon=True)
    t.start(); t.join(seconds)
    if not got:
        p.kill()
        return ""
    return got[0]


def end(p):
    try:
        out = p.communicate(timeout=5)[0].decode("utf-8", "replace").strip()
    except subprocess.TimeoutExpired:
        p.kill()
        out = "(still running: ended)"
    return out.replace("\n", " | ")


def ask(kind, target, seconds=5.0):
    """ping -> pong from outside the sandbox; the answer or the error."""
    s = socket.socket(socket.AF_UNIX if kind == "unix" else socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(seconds)
    try:
        s.connect(target if kind == "unix" else ("127.0.0.1", int(target)))
        s.sendall(b"ping")
        return s.recv(4).decode("utf-8", "replace") or "(closed)"
    except OSError as e:
        return "%s: %s" % (type(e).__name__, e)
    finally:
        s.close()


def listener(kind, target):
    """A listener outside the sandbox (to see whether something inside can connect out to it)."""
    s = socket.socket(socket.AF_UNIX if kind == "unix" else socket.AF_INET, socket.SOCK_STREAM)
    s.bind(target if kind == "unix" else ("127.0.0.1", 0))
    s.listen(1)
    s.settimeout(4)

    def serve():
        try:
            c, _ = s.accept()
            c.recv(4); c.sendall(b"pong"); c.close()
        except OSError:
            pass
    threading.Thread(target=serve, daemon=True).start()
    return s


def rules(dirs, probe):
    """Part 1: what each wording lets through, at both levels."""
    print("== 1. the rules ==")
    good = {}
    for level in ("strict", "basic"):
        for variant in VARIANTS:
            own = L.own_tmp()
            sock, other = os.path.join(own, "m.sock"), os.path.realpath(tempfile.mkdtemp(prefix="other-"))
            prof = profile(dirs, level, variant, sock, own)
            res = {}
            # A: listens on its socket file, and an answer comes back from it
            p = sealed(prof, [probe, "listen-unix", sock])
            line = first_line(p)
            res["A own socket"] = (ask("unix", sock) + " / " + end(p)) if line == "listening" else (line or "(nothing)") + " " + end(p)
            # B: an address of this Mac
            p = sealed(prof, [probe, "listen-tcp", "0"])
            line = first_line(p)
            res["B tcp listen"] = ("LISTENS: " + ask("tcp", line.split()[-1]) + " / " + end(p)) if line.startswith("listening") else (line or "(nothing)")
            if p.poll() is None:
                p.kill()
            # C: out to an address of this Mac
            out = listener("tcp", None)
            p = sealed(prof, [probe, "connect-tcp", str(out.getsockname()[1])])
            res["C tcp out"] = end(p); out.close()
            # D: out to another program's socket file
            there = os.path.join(other, "o.sock")
            out = listener("unix", there)
            p = sealed(prof, [probe, "connect-unix", there])
            res["D unix out"] = end(p); out.close()
            # E: a socket file somewhere else (the system's temporary folder itself; its own folder under another name)
            for name, path in (("E unix elsewhere", os.path.join(other, "x.sock")), ("F another name in own", os.path.join(own, "x.sock"))):
                p = sealed(prof, [probe, "listen-unix", path])
                line = first_line(p, 4)
                res[name] = "LISTENS" if line == "listening" else (line or "(nothing)")
                if p.poll() is None:
                    p.kill()
            ok = "pong" in res["A own socket"] and "served" in res["A own socket"] and not any("LISTENS" in v or "got" in v for k, v in res.items() if k[0] in "BCDE")
            print("%-6s %-13s %s" % (level, variant, "FITS" if ok else "no  "), json.dumps(res, ensure_ascii=False))
            if ok:
                good.setdefault(variant, []).append(level)
    fits = [v for v in VARIANTS if good.get(v) == ["strict", "basic"]]
    print("wordings that fit at both levels:", fits or "none")
    return fits


class Unix(http.client.HTTPConnection):
    def __init__(self, path, timeout):
        super().__init__("localhost", timeout=timeout)
        self.path = path

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(self.path)


def http_ask(path, method, where, body=None, key="", seconds=60):
    c = Unix(path, seconds)
    try:
        c.request(method, where, json.dumps(body).encode("utf-8") if body is not None else None,
                  dict({"Content-Type": "application/json"}, **({"Authorization": "Bearer " + key} if key else {})))
        r = c.getresponse()
        return r.status, r.read(4000).decode("utf-8", "replace")
    except (OSError, http.client.HTTPException) as e:
        return 0, "%s: %s" % (type(e).__name__, e)
    finally:
        c.close()


def wait(ai, what):
    t0 = time.time()
    while ai.job and ai.job["state"] == "running" and time.time() - t0 < 240:
        time.sleep(0.3)
    v = ai.job_view() or {}
    print("%s: %s %s" % (what, v.get("state"), v.get("text") or ""))
    return v.get("state") == "done"


def with_token():
    """GitHub answers a runner without a name only now and then: the question for the newest release goes with the job's own
    token (only to api.github.com, only here)."""
    tok, opened = os.environ.get("GH_TOKEN") or "", L._open

    def op(url, kind, headers=None, timeout=30):
        if tok and url.startswith("https://api.github.com/"):
            headers = dict(headers or {}, Authorization="Bearer " + tok)
        return opened(url, kind, headers, timeout)
    L._open = op


def sock_start(ai, rt, m, prof, sock, own):
    """llama.cpp's server as Kontor starts it, but on a socket file inside the given profile. (process, key, answer of /health)"""
    key = "probe-" + os.urandom(8).hex()
    flags = rt.get("flags") or []
    args = [rt["path"], "--model", m["path"], "--host", sock, "--ctx-size", "2048", "--parallel", "1"]
    args += [f for f in ("--no-webui", "--offline", "--jinja", "--no-slots") if f in flags]
    p = sealed(prof, args, env=ai._env(key, own), cwd=os.path.dirname(rt["path"]), stdin=subprocess.DEVNULL)
    tail = []
    threading.Thread(target=lambda: [tail.append(x.decode("utf-8", "replace").rstrip()[:200]) for x in p.stdout], daemon=True).start()
    t0, status = time.time(), (0, "")
    while time.time() - t0 < 90 and p.poll() is None:
        status = http_ask(sock, "GET", "/health", seconds=3) if os.path.exists(sock) else (0, "no socket file yet")
        if status[0] == 200:
            break
        time.sleep(0.5)
    return p, key, status, tail


def real(dirs, fits):
    """Parts 2 and 3: llama.cpp itself."""
    print("== 2. llama.cpp ==")
    with_token()
    ai = L.LocalAI(dirs["base"], dirs["data"], dirs["prog"])
    try:
        ai.install_runtime("strict")
    except Exception as e:
        print("llama.cpp not loaded:", type(e).__name__, e)
        return
    if not wait(ai, "llama.cpp (loaded, checked, tried inside the sandbox)"):
        return
    rt = ai.runtime()
    print("version:", rt.get("tag"), rt.get("version"), "| flags:", len(rt.get("flags") or []))
    helped = subprocess.run(ai._sealed_cmd([rt["path"], "--help"], "strict"), capture_output=True, text=True, timeout=60, env=ai._env("", L.own_tmp()), cwd=os.path.dirname(rt["path"]))
    host = [x.strip() for x in ((helped.stdout or "") + (helped.stderr or "")).split("\n") if x.strip().startswith("--host")]
    print("its --host:", host, "| the lines after it:", [x.strip()[:160] for x in ((helped.stdout or "") + (helped.stderr or "")).split("--host", 1)[-1].split("\n")[:3]])
    repo, name = "ggml-org/tiny-llamas", "stories260K.gguf"
    mid = "%s/%s" % (repo, name)
    ai.download_model("", repo, name)
    if not wait(ai, "model (Hugging Face through Kontor, checked)"):
        try:                                           # the socket file is what is asked here: the model then comes plainly (this probe only)
            import urllib.request
            os.makedirs(os.path.dirname(ai.model_path(repo, name)), exist_ok=True)
            with urllib.request.urlopen("https://huggingface.co/%s/resolve/main/%s" % (repo, name), timeout=120) as r, open(ai.model_path(repo, name), "wb") as f:
                f.write(r.read())
            ai._save("models.json", {"models": {mid: {"repo": repo, "file": name, "size": os.path.getsize(ai.model_path(repo, name)), "sha256": "0" * 64, "name": name}}})
            print("model: loaded plainly instead (%d bytes)" % os.path.getsize(ai.model_path(repo, name)))
        except Exception as e:
            print("no model:", type(e).__name__, e)
            return
    m = ai.models()[mid]
    body = {"messages": [{"role": "user", "content": "Once upon a time"}], "stream": True, "max_tokens": 8}
    plain_env = L.LocalAI._env
    for more in ({}, {"LLAMA_ARG_N_GPU_LAYERS": "0"}, {"LLAMA_ARG_N_GPU_LAYERS": "0", "LLAMA_ARG_DEVICE": "none"}):      # a runner's graphics chip is a stand-in: without it if it must be
        L.LocalAI._env = lambda self, key, tmp="", more=more: dict(plain_env(self, key, tmp), **more)
        try:
            ai.ensure(mid, 2048, "strict")
            pieces = list(ai.chat(body, threading.Event()))
            text = "".join(str(((x.get("choices") or [{}])[0].get("delta") or {}).get("content") or "") for x in pieces)
            print("today (127.0.0.1, strict, %s): sealed=%s, %d pieces, text=%r, tokens/s=%s" % (more or "as Kontor starts it", ai.sealed, len(pieces), text[:60], ai.tps))
            seen = subprocess.run(["/usr/sbin/lsof", "-nP", "-a", "-p", str(ai.proc.pid), "-i"], capture_output=True, text=True, timeout=20).stdout.strip().split("\n")
            print("   what it listens on today:", [x.split()[-2:] for x in seen[1:]])
            print("   its start:", [x for x in list(ai.tail) if "metal" in x.lower() or "device" in x.lower() or "offload" in x.lower()][:8])
            ai.stop()
            break
        except Exception as e:
            print("today (127.0.0.1, strict, %s) FAILED: %s %s | %s" % (more or "as Kontor starts it", type(e).__name__, str(e)[:300], " | ".join(list(ai.tail)[-6:])[:900]))
            ai.stop()
    for variant in (fits or ["path-literal", "literal"])[:3]:
        for level in ("strict", "basic"):
            own = L.own_tmp()
            sock = os.path.join(own, "m.sock")
            p, key, status, tail = sock_start(ai, rt, m, profile(dirs, level, variant, sock, own), sock, own)
            res = {"health": status[0], "socket bytes": len(sock.encode("utf-8"))}
            if status[0] == 200:
                res["without key"] = http_ask(sock, "POST", "/v1/chat/completions", dict(body, stream=False))[0]
                st, text = http_ask(sock, "POST", "/v1/chat/completions", dict(body, stream=False), key)
                res["chat"] = st
                try:
                    res["text"] = json.loads(text)["choices"][0]["message"]["content"][:60]
                except (ValueError, KeyError, IndexError, TypeError):
                    res["text"] = text[:200]
                seen = subprocess.run(["/usr/sbin/lsof", "-nP", "-a", "-p", str(p.pid), "-i"], capture_output=True, text=True, timeout=20).stdout.strip()
                res["network sockets"] = seen.split("\n")[1:] if seen else []
                res["socket file mode"] = oct(os.stat(sock).st_mode & 0o777)
            else:
                res["why"] = status[1][:200]; res["tail"] = tail[-8:]
            p.terminate()
            try:
                p.wait(8)
            except subprocess.TimeoutExpired:
                p.kill()
            print("socket file, %-6s %-13s %s" % (level, variant, "WORKS" if res.get("chat") == 200 and res.get("without key") == 401 and not res.get("network sockets") else "no   "),
                  json.dumps(res, ensure_ascii=False))
    print("== 3. what it asks macOS for (only printed) ==")
    if not fits:
        return
    own = L.own_tmp()
    sock = os.path.join(own, "m.sock")
    t0 = time.strftime("%Y-%m-%d %H:%M:%S")
    p, key, status, tail = sock_start(ai, rt, m, profile(dirs, "strict", fits[0], sock, own, more=["(deny mach-lookup)"]), sock, own)
    print("with every service of other programs denied: health", status[0], "| chat", http_ask(sock, "POST", "/v1/chat/completions", dict(body, stream=False), key)[0] if status[0] == 200 else "-",
          "|", tail[-4:] if status[0] != 200 else "")
    pid = p.pid
    p.terminate()
    try:
        p.wait(8)
    except subprocess.TimeoutExpired:
        p.kill()
    if os.environ.get("GITHUB_ACTIONS") == "true":      # the system's log of what the sandbox refused (a runner may read it)
        try:
            time.sleep(2)
            log = subprocess.run(["/usr/bin/sudo", "-n", "/usr/bin/log", "show", "--start", t0, "--style", "compact", "--predicate",
                                  'eventMessage CONTAINS "deny" AND eventMessage CONTAINS "mach-lookup"'], capture_output=True, text=True, timeout=120).stdout
            names = sorted({x.rsplit("mach-lookup", 1)[-1].strip() for x in log.split("\n") if "(%d)" % pid in x})
            print("asked for (%d): %s" % (len(names), names))
        except (OSError, subprocess.SubprocessError) as e:
            print("the log could not be read:", type(e).__name__, e)


def main():
    if sys.platform != "darwin" or not os.path.exists(L.SANDBOX):
        print("only on a Mac")
        return 0
    print("macOS", subprocess.run(["sw_vers", "-productVersion"], capture_output=True, text=True).stdout.strip(), os.uname().machine)
    os.environ["TMPDIR"] = subprocess.run(["getconf", "DARWIN_USER_TEMP_DIR"], capture_output=True, text=True).stdout.strip() or os.environ.get("TMPDIR", "")
    tempfile.tempdir = None
    data = os.path.realpath(tempfile.mkdtemp(prefix="probe-"))
    dirs = {"data": data, "prog": data + "-prog", "base": os.path.join(data, "assistant")}
    os.makedirs(os.path.join(dirs["base"], "runtime", "probe"))
    probe = os.path.join(dirs["base"], "runtime", "probe", "probe")          # "strict" starts only programs of the runtime folder
    with open(os.path.join(data, "probe.c"), "w") as f:
        f.write(PROBE_C)
    built = subprocess.run(["/usr/bin/cc", "-O1", "-o", probe, os.path.join(data, "probe.c")], capture_output=True, text=True)
    if built.returncode != 0:
        print("the small program was not built:", built.stderr[:500])
        return 1
    fits = rules(dirs, probe)
    try:
        real(dirs, fits)
    except Exception as e:                              # (whatever part 2 runs into: part 1 stands)
        print("llama.cpp: %s %s" % (type(e).__name__, str(e)[:400]))
    return 0 if fits else 1


if __name__ == "__main__":
    sys.exit(main())
