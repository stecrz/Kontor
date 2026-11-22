"""A stand-in for llama.cpp's llama-server in the tests: the same command line, /health and /v1/chat/completions (stream), no
model. What it answers is told by the question itself:

  call <tool> {json}     -> calls that tool (several lines: several calls); after the tool answered: "Ergebnis: <result>"
  think <text>           -> thoughts first, then "Fertig."
  slow                   -> writes slowly for a long time (to stop it)
  fail                   -> the server answers with an error
  toolong                -> "exceeds the available context size" while earlier turns are in the request
  silent                 -> says nothing (until it is asked again); mute -> says nothing at all
  loop <tool> {json}     -> calls that tool again and again, as long as tools are offered; then "Ende."
  written <tool> {json}  -> writes the call into its text (<tool_call>...</tool_call>) instead of handing it over
  cut                    -> an answer that runs into its limit (finish_reason "length")
  anything else          -> "Antwort: <question>"

The look at what to remember (a request that asks for JSON by a schema: Kontor's second, separate request after a question)
is answered from what that request holds -- nothing else reaches it:
  merke {json}           -> anywhere in what it was given (what the user said, earlier messages, the answer, known notes):
                            answers with that JSON ({"notes": [...], "forget": [...]}) -- so a test sees what reaches it
  Merk dir: <text>       -> in what the user said: a note with that text
  Vergiss: <text>        -> in what the user said: forgets the known notes that hold that text
  otherwise              -> nothing to note
(files beside it: notice-says -> answers with that file's text, whatever it is; notice-slow -> takes five seconds;
notice-fails -> the server answers with an error)

Started with --embedding (the model for finding by meaning): /v1/embeddings only. Each text's embedding (1024 numbers) is made
of its words -- a word counts by its first five letters, a few words count as the same (SAME: Ferien and Urlaub, Auto and
Wagen ...) and three times as much; the instruction before a question and the end mark after every text are left out. So texts
about the same thing are alike without a word in common, as with a real model. (embed-fails beside it: an error; record: the
last request to embed.json)

Files beside it tell it more (Kontor starts it with an environment of its own, so nothing else reaches it):
  record     -> it writes how it was started (arguments, names of environment variables) to started.json and the last
                request to request.json (the last look at what to remember: to notice.json)
  refuse     -> the start fails
  slowstart  -> /health says "loading" for a moment (its text: for that many seconds)
  script.json -> prepared answers (for the help images): [{"q": part of the question, "steps": [{"call": tool, "args": {...}} |
                {"think": text} | {"say": text}, ...]}] -- one step per round (a step after each tool result)
"""
import json
import re
import os
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HELP = """----- common params -----
-h,    --help, --usage                  print usage and exit
--version                               show version and build info
-c,    --ctx-size N                     size of the prompt context
-m,    --model FNAME                    model path to load
--offline                               Offline mode: forces use of cache, prevents network access
-np,   --parallel N                     number of server slots
--host HOST                             ip address to listen
--port PORT                             port to listen (default: 9931)
--ui,  --webui, --no-ui, --no-webui     whether to enable the built-in chat app
--api-key KEY                           API key to use for authentication
--slots, --no-slots                     expose slots monitoring endpoint
--jinja, --no-jinja                     whether to use jinja template engine for chat
--tools TOOL1,TOOL2,...                 experimental: built-in tools for AI agents
-mm,   --mmproj FILE                    path to a multimodal projector file
--embedding, --embeddings               restrict to only support embedding use case
--pooling {none,mean,cls,last,rank}     pooling type for embeddings
-b,    --batch-size N                   logical maximum batch size
-ub,   --ubatch-size N                  physical maximum batch size
"""


SAME = {"ferie": "urlaub", "urlau": "urlaub", "reise": "urlaub", "verre": "urlaub", "holid": "urlaub", "vacat": "urlaub",
        "auto": "wagen", "wagen": "wagen", "fahrz": "wagen", "oldti": "wagen", "pkw": "wagen",
        "rente": "ruhestand", "pensi": "ruhestand", "ruhes": "ruhestand", "aufho": "ruhestand"}


