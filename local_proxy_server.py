#!/usr/bin/env python3
"""Local Kiwoom proxy with runtime mock/live mode and daily PnL report."""

from __future__ import annotations

import json
import os
import threading
import time
from collections import defaultdict
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

KIWOOM_REAL = "https://api.kiwoom.com"
KIWOOM_MOCK = "https://mockapi.kiwoom.com"
STATE_PATH = os.getenv("STATE_PATH", "trade_state.json")


class KiwoomGateway:
    def __init__(self) -> None:
        self.appkey = os.getenv("KIWOOM_APPKEY", "")
        self.secret = os.getenv("KIWOOM_SECRETKEY", "")
        self.account_no = os.getenv("KIWOOM_ACCOUNT_NO", "")
        self.product_no = os.getenv("KIWOOM_PRODUCT_NO", "01")
        self.live_order = os.getenv("AUTO_LIVE_ORDER", "false").lower() in {"1", "true", "yes"}
        self.initial_mode = os.getenv("KIWOOM_INITIAL_MODE", "mock").lower()
        if self.initial_mode not in {"mock", "live"}:
            self.initial_mode = "mock"
        self._token: dict[str, str] = {"mock": "", "live": ""}
        self._expires: dict[str, float] = {"mock": 0.0, "live": 0.0}

    def enabled(self) -> bool:
        return bool(self.appkey and self.secret)

    def can_live_order(self) -> bool:
        return self.enabled() and self.live_order and bool(self.account_no)

    def _base(self, mode: str) -> str:
        return KIWOOM_MOCK if mode == "mock" else KIWOOM_REAL

    def token(self, mode: str) -> str:
        now = time.time()
        if self._token[mode] and now < self._expires[mode]:
            return self._token[mode]
        payload = self._post_json(
            f"{self._base(mode)}/oauth2/token",
            {"Content-Type": "application/json;charset=UTF-8"},
            {"grant_type": "client_credentials", "appkey": self.appkey, "secretkey": self.secret},
        )
        self._token[mode] = payload["access_token"]
        self._expires[mode] = now + max(60, int(payload.get("expires_in", 3600)) - 30)
        return self._token[mode]

    def _post_json(self, url: str, headers: dict[str, str], body: dict[str, Any]) -> dict[str, Any]:
        req = Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
        with urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def tr_post(self, mode: str, path: str, api_id: str, body: dict[str, Any]) -> dict[str, Any]:
        headers = {
            "Content-Type": "application/json;charset=UTF-8",
            "authorization": f"Bearer {self.token(mode)}",
            "api-id": api_id,
            "cont-yn": "N",
            "next-key": "",
        }
        return self._post_json(f"{self._base(mode)}{path}", headers, body)

    @staticmethod
    def _to_price(value: Any) -> int:
        text = str(value or "").replace(",", "").strip()
        if not text:
            return 0
        text = text.lstrip("+-")
        if not text.isdigit():
            return 0
        return int(text)

    def _extract_from_quote(self, payload: dict[str, Any]) -> int:
        for key in ("cur_prc", "cur_price", "stck_prpr", "now_prc", "price"):
            p = self._to_price(payload.get(key))
            if p > 0:
                return p
        return 0

    def _extract_from_orderbook(self, payload: dict[str, Any]) -> tuple[int, str]:
        bid = self._to_price(payload.get("buy_fpr_bid"))
        ask = self._to_price(payload.get("sel_fpr_bid"))
        if bid > 0 and ask > 0:
            return (bid + ask) // 2, "mid"
        if bid > 0:
            return bid, "bid"
        if ask > 0:
            return ask, "ask"
        return 0, "none"

    def quote(self, code: str) -> tuple[int, str]:
        errors: list[str] = []

        try:
            quote = self.tr_post("live", "/api/dostk/mrkcond", "ka10001", {"stk_cd": code})
            data = quote.get("output") if isinstance(quote, dict) else None
            if isinstance(data, dict):
                current = self._extract_from_quote(data)
                if current > 0:
                    return current, "kiwoom-live-ka10001-output"
            if isinstance(quote, dict):
                current = self._extract_from_quote(quote)
                if current > 0:
                    return current, "kiwoom-live-ka10001-top"
        except Exception as exc:  # nosec
            errors.append(f"live:ka10001:{exc}")

        try:
            ob = self.tr_post("live", "/api/dostk/mrkcond", "ka10004", {"stk_cd": code})
            ob_data = ob.get("output") if isinstance(ob, dict) else None
            if isinstance(ob_data, dict):
                current, kind = self._extract_from_orderbook(ob_data)
                if current > 0:
                    return current, f"kiwoom-live-ka10004-{kind}-output"
            if isinstance(ob, dict):
                current, kind = self._extract_from_orderbook(ob)
                if current > 0:
                    return current, f"kiwoom-live-ka10004-{kind}-top"
        except Exception as exc:  # nosec
            errors.append(f"live:ka10004:{exc}")

        return 0, "quote-unavailable | " + " ; ".join(errors[-4:])

    def submit_order(self, mode: str, side: str, code: str, qty: int, price: int) -> dict[str, Any]:
        if not self.can_live_order():
            return {
                "status": "paper",
                "message": "paper mode (AUTO_LIVE_ORDER=false or missing account)",
                "requested": {"mode": mode, "side": side, "code": code, "qty": qty, "price": price},
            }
        api_id = "kt10000" if side == "BUY" else "kt10001"
        body = {
            "dmst_stex_tp": "KRX",
            "stk_cd": code,
            "ord_qty": str(qty),
            "ord_uv": str(price),
            "trde_tp": "00",
            "cond_uv": "",
            "ord_dvsn": "00",
            "acnt_no": self.account_no,
            "prdt_no": self.product_no,
        }
        result = self.tr_post(mode, "/api/dostk/ordr", api_id, body)
        return {"status": "live", "message": "order sent", "result": result}


