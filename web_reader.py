"""Reads one web address for the assistant's internet search (web_search.py) -- in a process of its own, started for that one
request and ended after it (python3 -I: nothing of Kontor is imported, no settings, no other code). On the Mac it runs inside
the system's sandbox: network only to port 443 of other machines, nothing read in your home folder or in Kontor's data, nothing
written but temporary files, no other programs.

It gets the request on stdin as JSON -- {"url", "hosts", "method", "headers", "body", "as", "max_bytes", "max_text", "timeout",
"focus"} -- checks the address again (https, port 443, one of the hosts named, no address of this machine or of the local
network), fetches it (GET; POST only to the one search service that has no other way), follows a redirect only to the same
hosts, keeps no cookies, reads at most max_bytes within timeout seconds, and writes plain data to stdout as JSON:
  json  the parsed answer          xml   the records of the document (elements holding only text, as {tag: text})
  csv   the rows                   html  {title, text, lang, paywall}     text  the text
A question to Claude (Anthropic's Messages API) goes its own way (ask_claude): {"url", "body", "key", ...} -- the text given is
sent to the one fixed address with your key in its header, and only what Kontor uses of the answer comes back.
Nothing else ever leaves this process; what it read is gone when it ends.
"""
import codecs
import csv
import http.client
import io
import ipaddress
import json
import re
import socket
import ssl
import sys
import time
import urllib.error
import urllib.request
from html.parser import HTMLParser
from urllib.parse import urlparse
from xml.parsers import expat

MAX_BYTES = 8 << 20                 # an answer larger than this is never read
MAX_TEXT = 200000                   # characters of text handed back at most
MAX_SECONDS = 40
POST_ONLY = {"api.tavily.com": ("/search",), "api.anthropic.com": ("/v1/messages",)}     # the services that take their question only as POST (no cookies, no forms)
# Claude (Anthropic's Messages API): the one address a key for it is ever sent to, the version of that interface (its header
# anthropic-version), how long an answer may take (it searches and thinks first) and what such a key looks like -- an API key
# of Anthropic's Console, never the login of a subscription
CLAUDE = "https://api.anthropic.com/v1/messages"
CLAUDE_VERSION = "2026-10-21"
CLAUDE_SECONDS = 300
CLAUDE_KEY = re.compile(r"sk-ant-api[A-Za-z0-9_\-]{20,300}")
SKIP = {"script", "style", "noscript", "svg", "template", "iframe", "nav", "footer", "header", "form", "aside", "button", "select", "canvas", "object"}
BLOCK = {"p", "div", "br", "li", "ul", "ol", "tr", "table", "h1", "h2", "h3", "h4", "h5", "h6", "section", "article", "main", "blockquote", "pre", "dd", "dt", "dl"}


class Refused(Exception):
    """The request breaks a rule (its code is all that is handed back)."""


def host_ok(url: str, hosts) -> str:
    """The host of url if it may be fetched: https, port 443, no user in it, one of the hosts named exactly -- never a bare IP
    address, a name without a dot or one of this machine."""
    u = urlparse(url)
    host = (u.hostname or "").lower().rstrip(".")
    if u.scheme != "https":
        raise Refused("scheme")
    if not host or u.username or u.password or "@" in u.netloc:
        raise Refused("host")
    try:
        port = u.port
    except ValueError:
        raise Refused("host")
    if port not in (None, 443):
        raise Refused("port")
    if host not in {str(h).lower() for h in hosts or ()}:
        raise Refused("host")
    try:
        ipaddress.ip_address(host.strip("[]"))
        raise Refused("ip")
    except ValueError:
        pass
    if "." not in host or host.endswith((".local", ".localhost", ".internal", ".lan", ".home", ".arpa")) or host == "localhost":
        raise Refused("host")
    return host


def public(host: str) -> str:
    """The address to connect to: every address the name stands for must be a global one (not this machine, not the local
    network, not Tailscale's 100.64.0.0/10, nothing reserved) -- the connection then goes to exactly the one checked here."""
    try:
        infos = socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        raise Refused("dns")
    ips = []
    for info in infos:
        ip = ipaddress.ip_address(str(info[4][0]).split("%")[0])
        if not global_address(ip):
            raise Refused("private")
        ips.append(str(ip))
    if not ips:
        raise Refused("dns")
    return ips[0]


NAT64 = ipaddress.ip_network("64:ff9b::/96")             # an IPv4 address reached through a translator (RFC 6052): its last 32 bits
NAT64_LOCAL = ipaddress.ip_network("64:ff9b:1::/48")     # the same inside one network (RFC 8215): never the internet


