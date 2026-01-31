# Local Binance Bridge (Health Check)

This lightweight local server provides the `/health` endpoint that the demo UI checks
before marking the Binance connection as ready. It **does not** place orders or sign
requests yet; it is a safe starting point you can extend later.

It can also send a **real spot market order** if you provide Binance API keys via
environment variables. Use this carefully.

## Requirements
- Python 3.8+

## Run
```bash
python local_bridge/server.py
```

By default it listens on `http://127.0.0.1:8787`.

### Custom host/port
```bash
LOCAL_BRIDGE_HOST=127.0.0.1 LOCAL_BRIDGE_PORT=8787 python local_bridge/server.py
```

## Verify
Open in a browser:
```
http://127.0.0.1:8787/health
```

You should see:
```json
{"status": "ok"}
```

## Live order (optional)
Set your keys and (optionally) use testnet base URL:
```bash
export BINANCE_API_KEY=your_key
export BINANCE_API_SECRET=your_secret
export BINANCE_BASE_URL=https://testnet.binance.vision
python local_bridge/server.py
```

Alternatively, you can create a local config file at `local_bridge/keys.json`:
```json
{"api_key": "your_key", "api_secret": "your_secret"}
```

Then the UI can send a POST to `/order` with:
```json
{"symbol": "BTCUSDT", "side": "BUY", "type": "MARKET", "quoteOrderQty": 50}
```

## Switch testnet/live at runtime
You can switch the base URL after the server is running:
```bash
curl -X POST http://127.0.0.1:8787/config -H "Content-Type: application/json" -d '{"mode":"testnet"}'
curl -X POST http://127.0.0.1:8787/config -H "Content-Type: application/json" -d '{"mode":"live"}'
```
