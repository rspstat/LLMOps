# gateway

FastAPI 게이트웨이. 클라이언트 요청을 받아 가드 → 라우터 → provider 순으로 처리하고 모든 단계를 trace로 남긴다. 요청 한 건의 흐름은 [docs/architecture.md](../../../docs/architecture.md)의 "요청 흐름"에 있다.

## 응답 헤더

| 헤더 | 의미 |
|---|---|
| `X-Request-ID` | 이 요청의 trace 키 |
| `X-LLMOps-Route` | 라우터가 고른 경로(`small` / `frontier`) |
| `X-LLMOps-Fallback` | 다른 모델이 대신 답했는지(`true` / `false`). 답한 모델은 본문의 `model` |
| `X-LLMOps-Route-Reason` | 사유 범주(`judge_easy`, `promoted_low_confidence`, `keyword` 등) |
| `X-LLMOps-P-Easy` | 판정기가 낸 `p(easy)`(판정기를 거친 요청만) |
| `X-LLMOps-Cost-USD` | 이 요청의 비용(판정 호출 포함) |
| `X-LLMOps-Baseline-Cost-USD` | 같은 답을 상용 모델 단가로만 계산한 값. 상용 단가가 설정되지 않으면 생략. 둘의 차이가 아낀 금액(추정치) |

## 오류 형식

모든 오류 응답(401, 404, 405, 422, 500 포함)이 OpenAI와 같은 모양 `{"error": {"message", "type", "param", "code"}}` 하나이다. 그래서 OpenAI SDK의 예외 타입으로 그대로 올라온다. openai 파이썬 SDK 3.42.1로 확인했다: 401은 `AuthenticationError`, 입력 가드 차단(400)은 `BadRequestError`, 검증 오류(422)는 `UnprocessableEntityError`.

## 웹 화면 서빙

게이트웨이가 `code/frontend/dist`를 `/`로 서빙한다(`WEB_UI_ENABLED`, 기본 `true`). 빌드하지 않으면 `/`는 빌드 안내와 함께 503을 돌려준다. 화면의 동작은 [프런트엔드 문서](../../frontend/README.md)에 있다.
