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
POST_ONLY = {"api.tavily.com": ("/search",)}         # the one service that takes its question only as POST (no cookies, no forms)
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
        mapped = ip.ipv4_mapped if ip.version == 6 else None
        if not ip.is_global or ip.is_multicast or (mapped is not None and (not mapped.is_global or mapped.is_multicast)):
            raise Refused("private")
        ips.append(str(ip))
    if not ips:
        raise Refused("dns")
    return ips[0]


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


def fetch(req: dict, open_=None) -> dict:
    """The request carried out: {"ok", "status", "url", "type", "charset", "raw"} (raw: bytes) -- or Refused."""
    url, hosts = str(req.get("url") or ""), list(req.get("hosts") or [])
    host = host_ok(url, hosts)
    method = "POST" if req.get("method") == "POST" else "GET"
    if method == "POST" and urlparse(url).path not in POST_ONLY.get(host, ()):
        raise Refused("method")
    max_bytes = max(1, min(MAX_BYTES, int(req.get("max_bytes") or MAX_BYTES)))
    timeout = max(1.0, min(float(req.get("timeout") or 20), MAX_SECONDS))
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
    data = str(req.get("body") or "").encode("utf-8") if method == "POST" else None
    r = urllib.request.Request(url, data=data, headers=headers, method=method)
    t0 = time.time()
    try:
        resp = (open_ or _build(ssl.create_default_context(), hosts, check, pins).open)(r, timeout=timeout)
    except urllib.error.HTTPError as e:
        return {"ok": False, "error": "http", "status": e.code}
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
