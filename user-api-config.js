/**
 * 키움 REST API 개인 설정 파일
 * - 이 파일에 본인 키만 입력해서 사용하세요.
 * - 정적 페이지 특성상 키 노출 위험이 있으니 실계좌 민감키는 주의해서 사용하세요.
 */
window.USER_API_CONFIG = {
  provider: 'kiwoom_rest',

  // 호출할 데이터 URL
  // 예: 로컬 샘플('/api/stocks.json') 또는 키움 REST 데이터 프록시 URL
  apiUrl: '/api/stocks.json',

  // 키움 REST 인증값(필요한 항목만 입력)
  appKey: '',
  appSecret: '',
  accessToken: '', // 예: 'eyJ...'

  // 키움 연속조회/부가 헤더가 필요하면 여기에 추가
  headers: {
    // 'cont-yn': 'N',
    // 'next-key': ''
  }
};
