# 로컬 자동실행 서버 실행 방법

브라우저에는 키를 넣지 않고, 로컬 서버가 키움 API를 대신 호출합니다.

## 1) 환경변수
```bash
export KIWOOM_APPKEY='발급_appkey'
export KIWOOM_SECRETKEY='발급_secretkey'

# 실주문 사용 시(매우 주의)
export KIWOOM_ACCOUNT_NO='계좌번호'
export KIWOOM_PRODUCT_NO='01'
export AUTO_LIVE_ORDER=false   # 기본 false (paper)

# 초기 모드 (웹에서도 변경 가능: mock|live)
export KIWOOM_INITIAL_MODE=mock

# 포트(기본 9000)
export PORT=9000
```

## 2) 로컬 프록시 서버 실행
```bash
python local_proxy_server.py
```

## 3) 프론트 실행
```bash
python -m http.server 8000
```

브라우저 접속: `http://127.0.0.1:8000`

## 웹에서 설정 가능
- 거래 모드: `모의투자(mock)` / `실투자(live)`
- 모드 적용 버튼 누르면 서버 모드가 즉시 반영됨
- 당일 수익 요약(실현손익) 조회 가능

## 엔드포인트
- `GET /health`
- `GET /mode`
- `POST /mode` (`{"trade_mode":"mock|live"}`)
- `GET /quote/{code}`
- `POST /orders/execute` (`code`, `side`, `qty`, `price`)
- `GET /reports/daily?date=YYYY-MM-DD`

## 수익 데이터 저장
- 서버는 체결/실현손익을 `trade_state.json`에 저장합니다.
- 일자별 요약은 `/reports/daily`로 확인합니다.

## 주의
- `GET /quote/{code}` 는 장중/장외 왜곡을 줄이기 위해 모드와 무관하게 실전 시세 API 기준으로 현재가를 조회합니다.
- 주문 전송 여부만 `mock|live` 모드 + `AUTO_LIVE_ORDER` 설정의 영향을 받습니다.
- `AUTO_LIVE_ORDER=true` + 계좌정보 설정 시 실제 주문 전송될 수 있습니다.
- 먼저 `mock` + `AUTO_LIVE_ORDER=false`로 충분히 검증하세요.
