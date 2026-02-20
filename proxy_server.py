#!/usr/bin/env python3
"""
Local proxy for Kiwoom REST (or any HTTP JSON endpoint).
Run on your PC and keep API keys locally.

Usage:
  1) Copy proxy_config.sample.json -> proxy_config.local.json and fill values.
  2) python3 proxy_server.py --host 127.0.0.1 --port 8787 --config proxy_config.local.json

Endpoints:
  - GET /health
  - GET /api/stocks      -> forwards to config.target_url with configured headers
"""

from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


def load_config(path: Path) -> Dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not data.get("target_url"):
        raise ValueError("config.target_url is required")
    data.setdefault("headers", {})
    return data


class ProxyHandler(BaseHTTPRequestHandler):
    config: Dict[str, Any] = {}

    def _set_json(self, code: int = 200) -> None:
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_OPTIONS(self) -> None:  # noqa: N802
        self._set_json(204)

    def do_GET(self) -> None:  # noqa: N802
        if self.path.startswith("/health"):
            self._set_json(200)
            self.wfile.write(json.dumps({"ok": True, "service": "local-proxy"}).encode("utf-8"))
            return

        if not self.path.startswith("/api/stocks"):
            self._set_json(404)
            self.wfile.write(json.dumps({"error": "not found"}).encode("utf-8"))
            return

        target_url = self.config["target_url"]
        headers = {str(k): str(v) for k, v in self.config.get("headers", {}).items() if str(v).strip()}
        req = Request(target_url, headers=headers, method="GET")

        try:
            with urlopen(req, timeout=20) as resp:
                body = resp.read()
                status = getattr(resp, "status", 200)
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(body)
        except HTTPError as e:
            self._set_json(e.code)
            self.wfile.write(json.dumps({"error": "upstream http error", "status": e.code}).encode("utf-8"))
        except URLError as e:
            self._set_json(502)
            self.wfile.write(json.dumps({"error": "upstream unavailable", "reason": str(e)}).encode("utf-8"))
        except Exception as e:  # noqa: BLE001
            self._set_json(500)
            self.wfile.write(json.dumps({"error": "proxy failure", "reason": str(e)}).encode("utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--config", default="proxy_config.local.json")
    args = parser.parse_args()

    cfg = load_config(Path(args.config))
    ProxyHandler.config = cfg

    server = ThreadingHTTPServer((args.host, args.port), ProxyHandler)
    print(f"Proxy listening on http://{args.host}:{args.port}")
    print(f"Forwarding /api/stocks -> {cfg['target_url']}")
    server.serve_forever()


if __name__ == "__main__":
    main()
