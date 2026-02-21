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



def load_dotenv(path: str = ".env") -> None:
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            if not k or k in os.environ:
                continue
            v = v.strip().strip('"').strip("'")
            os.environ[k] = v


load_dotenv()
KIWOOM_REAL = "https://api.kiwoom.com"
KIWOOM_MOCK = "https://mockapi.kiwoom.com"
STATE_PATH = os.getenv("STATE_PATH", "trade_state.json")
COMMON_SYMBOLS = {"005930": "삼성전자", "000660": "SK하이닉스", "035420": "NAVER", "005380": "현대차", "051910": "LG화학"}


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


class KiwoomGateway:
    def __init__(self) -> None:
        # 공통 키 (하위 모드 키가 없으면 이 값을 fallback으로 사용)
        self.appkey = os.getenv("KIWOOM_APPKEY", "")
        self.secret = os.getenv("KIWOOM_SECRETKEY", "")
        # 모의/실전 개별 키 지원
        self.mock_appkey = os.getenv("KIWOOM_MOCK_APPKEY", "")
        self.mock_secret = os.getenv("KIWOOM_MOCK_SECRETKEY", "")
        self.live_appkey = os.getenv("KIWOOM_LIVE_APPKEY", "")
        self.live_secret = os.getenv("KIWOOM_LIVE_SECRETKEY", "")
        self.account_no = os.getenv("KIWOOM_ACCOUNT_NO", "")
        self.product_no = os.getenv("KIWOOM_PRODUCT_NO", "01")
        self.live_order = _env_bool("AUTO_LIVE_ORDER", False)
        use_mock = _env_bool("KIWOOM_USE_MOCK", True)
        default_mode = "mock" if use_mock else "live"
        self.initial_mode = os.getenv("KIWOOM_INITIAL_MODE", default_mode).lower()
        if self.initial_mode not in {"mock", "live"}:
            self.initial_mode = "mock"
        self._token: dict[str, str] = {"mock": "", "live": ""}
        self._expires: dict[str, float] = {"mock": 0.0, "live": 0.0}

        # 실체결/잔고 조회 API 설정 (브로커 TR 연동용)
        self.pos_path = os.getenv("KIWOOM_POS_PATH", "/api/dostk/inqr")
        self.pos_api_id = os.getenv("KIWOOM_POS_API_ID", "")
        self.fill_path = os.getenv("KIWOOM_FILL_PATH", "/api/dostk/inqr")
        self.fill_api_id = os.getenv("KIWOOM_FILL_API_ID", "")

    def _credentials(self, mode: str) -> tuple[str, str]:
        if mode == "mock":
            appkey = self.mock_appkey or self.appkey
            secret = self.mock_secret or self.secret
        else:
            appkey = self.live_appkey or self.appkey
            secret = self.live_secret or self.secret
        return appkey, secret

    def enabled(self, mode: str | None = None) -> bool:
        if mode is None:
            return self.enabled("mock") or self.enabled("live")
        appkey, secret = self._credentials(mode)
        return bool(appkey and secret)

    def can_live_order(self) -> bool:
        return self.enabled("live") and self.live_order and bool(self.account_no)

    def _base(self, mode: str) -> str:
        return KIWOOM_MOCK if mode == "mock" else KIWOOM_REAL

    def token(self, mode: str) -> str:
        now = time.time()
        if self._token[mode] and now < self._expires[mode]:
            return self._token[mode]
        appkey, secret = self._credentials(mode)
        if not (appkey and secret):
            raise ValueError(f"missing credentials for mode={mode}")
        payload = self._post_json(
            f"{self._base(mode)}/oauth2/token",
            {"Content-Type": "application/json;charset=UTF-8"},
            {"grant_type": "client_credentials", "appkey": appkey, "secretkey": secret},
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

    def _extract_name(self, payload: dict[str, Any]) -> str:
        for key in ("stk_nm", "hts_kor_isnm", "isu_nm", "prdt_abrv_name", "stk_kor_nm", "kor_isnm", "item_name"):
            name = str(payload.get(key, "")).strip()
            if name and any(ch.isalpha() for ch in name):
                return name
        return ""

    def _find_name_recursive(self, node: Any) -> str:
        if isinstance(node, dict):
            direct = self._extract_name(node)
            if direct:
                return direct
            for v in node.values():
                n = self._find_name_recursive(v)
                if n:
                    return n
        if isinstance(node, list):
            for item in node:
                n = self._find_name_recursive(item)
                if n:
                    return n
        return ""

    def symbol_name(self, code: str, mode: str = "live") -> str:
        if code in COMMON_SYMBOLS:
            return COMMON_SYMBOLS[code]
        if not self.enabled(mode):
            return ""
        try:
            quote = self.tr_post(mode, "/api/dostk/mrkcond", "ka10001", {"stk_cd": code})
            name = self._find_name_recursive(quote)
            if name:
                return name
        except Exception:  # nosec
            pass
        return ""

    def quote(self, code: str, mode: str = "live") -> tuple[int, str]:
        errors: list[str] = []

        try:
            quote = self.tr_post(mode, "/api/dostk/mrkcond", "ka10001", {"stk_cd": code})
            data = quote.get("output") if isinstance(quote, dict) else None
            if isinstance(data, dict):
                current = self._extract_from_quote(data)
                if current > 0:
                    return current, f"kiwoom-{mode}-ka10001-output"
            if isinstance(quote, dict):
                current = self._extract_from_quote(quote)
                if current > 0:
                    return current, f"kiwoom-{mode}-ka10001-top"
        except Exception as exc:  # nosec
            errors.append(f"{mode}:ka10001:{exc}")

        try:
            ob = self.tr_post(mode, "/api/dostk/mrkcond", "ka10004", {"stk_cd": code})
            ob_data = ob.get("output") if isinstance(ob, dict) else None
            if isinstance(ob_data, dict):
                current, kind = self._extract_from_orderbook(ob_data)
                if current > 0:
                    return current, f"kiwoom-{mode}-ka10004-{kind}-output"
            if isinstance(ob, dict):
                current, kind = self._extract_from_orderbook(ob)
                if current > 0:
                    return current, f"kiwoom-{mode}-ka10004-{kind}-top"
        except Exception as exc:  # nosec
            errors.append(f"{mode}:ka10004:{exc}")

        return 0, "quote-unavailable | " + " ; ".join(errors[-4:])


    def fetch_positions(self, mode: str) -> list[dict[str, Any]]:
        if not self.pos_api_id:
            raise ValueError("KIWOOM_POS_API_ID not set")
        body = {"acnt_no": self.account_no, "prdt_no": self.product_no}
        resp = self.tr_post(mode, self.pos_path, self.pos_api_id, body)
        rows = []
        output = resp.get("output") if isinstance(resp, dict) else None
        candidates = output if output is not None else resp
        if isinstance(candidates, list):
            iterable = candidates
        elif isinstance(candidates, dict):
            iterable = [v for v in candidates.values() if isinstance(v, dict)] or [candidates]
        else:
            iterable = []
        for item in iterable:
            code = str(item.get("stk_cd") or item.get("code") or "").strip()
            if not code:
                continue
            qty = self._to_price(item.get("qty") or item.get("hold_qty") or item.get("rmnd_qty"))
            avg_price = self._to_price(item.get("avg_prc") or item.get("pchs_avg_pric") or item.get("avg_price"))
            rows.append({"code": code, "qty": qty, "avg_price": float(avg_price), "eval_amount": int(qty * avg_price)})
        return rows

    def fetch_fills(self, mode: str, date_str: str) -> list[dict[str, Any]]:
        if not self.fill_api_id:
            raise ValueError("KIWOOM_FILL_API_ID not set")
        body = {"acnt_no": self.account_no, "prdt_no": self.product_no, "date": date_str}
        resp = self.tr_post(mode, self.fill_path, self.fill_api_id, body)
        output = resp.get("output") if isinstance(resp, dict) else None
        if isinstance(output, list):
            return output
        if isinstance(output, dict):
            return [output]
        return []

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
LAST_NAME: dict[str, str] = {}


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


def record_fill(mode: str, side: str, code: str, qty: int, price: int) -> dict[str, Any]:
    with LOCK:
        positions: dict[str, Any] = STATE["positions"]
        pos = positions.get(code, {"qty": 0, "avg_price": 0})
        realized = 0.0
        executed_qty = qty
        if side == "BUY":
            total_cost = pos["avg_price"] * pos["qty"] + price * qty
            new_qty = pos["qty"] + qty
            pos["qty"] = new_qty
            pos["avg_price"] = total_cost / new_qty if new_qty else 0
        else:
            executed_qty = min(qty, pos["qty"])
            if executed_qty > 0:
                realized = (price - pos["avg_price"]) * executed_qty
                pos["qty"] -= executed_qty
                if pos["qty"] <= 0:
                    pos = {"qty": 0, "avg_price": 0}
        positions[code] = pos
        fill = {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "date": datetime.now().strftime("%Y-%m-%d"),
            "mode": mode,
            "side": side,
            "code": code,
            "qty": executed_qty,
            "requested_qty": qty,
            "price": price,
            "amount": price * executed_qty,
            "realized_pnl": round(realized, 2),
        }
        STATE["fills"].append(fill)
        STATE["fills"] = STATE["fills"][-5000:]
        save_state(STATE)
        return {
            "realized_pnl": round(realized, 2),
            "executed_qty": executed_qty,
            "executed_amount": price * executed_qty,
            "position_qty": int(pos["qty"]),
            "avg_price": round(pos["avg_price"], 4),
        }


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


def daily_report_from_broker(date_str: str, mode: str) -> dict[str, Any]:
    rows = KIWOOM.fetch_fills(mode, date_str)
    by_code: dict[str, dict[str, Any]] = defaultdict(lambda: {"buy_amount": 0, "sell_amount": 0, "realized_pnl": 0})
    norm_rows = []
    for r in rows:
        code = str(r.get("stk_cd") or r.get("code") or "")
        side = str(r.get("side") or r.get("trde_tp") or "").upper()
        if side in {"1", "B", "BUY", "매수"}:
            side = "BUY"
        elif side in {"2", "S", "SELL", "매도"}:
            side = "SELL"
        qty = KIWOOM._to_price(r.get("qty") or r.get("cntr_qty") or r.get("ord_qty"))
        price = KIWOOM._to_price(r.get("price") or r.get("cntr_prc") or r.get("ord_uv"))
        realized = float(r.get("realized_pnl") or 0)
        amt = price * qty
        if code:
            c = by_code[code]
            if side == "BUY":
                c["buy_amount"] += amt
            elif side == "SELL":
                c["sell_amount"] += amt
            c["realized_pnl"] += realized
        norm_rows.append({"code": code, "side": side, "qty": qty, "price": price, "realized_pnl": realized})
    detail = [{"code": k, **v} for k, v in by_code.items()]
    total = round(sum(x["realized_pnl"] for x in detail), 2)
    return {"date": date_str, "total_realized_pnl": total, "count": len(norm_rows), "by_code": detail, "fills": norm_rows, "source": "broker-api"}


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
                json_response(self, 200, {"status": "ok", "api_enabled": KIWOOM.enabled(), "api_enabled_mock": KIWOOM.enabled("mock"), "api_enabled_live": KIWOOM.enabled("live"), "trade_mode": STATE["trade_mode"], "live_order": KIWOOM.can_live_order(), "use_mock_env": _env_bool("KIWOOM_USE_MOCK", True)})
                return
            if p.path == "/mode":
                json_response(self, 200, {"trade_mode": STATE["trade_mode"]})
                return
            if p.path.startswith("/symbol/"):
                code = p.path.split("/symbol/", 1)[1]
                if not code:
                    json_response(self, 400, {"error": "missing code"})
                    return
                mode = STATE["trade_mode"]
                name = KIWOOM.symbol_name(code, mode=mode) if KIWOOM.enabled(mode) else COMMON_SYMBOLS.get(code, "")
                if name:
                    with LOCK:
                        LAST_NAME[code] = name
                json_response(self, 200, {"code": code, "name": name, "resolved": bool(name)})
                return
            if p.path == "/positions":
                mode = STATE["trade_mode"]
                if mode == "live" and KIWOOM.enabled("live"):
                    try:
                        rows = KIWOOM.fetch_positions("live")
                        for row in rows:
                            row["name"] = LAST_NAME.get(row["code"]) or COMMON_SYMBOLS.get(row["code"], "")
                        json_response(self, 200, {"count": len(rows), "positions": rows, "source": "broker-api"})
                        return
                    except Exception as exc:  # nosec
                        json_response(self, 502, {"error": f"positions api failed: {exc}"})
                        return
                with LOCK:
                    rows = []
                    for code, pos in STATE.get("positions", {}).items():
                        rows.append({
                            "code": code,
                            "name": LAST_NAME.get(code) or COMMON_SYMBOLS.get(code, ""),
                            "qty": int(pos.get("qty", 0)),
                            "avg_price": float(pos.get("avg_price", 0)),
                            "eval_amount": int(pos.get("qty", 0) * pos.get("avg_price", 0)),
                        })
                json_response(self, 200, {"count": len(rows), "positions": rows, "source": "local"})
                return
            if p.path.startswith("/quote/"):
                code = p.path.split("/quote/", 1)[1]
                if not code:
                    json_response(self, 400, {"error": "missing code"})
                    return
                mode = STATE["trade_mode"]
                if KIWOOM.enabled(mode):
                    price, source = KIWOOM.quote(code, mode=mode)
                    if price > 0:
                        name = KIWOOM.symbol_name(code, mode=mode) or LAST_NAME.get(code) or COMMON_SYMBOLS.get(code, "")
                        with LOCK:
                            LAST_PRICE[code] = price
                            if name:
                                LAST_NAME[code] = name
                        json_response(self, 200, {"code": code, "name": name, "price": price, "source": source})
                        return

                    with LOCK:
                        last = LAST_PRICE.get(code)
                    if last is not None:
                        json_response(self, 200, {"code": code, "name": LAST_NAME.get(code) or COMMON_SYMBOLS.get(code, ""), "price": last, "source": "last-good", "warning": source})
                        return

                    json_response(self, 502, {"error": "quote unavailable", "code": code, "source": source})
                else:
                    json_response(self, 200, {"code": code, "name": COMMON_SYMBOLS.get(code, ""), "price": demo_quote(code), "source": "demo"})
                return
            if p.path == "/reports/daily":
                d = qs.get("date", [datetime.now().strftime("%Y-%m-%d")])[0]
                source = qs.get("source", ["auto"])[0]
                mode = STATE["trade_mode"]
                if source in {"api", "auto"} and mode == "live" and KIWOOM.enabled("live"):
                    try:
                        json_response(self, 200, daily_report_from_broker(d, mode="live"))
                        return
                    except Exception as exc:  # nosec
                        if source == "api":
                            json_response(self, 502, {"error": f"daily report api failed: {exc}"})
                            return
                local = daily_report(d)
                local["source"] = "local"
                json_response(self, 200, local)
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
                if broker.get("status") == "live":
                    # 실주문은 체결 결과를 브로커 조회 API로 확인한다.
                    fill_info = {"realized_pnl": 0.0, "executed_qty": 0, "executed_amount": 0, "position_qty": -1, "avg_price": 0}
                else:
                    fill_info = record_fill(mode, side, code, qty, price)
                broker["mode"] = mode
                broker.update(fill_info)
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
