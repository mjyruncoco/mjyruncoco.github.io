#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hashlib
import hmac
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen
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

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path != "/order":
            self._set_headers(404)
            self.wfile.write(json.dumps({"error": "not_found"}).encode("utf-8"))
            return

        content_length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(content_length).decode("utf-8") if content_length else "{}"
        try:
            payload = json.loads(raw_body)
        except json.JSONDecodeError:
            self._set_headers(400)
            self.wfile.write(json.dumps({"error": "invalid_json"}).encode("utf-8"))
            return

        symbol = payload.get("symbol", "BTCUSDT")
        side = payload.get("side", "BUY")
        order_type = payload.get("type", "MARKET")
        quantity = payload.get("quantity")

        api_key = os.getenv("BINANCE_API_KEY")
        api_secret = os.getenv("BINANCE_API_SECRET")
        if not api_key or not api_secret:
            self._set_headers(400)
            self.wfile.write(
                json.dumps({"error": "missing_api_keys"}).encode("utf-8")
            )
            return

        if not quantity:
            self._set_headers(400)
            self.wfile.write(json.dumps({"error": "missing_quantity"}).encode("utf-8"))
            return

        base_url = os.getenv("BINANCE_BASE_URL", "https://api.binance.com")
        endpoint = "/api/v3/order"
        params = {
            "symbol": symbol,
            "side": side,
            "type": order_type,
            "quantity": quantity,
            "timestamp": int(time.time() * 1000),
            "recvWindow": 5000,
        }
        query_string = urlencode(params)
        signature = hmac.new(
            api_secret.encode("utf-8"),
            query_string.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        signed_query = f"{query_string}&signature={signature}"
        request = Request(
            f"{base_url}{endpoint}?{signed_query}",
            method="POST",
            headers={"X-MBX-APIKEY": api_key},
        )
        try:
            with urlopen(request, timeout=10) as response:
                data = response.read().decode("utf-8")
            self._set_headers(200)
            self.wfile.write(data.encode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            self._set_headers(500)
            self.wfile.write(json.dumps({"error": str(exc)}).encode("utf-8"))


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