def inner_addresses(ip) -> list:
    """The IPv4 addresses an IPv6 address carries inside it -- where a connection to it ends up: mapped (::ffff:a.b.c.d),
    the old compatible form (::a.b.c.d), through a translator (64:ff9b::a.b.c.d), 6to4 (2002:...), Teredo."""
    if ip.version != 6:
        return []
    inner = [ip.ipv4_mapped, ip.sixtofour] + list(ip.teredo or ())
    if int(ip) >> 32 == 0 or ip in NAT64:
        inner.append(ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF))
    return [x for x in inner if x is not None]


def global_address(ip) -> bool:
    """Is this an address of the internet -- itself and every IPv4 address inside it (not this machine, not the local
    network, not Tailscale, nothing reserved, no multicast)?"""
    if not ip.is_global or ip.is_multicast or (ip.version == 6 and ip in NAT64_LOCAL):
        return False
    return all(x.is_global and not x.is_multicast for x in inner_addresses(ip))


class Redirect(urllib.request.HTTPRedirectHandler):
    max_redirections = 3

    def __init__(self, hosts, check):
        self.hosts, self.check = hosts, check

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        self.check(host_ok(newurl, self.hosts))                 # (a new host is checked and pinned like the first)
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new is not None:
            new.remove_header("Cookie")
        return new


def _pinned(pins: dict):
    """A connection to the address checked for its host (no second lookup between the check and the connection); the
    certificate is still checked for the host's name (SNI)."""
    class Pinned(http.client.HTTPSConnection):
        def connect(self):
            ip = pins.get(str(self.host).lower())
            if not ip:
                raise Refused("dns")
            sock = socket.create_connection((ip, self.port or 443), self.timeout)
            self.sock = self._context.wrap_socket(sock, server_hostname=self.host)
    return Pinned


class _PinnedHTTPS(urllib.request.HTTPSHandler):
    def __init__(self, ctx, pins):
        super().__init__(context=ctx)
        self.ctx, self.pins = ctx, pins

    def https_open(self, req):
        return self.do_open(_pinned(self.pins), req, context=self.ctx)


def _build(ctx, hosts, check, pins=None):
    """No proxy, no cookies, no file, ftp or data addresses: https to the checked address only, and redirects to the same
    hosts only."""
    o = urllib.request.OpenerDirector()
    for h in (urllib.request.ProxyHandler({}), _PinnedHTTPS(ctx, pins if pins is not None else {}), urllib.request.HTTPDefaultErrorHandler(),
              Redirect(hosts, check), urllib.request.HTTPErrorProcessor()):
        o.add_handler(h)
    return o


def fetch(req: dict, open_=None, own=None, longest: float = MAX_SECONDS) -> dict:
    """The request carried out: {"ok", "status", "url", "type", "charset", "raw"} (raw: bytes) -- or Refused. own: headers a
    function of this file adds itself, never taken from the request (ask_claude: nothing else reaches Claude's host);
    longest: the most seconds it may take."""
    url, hosts = str(req.get("url") or ""), list(req.get("hosts") or [])
    host = host_ok(url, hosts)
    method = "POST" if req.get("method") == "POST" else "GET"
    if (method == "POST" and urlparse(url).path not in POST_ONLY.get(host, ())) or (host == urlparse(CLAUDE).hostname and own is None):
        raise Refused("method")
    max_bytes = max(1, min(MAX_BYTES, int(req.get("max_bytes") or MAX_BYTES)))
    timeout = max(1.0, min(float(req.get("timeout") or 20), longest))
    test = req.get("_check") if callable(req.get("_check")) else None
    pins: dict = {}

    def check(h: str) -> None:                          # each host (also one a redirect leads to): checked, then its address pinned
        ip = test(h) if test else public(h)
        if ip:
            pins[h] = ip
    check(host)
    headers = {"User-Agent": str(req.get("user_agent") or "Mozilla/5.0 (compatible)"), "Accept": str((req.get("headers") or {}).get("Accept") or "*/*"),
               "Accept-Encoding": "identity"}
    for k, v in (req.get("headers") or {}).items():
        if str(k).lower() in ("accept", "authorization", "content-type", "accept-language") and isinstance(v, str) and "\n" not in v and "\r" not in v:
            headers[str(k)] = v
        elif str(k).lower() == "x-tavily-access-mode" and v == "keyless" and host in POST_ONLY:      # Tavily without a key
            headers["X-Tavily-Access-Mode"] = v
    if any(k.lower() == "authorization" for k in headers):   # a key or no key -- never both
        headers.pop("X-Tavily-Access-Mode", None)
    headers.update(own or {})
    data = str(req.get("body") or "").encode("utf-8") if method == "POST" else None
    r = urllib.request.Request(url, data=data, headers=headers, method=method)
    t0 = time.time()
    try:
        resp = (open_ or _build(ssl.create_default_context(), hosts, check, pins).open)(r, timeout=timeout)
    except urllib.error.HTTPError as e:
        return dict({"ok": False, "error": "http", "status": e.code}, **_said(e, req.get("error_words")))
    except Refused:
        raise
    except (urllib.error.URLError, OSError, ssl.SSLError, ValueError) as e:
        if isinstance(getattr(e, "reason", None), Refused):
            raise e.reason
        return {"ok": False, "error": "timeout" if isinstance(getattr(e, "reason", e), socket.timeout) else "network"}
    with resp:
        final = getattr(resp, "url", url) or url
        host_ok(final, hosts)
        ctype = str(resp.headers.get("Content-Type") or "")
        try:
            size = int(resp.headers.get("Content-Length") or 0)
        except ValueError:
            size = 0
        if size > max_bytes:
            return {"ok": False, "error": "size", "status": getattr(resp, "status", 200)}
        buf = bytearray()
        while True:
            if time.time() - t0 > timeout:
                return {"ok": False, "error": "timeout"}
            try:
                chunk = resp.read(65536)
            except (socket.timeout, OSError):
                return {"ok": False, "error": "timeout"}
            if not chunk:
                break
            buf += chunk
            if len(buf) > max_bytes:
                return {"ok": False, "error": "size", "status": getattr(resp, "status", 200)}
    m = re.search(r"charset=([\w.:-]+)", ctype, re.I)
    return {"ok": True, "status": getattr(resp, "status", 200), "url": final, "type": ctype.split(";")[0].strip().lower(), "charset": m.group(1) if m else "",
            "raw": bytes(buf)}


