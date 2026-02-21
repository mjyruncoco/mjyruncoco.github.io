#!/usr/bin/env python3
"""Kiwoom local proxy server.

Run on local PC and keep secrets in environment variables:
- KIWOOM_APPKEY
- KIWOOM_SECRETKEY
Optional:
- KIWOOM_USE_MOCK=true|false
- WATCHLIST=005930,000660,035420
- PORT=9000
"""

from __future__ import annotations

import json
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen


KIWOOM_REAL = "https://api.kiwoom.com"
KIWOOM_MOCK = "https://mockapi.kiwoom.com"

SAMPLE_CANDIDATES = [
    {"code": "005930", "name": "삼성전자", "price": 76000, "momentum20d": 0.03, "atr": 1200, "tradeValue20d": 640000000000},
    {"code": "000660", "name": "SK하이닉스", "price": 171000, "momentum20d": 0.04, "atr": 2500, "tradeValue20d": 410000000000},
    {"code": "035420", "name": "NAVER", "price": 210000, "momentum20d": 0.01, "atr": 3400, "tradeValue20d": 90000000000},
]


class KiwoomClient:
    def __init__(self) -> None:
        self.appkey = os.getenv("KIWOOM_APPKEY", "")
        self.secret = os.getenv("KIWOOM_SECRETKEY", "")
        self.use_mock = os.getenv("KIWOOM_USE_MOCK", "false").lower() in {"1", "true", "yes"}
        self.base = KIWOOM_MOCK if self.use_mock else KIWOOM_REAL
        self._token = ""
        self._token_expire_at = 0.0

    def enabled(self) -> bool:
        return bool(self.appkey and self.secret)

    def token(self) -> str:
        now = time.time()
        if self._token and now < self._token_expire_at:
            return self._token

        data = {
            "grant_type": "client_credentials",
            "appkey": self.appkey,
            "secretkey": self.secret,
        }
        payload = self._post_json(f"{self.base}/oauth2/token", {}, data)
        self._token = payload["access_token"]
        self._token_expire_at = now + max(60, int(payload.get("expires_in", 3600)) - 30)
        return self._token

    def request(self, path: str, api_id: str, body: dict[str, Any]) -> dict[str, Any]:
        headers = {
            "Content-Type": "application/json;charset=UTF-8",
            "authorization": f"Bearer {self.token()}",
            "api-id": api_id,
            "cont-yn": "N",
            "next-key": "",
        }
        return self._post_json(f"{self.base}{path}", headers, body)

    def _post_json(self, url: str, headers: dict[str, str], body: dict[str, Any]) -> dict[str, Any]:
        req = Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
        with urlopen(req, timeout=10) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw)

    def orderbook(self, code: str) -> dict[str, Any]:
        return self.request("/api/dostk/mrkcond", "ka10004", {"stk_cd": code})


KIWOOM = KiwoomClient()


def json_response(handler: BaseHTTPRequestHandler, status: int, data: dict[str, Any]) -> None:
    raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(raw)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type")
    handler.end_headers()
    handler.wfile.write(raw)


class Handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        try:
            self._do_get()
        except Exception as exc:  # nosec - local tool server
            json_response(self, 500, {"error": str(exc)})

    def _do_get(self) -> None:
        p = urlparse(self.path)
        qs = parse_qs(p.query)

        if p.path == "/health":
            mode = "kiwoom" if KIWOOM.enabled() else "demo"
            json_response(self, 200, {"status": "ok", "mode": mode})
            return

        if p.path == "/candidates":
            market = qs.get("market", ["000"])[0]
            watchlist = [x.strip() for x in os.getenv("WATCHLIST", "005930,000660,035420").split(",") if x.strip()]
            if KIWOOM.enabled():
                items = [{"code": c, "name": c, "price": 0, "momentum20d": 0.03, "atr": 150, "tradeValue20d": 0, "market": market} for c in watchlist]
                json_response(self, 200, {"items": items, "source": "watchlist"})
            else:
                json_response(self, 200, {"items": SAMPLE_CANDIDATES, "source": "demo"})
            return

        if p.path.startswith("/orderbook/"):
            code = p.path.split("/orderbook/", 1)[1]
            if not code:
                json_response(self, 400, {"error": "missing code"})
                return

            if KIWOOM.enabled():
                payload = KIWOOM.orderbook(code)
                json_response(self, 200, payload)
            else:
                price = 9000
                json_response(
                    self,
                    200,
                    {
                        "buy_fpr_bid": str(price - 10),
                        "sel_fpr_bid": str(price),
                        "buy_hoga_qty_1": "45000",
                        "buy_hoga_qty_2": "39000",
                        "buy_hoga_qty_3": "28000",
                    },
                )
            return

        json_response(self, 404, {"error": "not found"})

    def log_message(self, fmt: str, *args: Any) -> None:
        return


if __name__ == "__main__":
    port = int(os.getenv("PORT", "9000"))
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"[local_proxy_server] http://127.0.0.1:{port} (mode={'kiwoom' if KIWOOM.enabled() else 'demo'})")
    server.serve_forever()
