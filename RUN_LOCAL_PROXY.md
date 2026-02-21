# 로컬 키움 프록시 실행 방법

## 1) 필수
브라우저 HTML에 AppKey/Secret을 넣지 않고, 로컬 서버 환경변수로만 보관합니다.

```bash
export KIWOOM_APPKEY='발급받은_appkey'
export KIWOOM_SECRETKEY='발급받은_secretkey'
# 선택: 모의
export KIWOOM_USE_MOCK=true
# 선택: 분석 대상 watchlist
export WATCHLIST='005930,000660,035420'
```

## 2) 서버 실행
```bash
python local_proxy_server.py
```

서버 기본 주소는 `http://127.0.0.1:9000` 입니다.

## 3) 프론트 실행
```bash
python -m http.server 8000
```

브라우저에서 `http://127.0.0.1:8000` 접속 후:
- 로컬 서버 주소: `http://127.0.0.1:9000`
- 연결 확인 클릭
- API 분석 실행 클릭

## 제공 엔드포인트
- `GET /health`
- `GET /candidates?market=000`
- `GET /orderbook/{code}`

## 참고
- 현재 후보군은 `WATCHLIST` 기반으로 구성하고, 각 코드의 호가는 키움 `ka10004`를 호출합니다.
- 실거래 전에는 반드시 소액/모의로 검증하세요.
