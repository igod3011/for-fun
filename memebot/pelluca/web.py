"""pelluca.com: static pages plus a read-only JSON API, standard library only.

  python -m memebot.pelluca.web                 # serves http://127.0.0.1:8080 (Caddy in front adds HTTPS)
  set PELLUCA_WEB_PORT=8080                     (optional)

Routes
  /                  web/index.html
  /studio            web/studio.html
  /terms             legal/TERMS.md rendered to HTML on each request (one source of truth for the bot and site)
  /api/check?ca=...  the same facts and flags as the bot's /check, as JSON
  /static/<file>     files in web/ (no subfolders, no dotfiles)

The API uses check.cached_gather (60 s cache shared with nothing else in this process), the same flags as the
bot (check.assess) and the Free plan limits per client IP (limits.py). Behind Caddy the client IP comes from
X-Forwarded-For, trusted only when the request arrives from 127.0.0.1.
"""
import json
import os
import re
import threading
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import chain, check
from .limits import RateLimit

HERE = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(HERE, "web")
TERMS_MD = os.path.join(HERE, "legal", "TERMS.md")
PAGES = {"/": "index.html", "/studio": "studio.html"}
TYPES = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8", ".js": "text/javascript; charset=utf-8",
         ".svg": "image/svg+xml", ".png": "image/png", ".ico": "image/x-icon", ".txt": "text/plain; charset=utf-8"}
BUSY_SLOTS = 4            # API checks running at once; more get 503 instead of piling up on the RPC
CSP = ("default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
       "font-src https://fonts.gstatic.com; script-src 'self'; connect-src 'self'; frame-ancestors 'none'; "
       "base-uri 'none'; form-action 'self'")


def report_json(f):
    """Pure (unit-tested): what the website shows for one check. Never includes raw RPC payloads."""
    flags, verdict = check.assess(f)
    dx = f.get("dex") or {}
    out = {"mint": f["mint"], "verdict": verdict, "name": dx.get("name"),
           "price_usd": dx.get("price_usd"), "mcap": check.market_cap(f)[0], "mcap_source": check.market_cap(f)[1], "change_h1": dx.get("change_h1"),
           "change_h24": dx.get("change_h24"), "pool": f.get("pool"), "pool_sol": f.get("pool_sol"),
           "top10": f.get("top10"), "dev_pct": f.get("dev_pct"),
           "flags": [{"level": lvl, "text": txt} for lvl, txt in flags],
           "base_rate": check.BASE_RATE, "study": check.STUDY, "checked_at": f.get("checked_at")}
    ex = check.exit_math(f)
    if ex:
        out["exit"] = {k: ex[k] for k in ("stake", "round_trip_loss", "top10_drain") if k in ex}
    return out


def _inline(s):
    s = escape(s, quote=False)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<![\w*])_(.+?)_(?!\w)", r"<em>\1</em>", s)
    s = re.sub(r"(?<![\w*])\*(?!\s)(.+?)\*(?!\w)", r"<em>\1</em>", s)
    return s


def md_to_html(md):
    """Pure (unit-tested): the small Markdown subset TERMS.md uses: #/## headings, paragraphs, '-' lists with
    indented continuation lines, **bold**, *italic*/_italic_, `code`."""
    out, para, items = [], [], []

    def flush():
        if para:
            out.append("<p>" + _inline(" ".join(para)) + "</p>")
            para.clear()
        if items:
            out.append("<ul>" + "".join("<li>" + _inline(i) + "</li>" for i in items) + "</ul>")
            items.clear()
    for raw in md.splitlines():
        line = raw.rstrip()
        if not line.strip():
            flush()
        elif line.startswith("#"):
            flush()
            level = min(len(line) - len(line.lstrip("#")), 3)
            text = line.lstrip("#").strip()
            slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
            out.append(f'<h{level} id="{slug}">{_inline(text)}</h{level}>')
        elif line.startswith("- "):
            if para:
                flush()
            items.append(line[2:].strip())
        elif items and raw.startswith("  "):
            items[-1] += " " + line.strip()
        else:
            if items:
                flush()
            para.append(line.strip())
    flush()
    return "\n".join(out)


