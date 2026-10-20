# gateway

FastAPI 게이트웨이. 클라이언트 요청을 받아 가드 → 라우터 → provider 순으로 처리하고 모든 단계를 trace로 남긴다.

예정: OpenAI 호환 `/v1/chat/completions`, API 키 인증, 스트리밍, 요청 ID/trace 기록
