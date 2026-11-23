"""The model process on a real Mac -- GitHub's macOS job; skipped elsewhere. What "no network at all" means is asked of macOS
itself, inside the very profile Kontor starts a model with (llm_local.sandbox_profile):

  Rules      a small program built here listens on the socket file of its start and gets an answer through -- and nothing
             else of any network works: no address of this Mac to listen on, no connection going out (to an address, to
             another program's socket file), no socket file but that one. Without a socket file in the profile (as a new
             llama.cpp is tried) not even that. At both levels. Needs no network.
  RealLlama  llama.cpp's newest release and a tiny model, loaded, checked and started by Kontor's own code: its help says it
             can listen on a file (or Kontor would not install it), it answers over that file and only with the key of that
             start, and the process holds no socket of any network. Needs GitHub and Hugging Face: when they do not answer,
             it says so and is skipped.

    python3 tests/test_mac_model.py -v Rules
    python3 tests/test_mac_model.py -v RealLlama
"""
import json
import os
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import llm_local as L   # noqa: E402

ON_MAC = sys.platform == "darwin" and os.path.exists(L.SANDBOX) and os.path.exists("/usr/bin/cc")

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


def folders():
    """Kontor's folders as on a Mac: data, the program beside it, the assistant's own inside the data -- in the user's own
    temporary folder (where a model's folder of a start is made too)."""
    os.environ["TMPDIR"] = subprocess.run(["getconf", "DARWIN_USER_TEMP_DIR"], capture_output=True, text=True).stdout.strip() or os.environ.get("TMPDIR", "")
    tempfile.tempdir = None
    data = os.path.realpath(tempfile.mkdtemp(prefix="model-test-"))
    dirs = {"data": data, "prog": data + "-prog", "base": os.path.join(data, "assistant")}
    os.makedirs(os.path.join(dirs["base"], "runtime", "probe"))
    return dirs


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
    """ping -> pong from outside the sandbox: the answer, or the error."""
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
    """Something listening outside the sandbox (can a program inside connect out to it?)."""
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


def network_sockets(pid):
    """What a process holds of any network (addresses it listens on or is connected to), as the system lists it."""
    out = subprocess.run(["/usr/sbin/lsof", "-nP", "-a", "-p", str(pid), "-i"], capture_output=True, text=True, timeout=30).stdout.strip()
    return out.split("\n")[1:] if out else []