def embedding(text):
    import hashlib
    import math
    text = text.replace("<|endoftext|>", "")
    if "\nQuery:" in text:
        text = text.split("\nQuery:", 1)[1]
    v = [0.0] * 1024
    for w in re.findall(r"[a-zäöüß]+", text.lower()):
        if len(w) < 3:
            continue
        key, weight = (SAME[w[:5]], 3.0) if w[:5] in SAME else (w[:5], 1.0)
        h = hashlib.md5(key.encode()).digest()
        v[int.from_bytes(h[:2], "big") % 512] += weight * (1 if h[2] & 1 else -1)
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


def arg(name, default=None):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def main():
    if "--version" in sys.argv:
        print("version: 4711 (fake)\nbuilt for tests", file=sys.stderr)
        return 0
    if "--help" in sys.argv:
        print(HELP)
        return 0
    here = os.path.dirname(os.path.abspath(__file__))
    note = os.path.join(here, "started.json")
    if os.path.exists(os.path.join(here, "record")):       # the tests ask for a record of how it was started
        with open(note, "w") as f:
            json.dump({"argv": sys.argv[1:], "env": sorted(os.environ), "key_in_env": bool(os.environ.get("LLAMA_API_KEY"))}, f)
    if os.path.exists(os.path.join(here, "refuse")):       # ... or for a start that fails
        print("error: failed to load model (test)", file=sys.stderr)
        return 1
    key = os.environ.get("LLAMA_API_KEY", "")
    model = arg("--model") or arg("-m")
    if not model or not os.path.exists(model):
        print("error: model not found", file=sys.stderr)
        return 1
    slow = 0.0
    if os.path.exists(os.path.join(here, "slowstart")):
        with open(os.path.join(here, "slowstart")) as f:
            slow = float(f.read().strip() or 0.6)
    ready_at = time.time() + slow

    class H(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *a):
            pass

        def _json(self, code, obj):
            raw = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self):
            if self.path == "/health":
                return self._json(200, {"status": "ok"}) if time.time() >= ready_at else self._json(503, {"error": {"message": "Loading model"}})
            self._json(404, {"error": {"message": "File Not Found"}})

        def _send(self, obj):
            data = ("data: %s\n\n" % (obj if isinstance(obj, str) else json.dumps(obj))).encode()
            self.wfile.write(b"%x\r\n%s\r\n" % (len(data), data))
            self.wfile.flush()

        def do_POST(self):
            raw = self.rfile.read(int(self.headers.get("Content-Length") or 0))
            if self.headers.get("Authorization") != "Bearer " + key or not key:
                return self._json(401, {"error": {"message": "Invalid API Key"}})
            if self.path == "/v1/audio/transcriptions":            # a recording to write down: only with a model that hears (--mmproj)
                if "--mmproj" not in sys.argv or not os.path.exists(arg("--mmproj")):
                    return self._json(501, {"error": {"message": "The current model does not support audio input."}})
                mark = self.headers.get("Content-Type", "").split("boundary=")[-1].encode()
                parts = {}
                for chunk in raw.split(b"--" + mark):
                    head, _, data = chunk.partition(b"\r\n\r\n")
                    if b'name="' in head:
                        parts[head.split(b'name="')[1].split(b'"')[0].decode()] = data[:-2] if data.endswith(b"\r\n") else data
                wav = parts.get("file", b"")
                if wav[:4] != b"RIFF":
                    return self._json(400, {"error": {"message": "the input file is not a supported audio file"}})
                if os.path.exists(os.path.join(here, "record")):
                    with open(os.path.join(here, "audio.json"), "w") as f:
                        json.dump({"bytes": len(wav), "language": parts.get("language", b"").decode(), "fields": sorted(parts)}, f)
                return self._json(200, {"text": "language German<asr_text>Diktat mit %d Bytes.</asr_text>" % len(wav)})
            body = json.loads(raw or b"{}")
            if "--embedding" in sys.argv:                          # the model for finding by meaning: embeddings, nothing else
                if self.path != "/v1/embeddings":
                    return self._json(501, {"error": {"message": "This server does not support completions. Start it without --embedding"}})
                if os.path.exists(os.path.join(here, "record")):
                    with open(os.path.join(here, "embed.json"), "w") as f:
                        json.dump({"body": body, "argv": sys.argv[1:]}, f)
                if os.path.exists(os.path.join(here, "embed-fails")):
                    return self._json(500, {"error": {"message": "broken on purpose"}})
                texts = body.get("input") if isinstance(body.get("input"), list) else [body.get("input")]
                return self._json(200, {"object": "list", "data": [{"object": "embedding", "index": i, "embedding": embedding(str(t))} for i, t in enumerate(texts)]})
            if self.path != "/v1/chat/completions":
                return self._json(404, {"error": {"message": "not found"}})
            msgs = body.get("messages") or []
            noticed = None
            if isinstance((body.get("response_format") or {}).get("schema"), dict):       # the look at what to remember: answered from what it holds
                if os.path.exists(os.path.join(here, "record")):
                    with open(os.path.join(here, "notice.json"), "w") as f:
                        json.dump(body, f)
                if os.path.exists(os.path.join(here, "notice-fails")):
                    return self._json(500, {"error": {"message": "broken on purpose"}})
                given = json.loads(str((msgs[-1] if msgs else {}).get("content") or "{}"))
                texts = [str(given.get("said") or "")] + [str(x) for x in given.get("earlier") or []] + [str(given.get("answer") or "")] + [str(k.get("text") or "") for k in given.get("known") or []]
                noticed = {"notes": [], "forget": []}
                order = next((re.search(r"merke (\{.*\})", x, re.S) for x in texts if re.search(r"merke (\{.*\})", x, re.S)), None)
                said = str(given.get("said") or "")
                if os.path.exists(os.path.join(here, "notice-says")):           # a test puts the words into its mouth (also what is no JSON)
                    with open(os.path.join(here, "notice-says"), encoding="utf-8") as f:
                        noticed = f.read()
                elif order:
                    noticed = json.loads(order.group(1))
                else:
                    m = re.search(r"(?im)^\s*merk(?:e)? dir(?: bitte)?[:,]?\s*(?:dass\s+)?(.+)$", said)
                    if m and m.group(1).strip().lower() not in ("das", "das bitte", "dies"):
                        noticed["notes"].append({"text": m.group(1).strip()})
                    elif m and given.get("answer"):
                        noticed["notes"].append({"text": str(given["answer"])[:200]})
                    f = re.search(r"(?im)^\s*vergiss[:,]?\s*(?:dass\s+)?(.+)$", said)
                    if f:
                        noticed["forget"] = [k["id"] for k in given.get("known") or [] if f.group(1).strip().lower() in str(k.get("text") or "").lower()]
            elif os.path.exists(os.path.join(here, "record")):
                with open(os.path.join(here, "request.json"), "w") as f:
                    json.dump(body, f)
            last = msgs[-1] if msgs else {}
            users = [m for m in msgs if m.get("role") == "user"]
            q = str((users[-1] if users else {}).get("content") or "")
            if q.startswith(("[Page: ", "[Seite: ")) and "]\n" in q:           # Kontor's line before the question: where the user is
                q = q.split("]\n", 1)[1]
            if q.startswith("[Kontor: the user gave ") and "]\n" in q:         # ... and the receipts given with it
                q = q.split("]\n", 1)[1]
            script = None
            if os.path.exists(os.path.join(here, "script.json")):
                with open(os.path.join(here, "script.json"), encoding="utf-8") as f:
                    script = next((r for r in json.load(f) if r["q"] in q), None)
            if q.startswith("fail"):
                return self._json(500, {"error": {"message": "broken on purpose"}})
            if q.startswith("toolong") and len(users) > 1:
                return self._json(400, {"error": {"message": "request (99999 tokens) exceeds the available context size (8192 tokens)"}})
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
            delta = lambda d, fin=None: {"choices": [{"index": 0, "delta": d, "finish_reason": fin}], "object": "chat.completion.chunk"}
            asked = [re.sub(r"^\[Kontor: the user gave [^\n]*\]\n", "", str(m.get("content") or "").split("]\n", 1)[-1]) for m in users]
            first = next((x for x in reversed(asked) if not x.startswith("[Kontor:")), "")      # the question itself (not Kontor's reminder to answer)
            fin_reason = "stop"
            try:
                self._send(delta({"role": "assistant", "content": None}))
                names = {t["function"]["name"] for t in body.get("tools") or []}
                if noticed is not None:
                    if os.path.exists(os.path.join(here, "notice-slow")):
                        for _ in range(100):
                            self._send(delta({"content": " "}))
                            time.sleep(0.05)
                    text = noticed if isinstance(noticed, str) else json.dumps(noticed, ensure_ascii=False)
                    for i in range(0, len(text), 30):
                        self._send(delta({"content": text[i:i + 30]}))
                elif first.startswith("mute") or q.startswith("silent"):
                    pass
                elif first.startswith("loop "):
                    name, _, args = first[5:].partition(" ")
                    if names:
                        self._send(delta({"tool_calls": [{"index": 0, "id": "", "type": "function", "function": {"name": name, "arguments": args.strip() or "{}"}}]}))
                    else:
                        self._send(delta({"content": "Ende."}))
                elif first.startswith("written ") and last.get("role") != "tool":
                    name, _, args = first[8:].partition(" ")
                    text = 'Moment. <tool_call>\n{"name": "%s", "arguments": %s}\n</tool_call>' % (name, args.strip() or "{}")
                    for i in range(0, len(text), 9):
                        self._send(delta({"content": text[i:i + 9]}))
                elif q.startswith("cut"):
                    self._send(delta({"content": "Ein Anfang, der"}))
                    fin_reason = "length"
                elif script is not None:
                    done = 0                                       # tool results since the question: that many steps are behind us
                    for m in reversed(msgs):
                        if m.get("role") == "user":
                            break
                        done += m.get("role") == "tool"
                    calls = 0
                    for step in script["steps"][done:]:
                        if "think" in step:
                            for w in step["think"].split(" "):
                                self._send(delta({"reasoning_content": w + " "}))
                                time.sleep(0.01)
                            continue
                        if "call" in step:
                            self._send(delta({"tool_calls": [{"index": calls, "id": "call_%d" % calls, "type": "function",
                                                              "function": {"name": step["call"], "arguments": json.dumps(step.get("args") or {})}}]}))
                            calls += 1
                            break
                        text = step.get("say", "")
                        for i in range(0, len(text), 24):
                            self._send(delta({"content": text[i:i + 24]}))
                            time.sleep(0.005)
                        break
                elif last.get("role") == "tool":
                    text = "Ergebnis: " + str(last.get("content"))[:1500]
                    for i in range(0, len(text), 40):
                        self._send(delta({"content": text[i:i + 40]}))
                elif q.startswith("call "):
                    n = 0
                    for line in q.splitlines():
                        if not line.startswith("call "):
                            continue
                        name, _, args = line[5:].partition(" ")
                        if name not in names and not line.endswith("!"):       # a tool the request does not offer: plain text ("!" forces the call)
                            self._send(delta({"content": "kein Werkzeug " + name}))
                            continue
                        args = (args[:-1] if args.endswith("!") else args).strip() or "{}"
                        self._send(delta({"tool_calls": [{"index": n, "id": "call_%d" % n, "type": "function", "function": {"name": name, "arguments": ""}}]}))
                        half = len(args) // 2                                    # arguments arrive in pieces
                        for part in (args[:half], args[half:]):
                            self._send(delta({"tool_calls": [{"index": n, "function": {"arguments": part}}]}))
                        n += 1
                elif q.startswith("think "):
                    for w in q[6:].split():
                        self._send(delta({"reasoning_content": w + " "}))
                    self._send(delta({"content": "Fertig."}))
                elif q.startswith("slow"):
                    for i in range(400):
                        self._send(delta({"content": "wort%d " % i}))
                        time.sleep(0.05)
                else:
                    text = "Antwort: " + q
                    for i in range(0, len(text), 12):
                        self._send(delta({"content": text[i:i + 12]}))
                fin = delta({}, fin_reason)
                fin["timings"] = {"predicted_n": 7, "predicted_per_second": 42.0, "prompt_n": 3}
                self._send(fin)
                self._send("[DONE]")
                self.wfile.write(b"0\r\n\r\n")
            except (BrokenPipeError, ConnectionResetError):
                pass

    srv = ThreadingHTTPServer((arg("--host", "127.0.0.1"), int(arg("--port", "9931"))), H)
    srv.daemon_threads = True
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
