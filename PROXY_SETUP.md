# Kiwoom REST 로컬 프록시 실행 방법

브라우저 페이지에 실계좌 키를 넣지 않고, **내 PC에서 프록시 서버**를 띄워 키를 안전하게 보관하는 방식입니다.

## 1) 설정 파일 준비

```bash
cp proxy_config.sample.json proxy_config.local.json
```

`proxy_config.local.json`에 키움 REST 대상 URL/헤더를 입력합니다.

- `target_url`: 실제 조회할 키움 REST 엔드포인트
- `headers.appkey`, `headers.appsecret`, `headers.authorization`
- 필요하면 `cont-yn`, `next-key` 등 추가

## 2) 프록시 서버 실행

```bash
python3 proxy_server.py --host 127.0.0.1 --port 8787 --config proxy_config.local.json
```

정상 실행 시:
- `http://127.0.0.1:8787/health`
- `http://127.0.0.1:8787/api/stocks` (키움 REST로 포워딩)

## 3) 웹 페이지 설정

`user-api-config.js`에서 `apiUrl`을 아래처럼 둡니다.

```js
apiUrl: 'http://127.0.0.1:8787/api/stocks'
```

이제 페이지의 `API 불러오기`는 로컬 프록시를 호출하고, 키는 브라우저가 아닌 내 PC 프록시에만 저장됩니다.

## 보안 주의

- `proxy_config.local.json`은 절대 외부 공유/커밋하지 마세요.
- 실계좌 키는 브라우저 JS 파일에 직접 넣지 않는 것을 권장합니다.