def _said(e, words) -> dict:
    """Which of the words the request named stand in an error's answer (its first bytes, lower case) -- never the answer
    itself: so Kontor can tell why a service said no (no credit left) without taking a line of its text."""
    try:
        text = e.read(4096).decode("utf-8", "replace").lower()
    except Exception:                                  # no answer with the error, or one that cannot be read: nothing said
        return {}
    hit = [w for w in (words if isinstance(words, list) else [])[:8] if isinstance(w, str) and 3 <= len(w) <= 40 and w.lower() in text]
    return {"said": hit} if hit else {}


def ask_claude(req: dict, open_=None) -> dict:
    """The one request to Claude (Anthropic's Messages API): the text given -- the POST the card showed, whole -- to the one
    fixed address, with your key and the version of the interface in its headers. The address, its host, the method and the
    headers stand here and not in the request: one that names another address, or brings no text or no key that looks like
    one, is refused, and whatever else it names (hosts, a method, headers) is not looked at -- the key can go nowhere else
    (a redirect could only stay on that host). Handed back is only what Kontor uses of the answer (claude_answer), or that
    there is none."""
    key, body = req.get("key"), req.get("body")
    if req.get("url") != CLAUDE or not isinstance(key, str) or not CLAUDE_KEY.fullmatch(key) or not isinstance(body, str) or not body.strip():
        raise Refused("request")
    ask = {"url": CLAUDE, "hosts": [urlparse(CLAUDE).hostname], "method": "POST", "body": body, "headers": {"Content-Type": "application/json"}}
    ask.update({k: req[k] for k in ("timeout", "max_bytes", "user_agent", "error_words", "_check") if k in req})
    res = fetch(ask, open_, {"x-api-key": key, "anthropic-version": CLAUDE_VERSION}, CLAUDE_SECONDS)
    if not res.get("ok"):
        return res
    res = convert(res, {"as": "json"})
    res["data"] = claude_answer(res["data"])
    return res


