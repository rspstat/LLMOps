# 2026-10-13 · 클라이언트 `X-Request-ID`를 trace 키로 쓰면 충돌한다

> 초안입니다. 아래 "증상"은 실제 장애가 아니라 **구현 중 설계 검토에서 발견한 결함**이며, 구 동작을 코드로 재현해 실패시켜 보지는 않았습니다. PK 제약과 `write_many`의 동작(테스트로 검증됨)에서 추론한 결과입니다.

## 증상 (예상되는 동작)

2단계 설계 승인 시점의 계획은 "클라이언트가 보낸 `X-Request-ID`가 안전한 값이면 그대로 쓰고, 없으면 생성"이었다. trace 저장소(7단계)를 만들면서 보니 이 값이 `trace_events`의 기본키 `(request_id, seq)`의 일부였다. 그러면:

- 클라이언트가 같은 ID로 두 번 요청하면 두 번째 요청의 `INSERT`가 PK 제약(`IntegrityError`)으로 실패한다.
- `flush_trace`는 trace 저장 실패가 응답을 깨뜨리지 않도록 예외를 삼키므로, 사용자는 200을 받지만 **두 번째 요청의 trace가 조용히 사라진다**.
- 인증된 클라이언트가 다른 요청의 ID를 알면 그 ID로 요청을 보내 trace를 선점하거나 오염시킬 수 있다.

## 원인

"상관관계용 ID"와 "저장소 키"라는 서로 다른 역할을 하나의 값에 맡겼다. 클라이언트가 통제하는 값은 유일성을 보장할 수 없는데, 이를 기본키로 삼았다.

## 시도한 것

| 대안 | 판단 |
|---|---|
| 저장 시 `seq`를 `max(seq)+1`로 이어 붙여 충돌을 피한다 | 두 요청의 이벤트가 한 request_id 아래 섞여 평가(3단계)에서 요청 단위 집계가 깨진다. 데이터는 남지만 의미가 틀어진다 |
| 충돌 시 400으로 거부한다 | 재시도하는 클라이언트(같은 ID를 의도적으로 재사용)를 깨뜨린다 |
| 서버가 항상 ID를 생성하고 클라이언트 값은 별도 필드로 기록한다 | 채택 |

## 해결

- `gateway/middleware.py`: `request_id`는 항상 `uuid4().hex`로 서버가 생성한다. 응답 헤더 `X-Request-ID`도 이 값이다.
- 클라이언트가 `[A-Za-z0-9._-]{1,64}` 형식의 `X-Request-ID`를 보내면 `client_request_id`로 보관하고, 첫 trace 이벤트(`guard`)의 `detail`에 기록한다. 형식이 맞지 않으면 버린다.
- 테스트: 같은 클라이언트 ID로 두 번 요청해도 서로 다른 서버 ID가 발급되고(`test_request_id_is_server_generated_even_if_client_sends_one`), 두 trace 모두에 `client_request_id`가 남는다(`test_client_request_id_is_recorded_but_not_used_as_trace_key`).
- 결정 기록: `docs/architecture.md` 결정 기록 표(2026-10-13).
- 커밋: `fix: always generate server-side request id, keep client id for correlation only`

## 배운 점

- 저장소 키를 설계할 때는 "누가 이 값을 정하는가"를 먼저 묻는다. 외부 입력은 상관관계 정보일 뿐 식별자가 아니다.
- "저장 실패를 응답에 영향 주지 않게 삼키는" 정책은 가용성에는 좋지만, 이번처럼 데이터 손실을 조용하게 만든다. 그래서 `flush_trace`는 삼키되 `logger.exception`으로 남기고, 테스트로 그 로그를 확인한다(`test_trace_write_failure_does_not_fail_the_request`).
- 승인된 계획이라도 구현 중 근거가 바뀌면 바꾸고, 바꾼 이유를 결정 기록에 남긴다.

## 같은 세션의 사소한 관찰 (해결 아님)

- Windows PowerShell 5.1의 `Get-Content`가 BOM 없는 UTF-8 한글을 깨뜨려 보여 주는 현상이 있었다(파일 자체는 정상, 읽기 도구로는 정상 표시). 한글 문서는 `Read` 도구로 확인했다.
- Starlette가 `TestClient`에서 `httpx` 대신 `httpx2`를 권장하는 deprecation 경고가 나온다. 동작에는 영향이 없고 아직 대응하지 않았다.
