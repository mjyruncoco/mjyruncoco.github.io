#!/usr/bin/env python3
"""Local Kiwoom proxy server for auto-execution workflow.

Secrets stay ONLY in local environment variables:
- KIWOOM_APPKEY
- KIWOOM_SECRETKEY
Optional for live order forwarding:
- KIWOOM_ACCOUNT_NO
- KIWOOM_PRODUCT_NO (default: 01)
- KIWOOM_USE_MOCK=true|false
- AUTO_LIVE_ORDER=true|false (default false; false = paper)
- PORT=9000
"""

from __future__ import annotations

import json
import os
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse
from urllib.request import Request, urlopen

KIWOOM_REAL = "https://api.kiwoom.com"
KIWOOM_MOCK = "https://mockapi.kiwoom.com"


class KiwoomClient:
    def __init__(self) -> None:
        self.appkey = os.getenv("KIWOOM_APPKEY", "")
        self.secret = os.getenv("KIWOOM_SECRETKEY", "")
        self.account_no = os.getenv("KIWOOM_ACCOUNT_NO", "")
        self.product_no = os.getenv("KIWOOM_PRODUCT_NO", "01")
        self.use_mock = os.getenv("KIWOOM_USE_MOCK", "false").lower() in {"1", "true", "yes"}
        self.live_order = os.getenv("AUTO_LIVE_ORDER", "false").lower() in {"1", "true", "yes"}
        self.base = KIWOOM_MOCK if self.use_mock else KIWOOM_REAL
        self._token = ""
        self._token_expire_at = 0.0

    def enabled(self) -> bool:
        return bool(self.appkey and self.secret)

    def can_live_order(self) -> bool:
        return self.enabled() and self.live_order and bool(self.account_no)

    def token(self) -> str:
        now = time.time()
        if self._token and now < self._token_expire_at:
            return self._token
        payload = self._post_json(
            f"{self.base}/oauth2/token",
            {},
            {"grant_type": "client_credentials", "appkey": self.appkey, "secretkey": self.secret},
        )
        self._token = payload["access_token"]
        self._token_expire_at = now + max(60, int(payload.get("expires_in", 3600)) - 30)
        return self._token

    def tr_post(self, path: str, api_id: str, body: dict[str, Any]) -> dict[str, Any]:
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
            return json.loads(resp.read().decode("utf-8"))

    def orderbook(self, code: str) -> dict[str, Any]:
        return self.tr_post("/api/dostk/mrkcond", "ka10004", {"stk_cd": code})

    def submit_order(self, side: str, code: str, qty: int, price: int) -> dict[str, Any]:
        if not self.can_live_order():
            return {
                "status": "paper",
                "message": "paper mode (AUTO_LIVE_ORDER=false or missing account)",
                "requested": {"side": side, "code": code, "qty": qty, "price": price},
            }

        api_id = "kt10000" if side.upper() == "BUY" else "kt10001"
        # 지정가 주문 기준. 필드명은 키움 주문 TR 문서 스펙에 맞춰 운영 환경에서 검증 필요.
        body = {
            "dmst_stex_tp": "KRX",
            "stk_cd": code,
            "ord_qty": str(qty),
            "ord_uv": str(price),
            "trde_tp": "00",  # 지정가
            "cond_uv": "",
            "ord_dvsn": "00",
            "acnt_no": self.account_no,
            "prdt_no": self.product_no,
        }
        result = self.tr_post("/api/dostk/ordr", api_id, body)
        return {"status": "live", "message": "order sent", "result": result}


KIWOOM = KiwoomClient()


def json_response(handler: BaseHTTPRequestHandler, status: int, data: dict[str, Any]) -> None:
    raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(raw)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type")
    handler.end_headers()
    handler.wfile.write(raw)


def demo_quote(code: str) -> int:
    seed = sum(ord(c) for c in code) + int(time.time() // 2)
    base = 9000 + (seed % 300) - 150
    return max(1000, base)


class Handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        try:
            p = urlparse(self.path)
            if p.path == "/health":
                json_response(
                    self,
                    200,
                    {
                        "status": "ok",
                        "mode": "kiwoom" if KIWOOM.enabled() else "demo",
                        "live_order": KIWOOM.can_live_order(),
                    },
                )
                return

            if p.path.startswith("/quote/"):
                code = p.path.split("/quote/", 1)[1]
                if not code:
                    json_response(self, 400, {"error": "missing code"})
                    return

                if KIWOOM.enabled():
                    ob = KIWOOM.orderbook(code)
                    bid = int(str(ob.get("buy_fpr_bid", "0")).replace(",", "") or "0")
                    ask = int(str(ob.get("sel_fpr_bid", "0")).replace(",", "") or "0")
                    price = bid if bid > 0 else ask
                    json_response(self, 200, {"code": code, "price": price, "source": "kiwoom"})
                else:
                    json_response(self, 200, {"code": code, "price": demo_quote(code), "source": "demo"})
                return

            json_response(self, 404, {"error": "not found"})
        except Exception as exc:  # nosec
            json_response(self, 500, {"error": str(exc)})

    def do_POST(self) -> None:  # noqa: N802
        try:
            p = urlparse(self.path)
            content_len = int(self.headers.get("Content-Length", "0") or "0")
            raw = self.rfile.read(content_len).decode("utf-8") if content_len else "{}"
            payload = json.loads(raw)

            if p.path == "/orders/execute":
                code = str(payload.get("code", "")).strip()
                side = str(payload.get("side", "")).upper()
                qty = int(payload.get("qty", 0))
                price = int(payload.get("price", 0))
                if not code or side not in {"BUY", "SELL"} or qty <= 0:
                    json_response(self, 400, {"error": "invalid order payload"})
                    return

                result = KIWOOM.submit_order(side, code, qty, price)
                json_response(self, 200, result)
                return

            json_response(self, 404, {"error": "not found"})
        except Exception as exc:  # nosec
            json_response(self, 500, {"error": str(exc)})

    def log_message(self, fmt: str, *args: Any) -> None:
        return


if __name__ == "__main__":
    port = int(os.getenv("PORT", "9000"))
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(
        f"[local_proxy_server] http://127.0.0.1:{port} mode={'kiwoom' if KIWOOM.enabled() else 'demo'} live_order={KIWOOM.can_live_order()}"
    )
    server.serve_forever()