@unittest.skipUnless(ON_MAC, "the sandbox of macOS only on a Mac")
class Rules(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dirs = folders()
        cls.probe = os.path.join(cls.dirs["base"], "runtime", "probe", "probe")          # "strict" starts only programs of the runtime folder
        src = os.path.join(cls.dirs["data"], "probe.c")
        with open(src, "w") as f:
            f.write(PROBE_C)
        subprocess.run(["/usr/bin/cc", "-O1", "-o", cls.probe, src], check=True)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dirs["data"], ignore_errors=True)

    def sealed(self, level, sock, *args):
        prof = L.sandbox_profile(self.dirs["data"], self.dirs["prog"], self.dirs["base"], level, sock=sock)
        return subprocess.Popen([L.SANDBOX, "-p", prof, self.probe] + list(args), stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

    def test_only_its_own_socket_file(self):
        for level in ("strict", "basic"):
            own = L.own_tmp()
            other = os.path.realpath(tempfile.mkdtemp(prefix="other-"))
            sock = os.path.join(own, L.SOCK_NAME)
            try:
                # its own socket file: it listens there, and what is asked over it is answered
                p = self.sealed(level, sock, "listen-unix", sock)
                self.assertEqual(first_line(p), "listening", level)
                self.assertTrue(stat.S_ISSOCK(os.stat(sock).st_mode))
                self.assertEqual(ask("unix", sock), "pong", level)
                self.assertIn("served", end(p))
                os.remove(sock)
                # no address of this Mac
                p = self.sealed(level, sock, "listen-tcp", "0")
                self.assertEqual(first_line(p), "bind: Operation not permitted", level)
                end(p)
                # nothing going out: not to an address of this Mac, not to another program's socket file
                out = listener("tcp", None)
                self.assertEqual(end(self.sealed(level, sock, "connect-tcp", str(out.getsockname()[1]))), "connect: Operation not permitted", level)
                out.close()
                there = os.path.join(other, "o.sock")
                out = listener("unix", there)
                self.assertEqual(end(self.sealed(level, sock, "connect-unix", there)), "connect: Operation not permitted", level)
                out.close()
                # no other socket file: not elsewhere, not under another name in its own folder
                for path in (os.path.join(other, "x.sock"), os.path.join(own, "x.sock"), sock + "2"):
                    p = self.sealed(level, sock, "listen-unix", path)
                    self.assertEqual(first_line(p, 4), "bind: Operation not permitted", (level, path))
                    end(p)
                    self.assertFalse(os.path.exists(path))
                # ... and without a socket file in the rules (a new llama.cpp being tried): not even its own
                p = self.sealed(level, "", "listen-unix", sock)
                self.assertEqual(first_line(p, 4), "bind: Operation not permitted", level)
                end(p)
            finally:
                shutil.rmtree(own, ignore_errors=True); shutil.rmtree(other, ignore_errors=True)

    def test_the_test_would_notice(self):
        """Outside the sandbox the same program does all of it -- so a refusal above is the sandbox's."""
        own = os.path.realpath(tempfile.mkdtemp(prefix="plain-"))
        try:
            p = subprocess.Popen([self.probe, "listen-tcp", "0"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            line = first_line(p)
            self.assertTrue(line.startswith("listening "), line)
            self.assertEqual(ask("tcp", line.split()[-1]), "pong")
            end(p)
            out = listener("unix", os.path.join(own, "o.sock"))
            self.assertEqual(end(subprocess.Popen([self.probe, "connect-unix", os.path.join(own, "o.sock")], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)), "got pong")
            out.close()
            me = socket.socket()
            me.bind(("127.0.0.1", 0)); me.listen(1)
            self.assertTrue(any("LISTEN" in x for x in network_sockets(os.getpid())))          # and the system's list shows an address listened on
            me.close()
        finally:
            shutil.rmtree(own, ignore_errors=True)


@unittest.skipUnless(ON_MAC, "the sandbox of macOS only on a Mac")
class RealLlama(unittest.TestCase):
    REPO, FILE = "ggml-org/tiny-llamas", "stories260K.gguf"           # a model of a megabyte: it tells children's stories

    @classmethod
    def setUpClass(cls):
        cls.dirs = folders()
        cls.ai = L.LocalAI(cls.dirs["base"], cls.dirs["data"], cls.dirs["prog"])
        cls.opened = L._open
        token = os.environ.get("GH_TOKEN") or ""

        def with_token(url, kind, headers=None, timeout=30):
            # GitHub answers a runner without a name only now and then: the question for the newest release goes with the
            # job's own token (only to api.github.com, only in this test)
            if token and url.startswith("https://api.github.com/"):
                headers = dict(headers or {}, Authorization="Bearer " + token)
            return cls.opened(url, kind, headers, timeout)
        L._open = with_token

    @classmethod
    def tearDownClass(cls):
        cls.ai.stop()
        L._open = cls.opened
        shutil.rmtree(cls.dirs["data"], ignore_errors=True)

    def loaded(self, what):
        t0 = time.time()
        while self.ai.job and self.ai.job["state"] == "running" and time.time() - t0 < 300:
            time.sleep(0.3)
        v = self.ai.job_view() or {}
        if v.get("state") != "done":
            text = str(v.get("text") or v.get("state"))
            if "HTTP Error" in text or text.startswith(L.tr("s_ki_netz").split("%s")[0]) or v.get("state") == "running":
                self.skipTest("%s did not come over the network: %s" % (what, text))
            self.fail("%s: %s" % (what, text))

    def post(self, key, body):
        c = L._OnFile(self.ai.sock, timeout=60)
        try:
            c.request("POST", "/v1/chat/completions", json.dumps(body).encode("utf-8"),
                      dict({"Content-Type": "application/json"}, **({"Authorization": "Bearer " + key} if key else {})))
            r = c.getresponse()
            return r.status, r.read(4000).decode("utf-8", "replace")
        finally:
            c.close()

    def test_answers_over_its_file_and_holds_nothing_of_a_network(self):
        try:
            self.ai.install_runtime("strict")
        except (urllib.error.URLError, OSError) as e:
            self.skipTest("GitHub did not answer: %s" % e)
        self.loaded("llama.cpp")
        rt = self.ai.runtime()
        print("llama.cpp %s (%s)" % (rt.get("tag"), rt.get("version")), file=sys.stderr)
        self.assertIs(rt["sock"], True)                           # its own help says so (else Kontor would not have kept it)
        self.ai.download_model("", self.REPO, self.FILE)
        self.loaded("the model")
        mid = "%s/%s" % (self.REPO, self.FILE)
        body = {"messages": [{"role": "user", "content": "Once upon a time"}], "max_tokens": 8}
        for level in ("strict", "basic"):
            self.ai.ensure(mid, 2048, level)
            self.assertEqual((self.ai.state, self.ai.sealed), ("ready", level))
            sock, tmp, pid = self.ai.sock, self.ai.tmp, self.ai.proc.pid
            self.assertEqual((os.path.dirname(sock), os.path.basename(sock)), (tmp, L.SOCK_NAME))
            self.assertTrue(os.path.basename(tmp).startswith(L.TMP_PREFIX)); self.assertEqual(os.stat(tmp).st_mode & 0o777, 0o700)
            self.assertTrue(stat.S_ISSOCK(os.stat(sock).st_mode)); self.assertEqual(os.stat(sock).st_mode & 0o022, 0)
            pieces = list(self.ai.chat(dict(body, stream=True), threading.Event()))                # as Kontor asks it
            said = "".join(str(((x.get("choices") or [{}])[0].get("delta") or {}).get("content") or "") for x in pieces)
            self.assertTrue(said.strip(), pieces)
            self.assertEqual(self.post("", body)[0], 401); self.assertEqual(self.post("not-the-key", body)[0], 401)       # only with the key of this start
            self.assertEqual(self.post(self.ai.key, body)[0], 200)
            self.assertEqual(network_sockets(pid), [], level)     # no address listened on, nothing connected: not even on this Mac
            args = subprocess.run(["/bin/ps", "-ww", "-o", "args=", "-p", str(pid)], capture_output=True, text=True).stdout
            self.assertIn("--host %s" % sock, args); self.assertNotIn("--port", args); self.assertNotIn(self.ai.key, args)
            print("%s: %r, %s tokens/s" % (level, said[:40], self.ai.tps), file=sys.stderr)
        self.ai.stop()
        self.assertFalse(os.path.exists(tmp))                     # its folder of that start is gone, the socket file with it


if __name__ == "__main__":
    unittest.main()
