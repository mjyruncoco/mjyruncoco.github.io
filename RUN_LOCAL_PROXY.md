# 로컬 자동실행 서버 실행 방법

브라우저에는 키를 넣지 않고, 로컬 서버가 키움 API를 대신 호출합니다.

## 0) .env 파일
프로젝트 루트에 `.env`를 두면 서버 시작 시 자동으로 읽습니다. (이미 셸에 있는 값은 덮어쓰지 않음)


## 1) 환경변수
```bash
export KIWOOM_APPKEY='발급_appkey'
export KIWOOM_SECRETKEY='발급_secretkey'

# (권장) 모의/실전 분리 키가 있으면 각각 설정
export KIWOOM_MOCK_APPKEY='모의_appkey'
export KIWOOM_MOCK_SECRETKEY='모의_secretkey'
export KIWOOM_LIVE_APPKEY='실전_appkey'
export KIWOOM_LIVE_SECRETKEY='실전_secretkey'

# 실주문 사용 시(매우 주의)
export KIWOOM_ACCOUNT_NO='계좌번호'
export KIWOOM_PRODUCT_NO='01'
export AUTO_LIVE_ORDER=false   # 기본 false (paper)

# 초기 모드 (웹에서도 변경 가능: mock|live)
export KIWOOM_USE_MOCK=false  # true면 기본 mock, false면 기본 live
export KIWOOM_INITIAL_MODE=live

# (선택) 실계좌 잔고/체결 조회 TR 설정
export KIWOOM_POS_API_ID=''
export KIWOOM_POS_PATH='/api/dostk/inqr'
export KIWOOM_FILL_API_ID=''
export KIWOOM_FILL_PATH='/api/dostk/inqr'

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
- 연결 확인에서 API 키 인식 상태를 `api(mock/live)`로 확인 가능
- 거래 모드: `모의투자(mock)` / `실투자(live)`
- 보유수량/당일수익 조회 시 `source=broker-api|local`가 표시됩니다.
- 모드 적용 버튼 누르면 서버 모드가 즉시 반영됨
- 당일 수익 요약(실현손익) 조회 가능

## 엔드포인트
- `GET /health`
- `GET /mode`
- `POST /mode` (`{"trade_mode":"mock|live"}`)
- `GET /quote/{code}`
- `GET /symbol/{code}` (종목명 조회, 실패 시 `resolved=false`)
- `GET /positions` (현재 보유수량/평균단가 조회)
- `POST /orders/execute` (`code`, `side`, `qty`, `price`)
- `GET /reports/daily?date=YYYY-MM-DD`

## 수익 데이터 저장
- 서버는 체결/실현손익을 `trade_state.json`에 저장합니다.
- 일자별 요약은 `/reports/daily`로 확인합니다.

## 주의
- `GET /quote/{code}` 는 주문 모드와 별개로 live 시세 TR(`ka10001` → `ka10004`) 기준으로 조회합니다.
- 조회 실패 시 가짜 가격을 섞지 않고, 최근 정상값(`last-good`)이 있으면 그 값을 반환하고 없으면 502를 반환합니다.
- `/orders/execute` 응답에는 `executed_qty`, `executed_amount`, `position_qty`, `avg_price`가 포함됩니다.
- 종목명 조회가 실패하면 UI에 `종목명 미확인`으로 표시되며, 일부 대표 종목은 내장 매핑으로 보완됩니다.
- 주문 전송 여부만 `mock|live` 모드 + `AUTO_LIVE_ORDER` 설정의 영향을 받습니다.
- `AUTO_LIVE_ORDER=true` + 계좌정보 설정 시 실제 주문 전송될 수 있습니다.
- 먼저 `mock` + `AUTO_LIVE_ORDER=false`로 충분히 검증하세요.
