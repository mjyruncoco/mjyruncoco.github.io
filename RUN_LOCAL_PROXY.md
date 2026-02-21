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

# 모의 서버 사용 시
export KIWOOM_USE_MOCK=true

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

## 프론트 사용 순서
1. 로컬 API 주소 확인 (`http://127.0.0.1:9000`)
2. 연결 확인
3. 종목코드/매수가/목표가/손절가/수량 입력 후 규칙 추가
4. 모니터링 시작

## 엔드포인트
- `GET /health`
- `GET /quote/{code}`
- `POST /orders/execute`  (payload: `code`, `side`, `qty`, `price`)

## 주의
- `AUTO_LIVE_ORDER=true` + 계좌정보 설정 시 실제 주문 전송될 수 있습니다.
- 먼저 `AUTO_LIVE_ORDER=false`(paper)로 충분히 검증하세요.