KIWOOM = KiwoomGateway()
LOCK = threading.Lock()


def _default_state() -> dict[str, Any]:
    return {"trade_mode": KIWOOM.initial_mode, "positions": {}, "fills": []}


def load_state() -> dict[str, Any]:
    if not os.path.exists(STATE_PATH):
        return _default_state()
    with open(STATE_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    base = _default_state()
    base.update(data)
    return base


def save_state(state: dict[str, Any]) -> None:
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


STATE = load_state()
LAST_PRICE: dict[str, int] = {}


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
    seed = sum(ord(c) for c in code)
    return max(1000, 9000 + (seed % 300) - 150)


def record_fill(mode: str, side: str, code: str, qty: int, price: int) -> float:
    with LOCK:
        positions: dict[str, Any] = STATE["positions"]
        pos = positions.get(code, {"qty": 0, "avg_price": 0})
        realized = 0.0
        if side == "BUY":
            total_cost = pos["avg_price"] * pos["qty"] + price * qty
            new_qty = pos["qty"] + qty
            pos["qty"] = new_qty
            pos["avg_price"] = total_cost / new_qty if new_qty else 0
        else:
            sell_qty = min(qty, pos["qty"])
            if sell_qty > 0:
                realized = (price - pos["avg_price"]) * sell_qty
                pos["qty"] -= sell_qty
                if pos["qty"] <= 0:
                    pos = {"qty": 0, "avg_price": 0}
        positions[code] = pos
        STATE["fills"].append(
            {
                "ts": datetime.now().isoformat(timespec="seconds"),
                "date": datetime.now().strftime("%Y-%m-%d"),
                "mode": mode,
                "side": side,
                "code": code,
                "qty": qty,
                "price": price,
                "realized_pnl": round(realized, 2),
            }
        )
        STATE["fills"] = STATE["fills"][-5000:]
        save_state(STATE)
    return realized


def daily_report(date_str: str) -> dict[str, Any]:
    rows = [x for x in STATE.get("fills", []) if x.get("date") == date_str]
    by_code: dict[str, dict[str, Any]] = defaultdict(lambda: {"buy_amount": 0, "sell_amount": 0, "realized_pnl": 0})
    for r in rows:
        amt = r["price"] * r["qty"]
        c = by_code[r["code"]]
        if r["side"] == "BUY":
            c["buy_amount"] += amt
        else:
            c["sell_amount"] += amt
        c["realized_pnl"] += r.get("realized_pnl", 0)
    detail = [{"code": k, **v} for k, v in by_code.items()]
    total = round(sum(x["realized_pnl"] for x in detail), 2)
    return {"date": date_str, "total_realized_pnl": total, "count": len(rows), "by_code": detail, "fills": rows}


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
            qs = parse_qs(p.query)
            if p.path == "/health":
                json_response(self, 200, {"status": "ok", "api_enabled": KIWOOM.enabled(), "trade_mode": STATE["trade_mode"], "live_order": KIWOOM.can_live_order()})
                return
            if p.path == "/mode":
                json_response(self, 200, {"trade_mode": STATE["trade_mode"]})
                return
            if p.path.startswith("/quote/"):
                code = p.path.split("/quote/", 1)[1]
                if not code:
                    json_response(self, 400, {"error": "missing code"})
                    return
                if KIWOOM.enabled():
                    price, source = KIWOOM.quote(code)
                    if price > 0:
                        with LOCK:
                            LAST_PRICE[code] = price
                        json_response(self, 200, {"code": code, "price": price, "source": source})
                        return

                    with LOCK:
                        last = LAST_PRICE.get(code)
                    if last is not None:
                        json_response(self, 200, {"code": code, "price": last, "source": "last-good", "warning": source})
                        return

                    json_response(self, 502, {"error": "quote unavailable", "code": code, "source": source})
                else:
                    json_response(self, 200, {"code": code, "price": demo_quote(code), "source": "demo"})
                return
            if p.path == "/reports/daily":
                d = qs.get("date", [datetime.now().strftime("%Y-%m-%d")])[0]
                json_response(self, 200, daily_report(d))
                return
            json_response(self, 404, {"error": "not found"})
        except Exception as exc:  # nosec
            json_response(self, 500, {"error": str(exc)})

    def do_POST(self) -> None:  # noqa: N802
        try:
            p = urlparse(self.path)
            content_len = int(self.headers.get("Content-Length", "0") or "0")
            payload = json.loads(self.rfile.read(content_len).decode("utf-8") if content_len else "{}")
            if p.path == "/mode":
                mode = str(payload.get("trade_mode", "")).lower()
                if mode not in {"mock", "live"}:
                    json_response(self, 400, {"error": "trade_mode must be mock|live"})
                    return
                with LOCK:
                    STATE["trade_mode"] = mode
                    save_state(STATE)
                json_response(self, 200, {"status": "ok", "trade_mode": mode})
                return
            if p.path == "/orders/execute":
                code = str(payload.get("code", "")).strip()
                side = str(payload.get("side", "")).upper()
                qty = int(payload.get("qty", 0))
                price = int(payload.get("price", 0))
                if not code or side not in {"BUY", "SELL"} or qty <= 0 or price <= 0:
                    json_response(self, 400, {"error": "invalid order payload"})
                    return
                mode = STATE["trade_mode"]
                broker = KIWOOM.submit_order(mode, side, code, qty, price)
                realized = record_fill(mode, side, code, qty, price)
                broker["mode"] = mode
                broker["realized_pnl"] = realized
                json_response(self, 200, broker)
                return
            json_response(self, 404, {"error": "not found"})
        except Exception as exc:  # nosec
            json_response(self, 500, {"error": str(exc)})

    def log_message(self, fmt: str, *args: Any) -> None:
        return


if __name__ == "__main__":
    port = int(os.getenv("PORT", "9000"))
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"[local_proxy_server] http://127.0.0.1:{port} trade_mode={STATE['trade_mode']} live_order={KIWOOM.can_live_order()}")
    server.serve_forever()
