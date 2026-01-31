# Local Binance Bridge (Health Check)

This lightweight local server provides the `/health` endpoint that the demo UI checks
before marking the Binance connection as ready. It **does not** place orders or sign
requests yet; it is a safe starting point you can extend later.

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
