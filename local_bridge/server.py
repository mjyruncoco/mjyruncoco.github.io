#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse


class LocalBridgeHandler(BaseHTTPRequestHandler):
    def _set_headers(self, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Api-Key, X-Api-Secret")
        self.end_headers()

    def do_OPTIONS(self) -> None:  # noqa: N802
        self._set_headers(204)

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path == "/health":
            self._set_headers(200)
            self.wfile.write(json.dumps({"status": "ok"}).encode("utf-8"))
            return
        self._set_headers(404)
        self.wfile.write(json.dumps({"error": "not_found"}).encode("utf-8"))


def run() -> None:
    host = os.getenv("LOCAL_BRIDGE_HOST", "127.0.0.1")
    port = int(os.getenv("LOCAL_BRIDGE_PORT", "8787"))
    server = ThreadingHTTPServer((host, port), LocalBridgeHandler)
    print(f"Local bridge running on http://{host}:{port}")
    print("Health check: GET /health")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")


if __name__ == "__main__":
    run()