def terms_page():
    with open(TERMS_MD, encoding="utf-8") as fh:
        body = md_to_html(fh.read())
    with open(os.path.join(WEB, "terms.html"), encoding="utf-8") as fh:
        return fh.read().replace("<!--TERMS-->", body)


def static_path(name):
    """Pure: the file under web/ for /static/<name>, or None. Only plain file names with a known type."""
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,80}", name) or ".." in name:
        return None
    if os.path.splitext(name)[1] not in TYPES:
        return None
    p = os.path.join(WEB, name)
    return p if os.path.isfile(p) else None


class App:
    """Request logic without sockets, so it can be tested directly."""

    def __init__(self, gather=check.cached_gather, limit=None):
        self.gather = gather
        self.limit = limit or RateLimit()
        self.slots = threading.BoundedSemaphore(BUSY_SLOTS)

    def api_check(self, ca, client):
        """Returns (status, dict)."""
        ca = (ca or "").strip()
        if not chain.is_address(ca):
            return 400, {"error": "That is not a Solana token address."}
        hit = self.limit.take(client)
        if hit:
            return 429, {"error": f"Free limit reached ({'20 checks per hour' if hit == 'hour' else '100 checks per day'})."
                                  " Try again later or use the Telegram bot."}
        if not self.slots.acquire(blocking=False):
            return 503, {"error": "Busy right now. Try again in a few seconds."}
        try:
            return 200, report_json(self.gather(ca))
        except Exception:
            return 502, {"error": "The chain could not be read right now. Try again in a minute."}
        finally:
            self.slots.release()


def client_ip(peer, headers):
    """Pure: the visitor's IP. X-Forwarded-For is trusted only from the local reverse proxy."""
    if peer in ("127.0.0.1", "::1"):
        fwd = (headers.get("X-Forwarded-For") or "").split(",")[-1].strip()
        if fwd:
            return fwd
    return peer


def make_handler(app):
    class Handler(BaseHTTPRequestHandler):
        server_version = "pelluca"
        sys_version = ""

        def _send(self, status, body, ctype, cache="no-store"):
            data = body.encode("utf-8") if isinstance(body, str) else body
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", cache)
            self.send_header("Content-Security-Policy", CSP)
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(data)

        def do_HEAD(self):
            self.do_GET()

        def do_GET(self):
            u = urlparse(self.path)
            path = u.path.rstrip("/") or "/"
            try:
                if path == "/api/check":
                    ca = parse_qs(u.query).get("ca", [""])[0]
                    status, obj = app.api_check(ca, client_ip(self.client_address[0], self.headers))
                    return self._send(status, json.dumps(obj), "application/json")
                if path == "/terms":
                    return self._send(200, terms_page(), TYPES[".html"], "public, max-age=300")
                if path in PAGES:
                    with open(os.path.join(WEB, PAGES[path]), "rb") as fh:
                        return self._send(200, fh.read(), TYPES[".html"], "public, max-age=300")
                if path.startswith("/static/"):
                    p = static_path(path[len("/static/"):])
                    if p:
                        with open(p, "rb") as fh:
                            return self._send(200, fh.read(), TYPES[os.path.splitext(p)[1]], "public, max-age=3600")
                if path == "/favicon.ico":
                    with open(os.path.join(WEB, "favicon.svg"), "rb") as fh:
                        return self._send(200, fh.read(), TYPES[".svg"], "public, max-age=86400")
                return self._send(404, "Not found", TYPES[".txt"])
            except Exception:
                return self._send(500, "Server error", TYPES[".txt"])

        def log_message(self, fmt, *args):            # no visitor IPs in the logs (ToS section 8: minimal data)
            pass
    return Handler


def main():
    port = int(os.environ.get("PELLUCA_WEB_PORT", "8080"))
    srv = ThreadingHTTPServer(("127.0.0.1", port), make_handler(App()))
    srv.daemon_threads = True
    print(f"Pelluca web on http://127.0.0.1:{port}", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
