#!/usr/bin/env python3
"""Capture proxy: log request/response body ke file, teruskan ke upstream.
Dipakai buat membedah kenapa request tertentu kena filter provider (HTTP 451)."""
import json
import sys
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

UPSTREAM = "http://127.0.0.1:5899"
OUT = Path(__file__).with_name("capture.jsonl")


class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format, *args):
        pass

    def _go(self, method):
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b""
        rec = {"path": self.path, "len": len(raw)}
        try:
            rec["req"] = json.loads(raw)
        except Exception:
            rec["req_raw"] = raw[:4000].decode("utf-8", "replace")
        headers = {k: v for k, v in self.headers.items()
                   if k.lower() in ("authorization", "content-type", "accept")}
        req = urllib.request.Request(UPSTREAM.rstrip("/") + self.path, data=raw if raw else None,
                                     headers=headers, method=method)
        status, body = 0, b""
        try:
            r = urllib.request.urlopen(req, timeout=900)
            status = r.status
            body = r.read()
        except urllib.error.HTTPError as e:
            status = e.code
            body = e.read()
        except Exception as e:
            status = 599
            body = json.dumps({"proxy_error": str(e)}).encode()
        rec["status"] = status
        rec["resp_head"] = body[:600].decode("utf-8", "replace")
        with open(OUT, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        self._go("POST")

    def do_GET(self):
        self._go("GET")


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5901
    print("capture proxy :%d -> %s | log: %s" % (port, UPSTREAM, OUT))
    ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()