def claude_answer(msg) -> dict:
    """Of Claude's answer what Kontor uses, as plain data: its text piece by piece, each with the sources it cites (address,
    title); what its own searches found (address, title, age) and how many of them failed; how the answer ended; the figures
    of its use (tokens in and out, searches). Nothing else comes out of this process -- not what it thought, nothing
    encrypted."""
    if not isinstance(msg, dict) or not isinstance(msg.get("content"), list):
        raise Refused("parse")
    cut = lambda v, n: str(v if isinstance(v, str) else "")[:n]
    parts, found, failed = [], [], 0
    for b in msg["content"][:400]:
        if not isinstance(b, dict):
            continue
        if b.get("type") == "text" and isinstance(b.get("text"), str):
            cites = b.get("citations") if isinstance(b.get("citations"), list) else []
            parts.append({"text": b["text"][:MAX_TEXT], "sources": [{"url": cut(c.get("url"), 500), "title": cut(c.get("title"), 200)} for c in cites[:20] if isinstance(c, dict)]})
        elif b.get("type") == "web_search_tool_result":
            got = b.get("content")
            failed += 0 if isinstance(got, list) else 1    # (an error of the search stands there instead of its results)
            found += [{"url": cut(r.get("url"), 500), "title": cut(r.get("title"), 200), "age": cut(r.get("page_age"), 40)}
                      for r in (got if isinstance(got, list) else [])[:20] if isinstance(r, dict)]
    use = msg.get("usage") if isinstance(msg.get("usage"), dict) else {}
    tools = use.get("server_tool_use") if isinstance(use.get("server_tool_use"), dict) else {}
    n = lambda v: v if isinstance(v, int) and not isinstance(v, bool) and 0 <= v < 10 ** 9 else 0
    return {"model": cut(msg.get("model"), 80), "stop": cut(msg.get("stop_reason"), 40), "parts": parts, "results": found[:100], "failed": failed,
            "usage": {"in": n(use.get("input_tokens")) + n(use.get("cache_creation_input_tokens")) + n(use.get("cache_read_input_tokens")),
                      "out": n(use.get("output_tokens")), "searches": n(tools.get("web_search_requests"))}}


def decode(raw: bytes, charset: str, html: bool = False) -> str:
    """The text in the page's character set -- one that is no text encoding (rot13, hex, base64 ...) or does not fit: UTF-8."""
    cs = charset
    if not cs and html:
        m = re.search(rb"<meta[^>]+charset=[\"']?([\w.:-]+)", raw[:4096], re.I)
        cs = m.group(1).decode("ascii", "replace") if m else ""
    try:
        if not getattr(codecs.lookup(cs or "utf-8"), "_is_text_encoding", True):
            raise LookupError(cs)
        return raw.decode(cs or "utf-8", "replace")
    except (LookupError, ValueError, TypeError):
        return raw.decode("utf-8", "replace")


def _false(v) -> bool:
    """false, "false", "FALSE", http(s)://schema.org/False -- what marks a page as not free to read."""
    t = str(v if v is not None else "").strip().strip('"').strip().lower()
    return t in ("false", "0", "no") or bool(re.fullmatch(r"https?://(www\.)?schema\.org/false", t))


class _Text(HTMLParser):
    """The readable text of a page: without scripts, styles, menus, forms; paragraphs kept as lines. focus: only what stands
    inside elements of these classes (or the page's <article>/<main>), when the page has such."""

    def __init__(self, focus):
        super().__init__(convert_charrefs=True)
        self.focus = set(focus or ())
        self.parts, self.inside, self.skip, self.depth = {"all": [], "focus": []}, 0, 0, []
        self.title, self.in_title, self.lang, self.ld, self.in_ld, self.closed = "", False, "", [], False, False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "html" and a.get("lang"):
            self.lang = str(a["lang"])[:10]
        if tag == "title":
            self.in_title = True
        if tag == "script" and str(a.get("type") or "").lower() == "application/ld+json":
            self.in_ld = True
        if str(a.get("itemprop") or "").strip().lower() == "isaccessibleforfree" and _false(a.get("content") if a.get("content") is not None else a.get("href")):
            self.closed = True                        # <meta itemprop="isAccessibleForFree" content="false">, <link ... href="https://schema.org/False">
        classes = set(str(a.get("class") or "").split())
        hit = bool(classes & self.focus) or (not self.focus and tag in ("article", "main"))
        if tag in ("br", "hr", "img", "meta", "link", "input", "source", "wbr", "area", "col", "embed", "param", "track"):
            if tag == "br":
                self._add("\n")
            return
        self.depth.append((tag, hit))
        if hit:
            self.inside += 1
        if tag in SKIP:
            self.skip += 1
        if tag in BLOCK:
            self._add("\n")

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False
        if tag == "script":
            self.in_ld = False
        while self.depth:
            t, hit = self.depth.pop()
            if hit:
                self.inside -= 1
            if t in SKIP:
                self.skip -= 1
            if t == tag:
                break
        if tag in BLOCK:
            self._add("\n")

    def handle_data(self, data):
        if self.in_title:
            self.title += data
        if self.in_ld:
            self.ld.append(data)
        if not self.skip:
            self._add(data)

    def _add(self, s):
        self.parts["all"].append(s)
        if self.inside > 0:
            self.parts["focus"].append(s)


