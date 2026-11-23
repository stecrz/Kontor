"""A stand-in for llama.cpp's llama-server in the tests: the same command line, /health and /v1/chat/completions (stream), no
model. What it answers is told by the question itself:

  call <tool> {json}     -> calls that tool (several lines: several calls); after the tool answered: "Ergebnis: <result>"
  think <text>           -> thoughts first, then "Fertig."
  slow                   -> writes slowly for a long time (to stop it)
  fail                   -> the server answers with an error
  toolong                -> "exceeds the available context size" while earlier turns are in the request
  silent                 -> says nothing (until it is asked again); mute -> says nothing at all
  loop <tool> {json}     -> calls that tool again and again, as long as it may (tools offered, tool_choice not "none"); then "Ende."
  stubborn <tool> {json} -> like loop, but when it may not call any more it writes the call into its text (Qwen's form
                            <tool_call><function=...>); asked to answer in words it says "Gut: Schluss."
  ponder <tool> {json}   -> thinks ("Ich brauche <tool>."), then calls the tool; after its result: "Ergebnis: <result>"
  badargs <tool>         -> calls the tool with arguments that break off ({"expression": "1+); after its result: "Ergebnis: ..."
                            ("badargs <tool> again": told that they were broken, it calls the tool once more, with {})
  written <tool> {json}  -> writes the call into its text (<tool_call>...</tool_call>) instead of handing it over
  cut                    -> an answer that runs into its limit (finish_reason "length")
  anything else          -> "Antwort: <question>"

The look at what to remember (a request that asks for JSON by a schema: Kontor's second, separate request after a question)
is answered from what that request holds -- nothing else reaches it (naming the names of notes: the capitalised words after the
first of each, and a made-up "Erfunden" that is in none; record: to names.json):
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

Like llama.cpp it refuses a conversation it cannot put into the model's template (HTTP 500): a tool call in it whose
arguments are no JSON object, thoughts (reasoning_content) that are no text, a message without content; a reasoning_effort
the template refuses (HTTP 400); a picture without a picture part (--mmproj). GET /props tells what the template can do
(chat_template_caps: no levels of thinking, earlier thoughts not kept; modalities: audio with an --mmproj named ...asr..., else vision) -- props.json beside
it changes that ({"chat_template_caps": {...}}), no-props makes it an older build that does not answer there.

Files beside it tell it more (Kontor starts it with an environment of its own, so nothing else reaches it):
  noeyes     -> the start fails when it is given a picture part (--mmproj)
  (a question with "absturz" and a picture in the request: the process ends at once)
  record     -> it writes how it was started (arguments, names of environment variables) to started.json and the last
                request to request.json (the last look at what to remember: to notice.json)
  refuse     -> the start fails
  slowstart  -> /health says "loading" for a moment (its text: for that many seconds)
  nosock     -> an older llama.cpp: its help knows no socket file for --host, and it listens on none
  script.json -> prepared answers (for the help images): [{"q": part of the question, "steps": [{"call": tool, "args": {...}} |
                {"think": text} | {"say": text}, ...]}] -- one step per round (a step after each tool result); a call or a say
                may carry its thoughts ("think") with it
"""
import json
import re
import os
import socket
import socketserver
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
--host HOST                             IP addresses to listen on, comma-separated, or UNIX socket paths
                                        ending in .sock; with multiple TCP addresses, :: binds IPv6 only;
                                        overlapping addresses result in undefined behavior (default:
                                        127.0.0.1)
                                        (env: LLAMA_ARG_HOST)
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


# what llama.cpp's help says about --host (b12648, as GitHub's Mac printed it: over several lines)
SOCK_SAID = HELP.split("--host HOST", 1)[1].split("(env: LLAMA_ARG_HOST)")[0].strip()


