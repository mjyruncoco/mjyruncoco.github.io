/**
 * 브라우저용 설정 파일 (민감키는 넣지 말고 프록시 서버에 넣으세요)
 */
window.USER_API_CONFIG = {
  provider: 'kiwoom_rest_proxy',

  // 내 PC에서 띄운 로컬 프록시 주소
  // proxy_server.py 기본값: 127.0.0.1:8787
  apiUrl: 'http://127.0.0.1:8787/api/stocks',

  // 브라우저에서 직접 보낼 추가 헤더가 있으면 입력 (보통 비워둠)
  headers: {}
};