def html_text(page: str, focus=None, max_text: int = MAX_TEXT) -> dict:
    p = _Text(focus)
    try:
        p.feed(page)
        p.close()
    except Exception:                                  # a broken page: what was read so far
        pass
    raw = "".join(p.parts["focus"]) if "".join(p.parts["focus"]).strip() else "".join(p.parts["all"])
    lines = [re.sub(r"[ \t ]+", " ", x).strip() for x in raw.splitlines()]
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
    ld = " ".join(p.ld)
    paywall = p.closed or any(_false(m.group(1)) for m in re.finditer(r'"isAccessibleForFree"\s*:\s*("[^"]{0,40}"|[A-Za-z]+)', ld))     # the page itself says: not free to read
    return {"title": re.sub(r"\s+", " ", p.title).strip()[:300], "lang": p.lang, "paywall": paywall, "text": text[:max_text]}


def xml_records(raw: bytes, max_items: int = 20000) -> list:
    """The elements that hold text in their own children, each as {"@tag": its name, "@attribute": ..., child: text} (names
    without their namespace; a child that comes twice: both texts, " | " between) -- with no document type, no entities of its
    own (a file that declares them is refused: they can blow up to any size)."""
    out, stack = [], []
    p = expat.ParserCreate()

    def forbid(*a):
        raise Refused("xml")
    p.StartDoctypeDeclHandler = forbid
    p.EntityDeclHandler = forbid
    p.UnparsedEntityDeclHandler = forbid
    p.ExternalEntityRefHandler = forbid
    local = lambda t: str(t).rsplit(":", 1)[-1]

    def start(tag, attrs):
        stack.append({"tag": local(tag), "attrs": {"@" + local(k): str(v)[:300] for k, v in list(attrs.items())[:12]}, "text": [], "kids": {}, "leaf": True})
        if len(stack) > 1:
            stack[-2]["leaf"] = False

    def end(tag):
        e = stack.pop()
        if stack and e["leaf"]:
            text, kids = "".join(e["text"]).strip()[:2000], stack[-1]["kids"]
            if text:
                kids[e["tag"]] = (kids[e["tag"]] + " | " + text)[:2000] if e["tag"] in kids else text
        if not e["leaf"] and e["kids"] and len(out) < max_items:
            out.append(dict({"@tag": e["tag"]}, **e["attrs"], **e["kids"]))

    def data(s):
        if stack:
            stack[-1]["text"].append(s)
    p.StartElementHandler, p.EndElementHandler, p.CharacterDataHandler = start, end, data
    try:
        p.Parse(raw, True)
    except expat.ExpatError:
        raise Refused("parse")
    return out


def convert(res: dict, req: dict) -> dict:
    """What was fetched, as plain data of the kind asked for."""
    kind, raw = req.get("as") or "text", res.pop("raw")
    max_text = max(100, min(MAX_TEXT, int(req.get("max_text") or MAX_TEXT)))
    if kind == "json":
        try:
            res["data"] = json.loads(decode(raw, res["charset"]))
        except (ValueError, RecursionError):
            raise Refused("parse")
    elif kind == "xml":
        res["data"] = xml_records(raw)
    elif kind == "csv":
        text = decode(raw, res["charset"])
        head = text.split("\n", 1)[0]
        try:
            rows = list(csv.reader(io.StringIO(text), delimiter=";" if head.count(";") > head.count(",") else ","))
        except csv.Error:                               # a field beyond the csv module's limit (128 KiB) and the like: not readable
            raise Refused("parse")
        res["data"] = [[c[:300] for c in r[:60]] for r in rows[:5000]]
    elif kind == "html":
        if res["type"] not in ("text/html", "application/xhtml+xml", ""):
            raise Refused("type")
        res["data"] = html_text(decode(raw, res["charset"], html=True), req.get("focus"), max_text)
    else:
        res["data"] = decode(raw, res["charset"])[:max_text]
    res.pop("charset", None)
    return res


def handle(req: dict, open_=None) -> dict:
    try:
        if "key" in req or urlparse(str(req.get("url") or "")).hostname == urlparse(CLAUDE).hostname:     # to Claude: only ever its own way
            return ask_claude(req, open_)
        res = fetch(req, open_)
        return convert(res, req) if res.get("ok") else res
    except Refused as e:
        return {"ok": False, "error": str(e)}


def main() -> int:
    try:
        req = json.loads(sys.stdin.read(1 << 20))
        if not isinstance(req, dict):
            raise ValueError
    except ValueError:
        req = {}
    req.pop("_check", None)                             # (only the tests of this module skip the name lookup)
    out = handle(req) if req else {"ok": False, "error": "request"}
    sys.stdout.write(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