def main():
    if "--version" in sys.argv:
        print("version: 4711 (fake)\nbuilt for tests", file=sys.stderr)
        return 0
    here = os.path.dirname(os.path.abspath(__file__))
    old = os.path.exists(os.path.join(here, "nosock"))
    if "--help" in sys.argv:
        print(HELP.replace(SOCK_SAID, "ip address to listen (default: 127.0.0.1)") if old else HELP)
        return 0
    note = os.path.join(here, "started.json")
    if os.path.exists(os.path.join(here, "record")):       # the tests ask for a record of how it was started
        with open(note, "w") as f:
            json.dump({"argv": sys.argv[1:], "env": sorted(os.environ), "key_in_env": bool(os.environ.get("LLAMA_API_KEY"))}, f)
    if os.path.exists(os.path.join(here, "refuse")):       # ... or for a start that fails
        print("error: failed to load model (test)", file=sys.stderr)
        return 1
    if os.path.exists(os.path.join(here, "noeyes")) and "--mmproj" in sys.argv:       # ... only with its picture part
        print("error: failed to load mmproj (test)", file=sys.stderr)
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

        def _props(self):
            """What llama.cpp's /props says of the model, as far as Kontor reads it."""
            part = "--mmproj" in sys.argv and os.path.exists(arg("--mmproj") or "") and "--embedding" not in sys.argv
            hears = part and "asr" in os.path.basename(arg("--mmproj")).lower()       # an audio part (a speech model's) or a picture part
            props = {"default_generation_settings": {"n_ctx": int(arg("--ctx-size", "0") or 0)}, "total_slots": int(arg("--parallel", "1") or 1),
                     "modalities": {"vision": part and not hears, "audio": hears}, "build_info": "b4711-fake",
                     "chat_template_caps": {"supports_tools": True, "supports_tool_calls": True, "supports_preserve_reasoning": False,
                                            "supports_reasoning_effort": False, "reasoning_effort_levels": [], "reasoning_effort_rejected": []}}
            if os.path.exists(os.path.join(here, "props.json")):
                with open(os.path.join(here, "props.json"), encoding="utf-8") as f:
                    for k, v in json.load(f).items():
                        props[k] = dict(props.get(k) or {}, **v) if isinstance(v, dict) else v
            return props

        def _refused(self, body):
            """Why llama.cpp would not take this conversation (None: it does) -- (status, message)."""
            caps = self._props()["chat_template_caps"]
            effort = body.get("reasoning_effort")
            if isinstance(effort, str) and effort in caps["reasoning_effort_rejected"]:
                return 400, 'reasoning_effort "%s" is not supported by the chat template' % effort
            for m in body.get("messages") or []:
                if not isinstance(m, dict) or "role" not in m:
                    return 500, "Missing 'role' in message"
                if m["role"] != "assistant" and "content" not in m:
                    return 400, "All non-assistant messages must contain 'content'"
                if m["role"] == "assistant" and "content" not in m and "tool_calls" not in m:
                    return 400, "Assistant message must contain either 'content' or 'tool_calls'!"
                if "reasoning_content" in m and not isinstance(m["reasoning_content"], str):
                    return 500, "type must be string, but is %s" % type(m["reasoning_content"]).__name__
                c = m.get("content")
                if isinstance(c, list):
                    for part in c:
                        if not isinstance(part, dict) or part.get("type") not in ("text", "image_url"):
                            return 500, "Unsupported content part type"
                        if part["type"] == "image_url":
                            url = str((part.get("image_url") or {}).get("url") or "")
                            if not self._props()["modalities"]["vision"]:
                                return 500, "image input is not supported - hint: if this is unexpected, you may need to provide the mmproj"
                            if not url.startswith("data:image/"):
                                return 500, "this stand-in takes pictures only as data: (never an address)"
                elif c is not None and not isinstance(c, str):
                    return 500, "Invalid 'content' type: expected string or array"
                for tc in m.get("tool_calls") or []:
                    args = ((tc or {}).get("function") or {}).get("arguments")
                    try:
                        if not isinstance(json.loads(args) if isinstance(args, str) else args, dict):
                            raise ValueError
                    except ValueError:
                        return 500, "Failed to parse tool call arguments as JSON: " + str(args)[:80]
            return None

        def do_GET(self):
            if self.path == "/health":
                return self._json(200, {"status": "ok"}) if time.time() >= ready_at else self._json(503, {"error": {"message": "Loading model"}})
            if self.path == "/props" and not os.path.exists(os.path.join(here, "no-props")):
                if self.headers.get("Authorization") != "Bearer " + key or not key:
                    return self._json(401, {"error": {"message": "Invalid API Key"}})
                return self._json(200, self._props())
            self._json(404, {"error": {"message": "File Not Found"}})

        def _send(self, obj):
            data = ("data: %s\n\n" % (obj if isinstance(obj, str) else json.dumps(obj))).encode()
            self.wfile.write(b"%x\r\n%s\r\n" % (len(data), data))
            self.wfile.flush()

        def do_POST(self):
            raw = self.rfile.read(int(self.headers.get("Content-Length") or 0))
            if self.headers.get("Authorization") != "Bearer " + key or not key:
                return self._json(401, {"error": {"message": "Invalid API Key"}})
            if self.path == "/v1/audio/transcriptions":            # a recording to write down: only with a model that hears (--mmproj, an audio part)
                if not self._props()["modalities"]["audio"]:
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
            no = self._refused(body)
            if no is not None:
                return self._json(no[0], {"error": {"message": no[1]}})
            msgs = body.get("messages") or []
            noticed = None
            if isinstance((body.get("response_format") or {}).get("schema"), dict):       # the look at what to remember: answered from what it holds
                given = json.loads(str((msgs[-1] if msgs else {}).get("content") or "{}"))
                if os.path.exists(os.path.join(here, "record")) and not isinstance(given.get("notes"), list):
                    with open(os.path.join(here, "notice.json"), "w") as f:
                        json.dump(body, f)
                if os.path.exists(os.path.join(here, "notice-fails")):
                    return self._json(500, {"error": {"message": "broken on purpose"}})
                if isinstance(given.get("notes"), list):           # naming the names in notes typed in the settings: the capitalised words after the first
                    if os.path.exists(os.path.join(here, "record")):
                        with open(os.path.join(here, "names.json"), "w") as f:
                            json.dump(body, f)
                    named = {"notes": [{"id": n.get("id"), "names": re.findall(r"(?<=\s)[A-ZÄÖÜ][\wäöüß-]{3,}", str(n.get("text") or "")) + ["Erfunden"]} for n in given["notes"]]}
                    given = {"said": "", "names": named}
                texts = [str(given.get("said") or "")] + [str(x) for x in given.get("earlier") or []] + [str(given.get("answer") or "")] + [str(k.get("text") or "") for k in given.get("known") or []]
                noticed = {"notes": [], "forget": []}
                order = None
                for x in texts:                                     # (one that is no JSON -- written inside other JSON, as a tool's result in the answer: not an order)
                    for m in re.finditer(r"merke (\{.*\})", x, re.S):
                        try:
                            json.loads(m.group(1))
                            order = order or m
                        except ValueError:
                            pass
                said = str(given.get("said") or "")
                if given.get("names"):
                    noticed = given["names"]
                elif os.path.exists(os.path.join(here, "notice-says")):           # a test puts the words into its mouth (also what is no JSON)
                    with open(os.path.join(here, "notice-says"), encoding="utf-8") as f:
                        noticed = f.read()
                elif order:
                    noticed = json.loads(order.group(1))
                else:
                    m = re.search(r"(?im)^\s*merk(?:e)? dir(?: bitte)?[:,]?\s*(?:dass\s+)?(.+)$", said)
                    if m and m.group(1).strip().lower() not in ("das", "das bitte", "dies"):
                        noticed["notes"].append({"text": m.group(1).strip(), "names": []})
                    elif m and given.get("answer"):
                        noticed["notes"].append({"text": str(given["answer"])[:200], "names": []})
                    f = re.search(r"(?im)^\s*vergiss[:,]?\s*(?:dass\s+)?(.+)$", said)
                    if f:
                        noticed["forget"] = [k["id"] for k in given.get("known") or [] if f.group(1).strip().lower() in str(k.get("text") or "").lower()]
            elif os.path.exists(os.path.join(here, "record")):
                with open(os.path.join(here, "request.json"), "w") as f:
                    json.dump(body, f)
            last = msgs[-1] if msgs else {}
            users = [m for m in msgs if m.get("role") == "user"]
            pics = 0
            for m in users:                                 # a message of several parts (text beside pictures): its text, and how many pictures
                if isinstance(m.get("content"), list):
                    seen = sum(1 for x in m["content"] if x.get("type") == "image_url")
                    pics += seen
                    m["content"] = "".join(str(x.get("text") or "") for x in m["content"] if x.get("type") == "text") + (" [%d Bild(er) gesehen]" % seen if seen else "")
            if pics and any("absturz" in str(m.get("content") or "") for m in users):
                os._exit(3)                                 # falls over at a picture (as reported of some models)
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
                elif first.startswith(("loop ", "stubborn ")):
                    kind, _, rest = first.partition(" ")
                    name, _, args = rest.partition(" ")
                    if names and body.get("tool_choice") != "none":
                        self._send(delta({"tool_calls": [{"index": 0, "id": "", "type": "function", "function": {"name": name, "arguments": args.strip() or "{}"}}]}))
                    elif kind == "stubborn" and not str(users[-1].get("content") or "").startswith("[Kontor: now answer"):
                        text = "Noch eins. <tool_call>\n<function=%s>\n%s</function>\n</tool_call>" % (name, "".join(
                            "<parameter=%s>\n%s\n</parameter>\n" % (k, v if isinstance(v, str) else json.dumps(v)) for k, v in json.loads(args.strip() or "{}").items()))
                        for i in range(0, len(text), 11):
                            self._send(delta({"content": text[i:i + 11]}))
                    else:
                        self._send(delta({"content": "Gut: Schluss." if kind == "stubborn" else "Ende."}))
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
                            if "call" not in step and "say" not in step:      # (thoughts alone: the next step follows in the same round)
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
                elif first.startswith("ponder ") and last.get("role") != "tool":
                    name, _, args = first[7:].partition(" ")
                    for w in ("Ich brauche %s." % name).split(" "):
                        self._send(delta({"reasoning_content": w + " "}))
                    self._send(delta({"tool_calls": [{"index": 0, "id": "call_0", "type": "function", "function": {"name": name, "arguments": args.strip() or "{}"}}]}))
                elif first.startswith("badargs ") and last.get("role") != "tool":
                    self._send(delta({"tool_calls": [{"index": 0, "id": "call_0", "type": "function", "function": {"name": first[8:].split()[0], "arguments": '{"expression": "1+'}}]}))
                elif first.startswith("badargs ") and first.rstrip().endswith(" again") and "not a complete JSON object" in str(last.get("content")):
                    self._send(delta({"tool_calls": [{"index": 0, "id": "call_1", "type": "function", "function": {"name": first[8:].split()[0], "arguments": "{}"}}]}))
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

    host = arg("--host", "127.0.0.1")
    if host.endswith(".sock") and not old:                 # as llama.cpp's server: a socket file instead of an address (the port is ignored)
        class OnFile(ThreadingHTTPServer):
            address_family = socket.AF_UNIX

            def server_bind(self):                         # (HTTPServer's own asks for the name of the host, which a file has not)
                socketserver.TCPServer.server_bind(self)
                self.server_name, self.server_port = "localhost", 0
        srv = OnFile(host, H)
    else:
        srv = ThreadingHTTPServer((host, int(arg("--port", "9931"))), H)
    srv.daemon_threads = True
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
