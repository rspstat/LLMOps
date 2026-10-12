# 아키텍처 설계 노트

> 설계가 확정되는 대로 이 문서를 채웁니다. 중간발표 자료의 근거 문서로 사용합니다.

## 1. 요청 흐름

> 1단계(구현됨) 기준. 출력 가드, Jev 판정, 스트리밍은 이후 단계.

`POST /v1/chat/completions` (Bearer 인증, 비스트리밍)

| 순서 | 단계 | 입력 → 출력 | 실패/차단 시 동작 |
|---|---|---|---|
| 0 | 요청 ID | 서버가 `request_id` 생성, 응답 헤더 `X-Request-ID`로 반환. 클라이언트가 보낸 `X-Request-ID`는 안전한 값일 때만 `client_request_id`로 trace에 기록 | 항상 서버 생성 (trace 키 충돌·위조 방지) |
| 1 | 입력 가드 | 모든 메시지 본문 → `allow` / `block` + 사유 + 점수 | 400 `input_blocked`. 응답에는 범주만(`prompt_injection` 등), 세부 규칙은 trace에만 |
| 2 | 라우터 | 사용자 메시지 → `small` / `frontier` + 사유 + 신뢰도 | 규칙이 없으면 `small`을 낮은 신뢰도(기본 0.5)로 선택. 2단계에서 이 값으로 승격 |
| 3 | provider 호출 | 라우트에 매핑된 provider | `ProviderError`면 오프라인 fallback으로 1회 재시도(trace에 두 시도 모두 기록). 둘 다 실패하면 502 `provider_unavailable` |
| 4 | trace 저장 | 요청 단위로 모아 한 트랜잭션으로 기록 | 저장 실패는 로그만 남기고 응답은 정상 반환 |

- `max_tokens`는 `MAX_OUTPUT_TOKENS`로 상한을 둔다. 요청의 `model` 필드는 받지만 라우터가 결정한다.
- 가드·라우터 임계값(최대 입력 길이, 긴 프롬프트 기준, 키워드, 단가)은 모두 설정(`gateway/settings.py`, 환경 변수)이며 코드에 하드코딩하지 않는다.
- 레이어 의존 방향: `gateway` → `guards` / `router` / `providers`. 하위 모듈은 `gateway`를 import하지 않고 자기 설정 객체만 받는다.

## 2. Provider 인터페이스

`providers/base.py`의 `Provider` 프로토콜: `name: str`, `async complete(ProviderRequest) -> ProviderResponse`.

- 요청: `messages`, `max_tokens`, `temperature`(선택). 응답: `content`, `model`, `prompt_tokens`, `completion_tokens`, `finish_reason`.
- 실패는 모두 `ProviderError`로 통일(네트워크, HTTP 오류, 잘못된 응답). 상세 오류 본문은 200자까지만 담고 키는 포함하지 않는다.
- 지연 시간은 호출하는 쪽(파이프라인)이 시도마다 잰다. provider가 직접 보고하지 않는다.
- 구현: `MockProvider`(결정적 echo, 장애 주입 가능), `OpenAICompatProvider`(vLLM·OpenAI 등 `/chat/completions` 호환 서버). Anthropic·Google 네이티브 API와 Jev는 같은 프로토콜로 이후 추가.
- `ProviderRegistry`: 라우트 이름 → provider, 그리고 항상 오프라인인 fallback.
- 기본 provider는 mock이다. 실제 provider는 `SMALL_PROVIDER` / `FRONTIER_PROVIDER`를 명시적으로 바꿔야만 켜진다.

## 3. 라우팅 정책

(판정 기준, 신뢰도 임계값, 상위 모델 승격 규칙, fallback)

## 4. 가드레일

(탐지 대상, 차단/마스킹/경고 정책, 오탐·미탐 처리)

## 5. Trace 스키마

요청 하나가 단계(guard / router / provider)마다 한 행씩 `trace_events`에 쌓인다. 이후 단계의 이벤트(출력 가드, 평가 등)도 스키마 변경 없이 `stage` 값만 늘려 기록한다.

| 컬럼 | 타입 | 설명 |
|---|---|---|
| `request_id` | TEXT | 서버 생성 ID (= 응답 헤더 `X-Request-ID`). PK 일부 |
| `seq` | INTEGER | 요청 안에서의 순서(0부터). PK 일부 |
| `stage` | TEXT | `guard` / `router` / `provider` |
| `decision` | TEXT | guard: `allow`·`block`, router: 선택한 라우트, provider: `ok`·`error` |
| `confidence` | DOUBLE PRECISION | guard는 위험 점수(규칙은 0 또는 1), router는 신뢰도 |
| `model` | TEXT | 실제 응답한 모델 (provider 단계) |
| `prompt_tokens`, `completion_tokens` | INTEGER | 서버가 `usage`를 주지 않으면 추정값 |
| `cost_usd` | DOUBLE PRECISION | 토큰 × 라우트별 단가(설정). fallback·mock은 0 |
| `latency_ms` | INTEGER | 단계별 소요 시간 |
| `detail_json` | TEXT | 사유, provider 이름, fallback 여부, 오류 요약, `client_request_id`, 입력 길이·해시 등 |
| `created_at` | TEXT | ISO-8601 UTC |

- 이식성: `AUTOINCREMENT` 같은 방언 기능 없이 복합 PK만 쓰고, 타입은 TEXT / INTEGER / DOUBLE PRECISION으로 제한했다. PostgreSQL 이행 시 `detail_json` → JSONB, `created_at` → TIMESTAMPTZ.
- 저장소 선택: `DATABASE_URL`(`sqlite:///경로`)을 `create_trace_store()`가 해석한다. `postgresql://`은 `NotImplementedError`. `TraceStore` 프로토콜은 `write_many(events)`(한 트랜잭션)와 `get(request_id)`(`seq` 순)이다.
- 개인정보: 프롬프트 본문은 기본적으로 저장하지 않는다(`input_chars`, `input_sha256` 앞 16자만). `TRACE_STORE_CONTENT=true`일 때만 `detail.input`에 저장한다. 레포가 Public이므로 DB 파일은 커밋하지 않는다(`*.sqlite3`는 `.gitignore`).
- 조회 API는 두지 않는다. 확인은 응답 헤더의 요청 ID와 `TraceStore.get()`으로 한다.

## 6. 평가 설계

(데이터셋, 지표, judge 구성, 비교 실험 목록)

## 7. 결정 기록

| 날짜 | 결정 | 이유 |
|---|---|---|
| 2026-10-12 | 저장소 이름 `LLMOps`, Public 생성 | |
| 2026-10-13 | trace 저장소는 SQLite로 시작. `TraceStore` 인터페이스와 `DATABASE_URL`로 선택하고, 이식 가능한 컬럼 타입만 사용. 평가(3단계) 전 PostgreSQL로 교체 | 환경에 PostgreSQL이 없고 1단계 목표가 끝까지 동작하는 관통이므로. 평가 단계에서 집계 쿼리가 필요해지는 시점에 이행 |
| 2026-10-13 | `openai_compat` provider를 1단계에 포함. 테스트는 mock HTTP만, 실호출은 `ALLOW_LIVE_CALLS=1`로 켜는 수동 스모크 스크립트(`scripts/smoke_live.py`)로 분리 | 실제 모델 호출 경로는 검증하되 비용과 키 노출을 통제하기 위해 |
| 2026-10-13 | `/v1/traces` 조회 엔드포인트는 두지 않음. 응답 헤더에 `X-Request-ID`, 저장소에 `get(request_id)` 제공 | 인증과 노출 범위 문제를 피하고 1단계 범위를 지키기 위해 |
| 2026-10-13 | Python 3.12를 uv로 고정 (`.python-version`, `requires-python >=3.11`, `uv.lock` 커밋) | 재현 가능한 환경, 시스템 Python 혼재(msys64/3.14) 회피 |
| 2026-10-13 | 기본 provider는 mock, trace에 프롬프트 본문은 기본 미저장(길이·해시만) | 실수로 인한 과금 방지, Public 레포와 개인정보 보호 |
| 2026-10-13 | 요청 ID는 항상 서버가 생성하고, 클라이언트의 `X-Request-ID`는 안전한 값만 `client_request_id`로 trace에 기록 | trace PK가 요청 ID라서, 클라이언트 값을 그대로 쓰면 재사용 시 저장 실패·타 요청 trace 오염이 가능. 구현 중 발견해 계획(수용/생성)에서 변경 |
| 2026-10-13 | provider 장애 시 항상 오프라인 mock fallback으로 응답하고 trace에 기록. 단, fallback 응답의 모델명은 `fallback-mock`으로 드러남 | Jev·외부 API 장애에도 시스템이 동작해야 한다는 원칙(CLAUDE.md). 품질 저하는 숨기지 않고 기록 |
| 2026-10-13 | 입력 가드·라우터는 1단계에서 규칙(정규식, 길이, 키워드)만 사용 | 한 줄 관통이 목표. 정확도는 한계가 있고(오탐·미탐 존재) 4단계(가드 고도화)와 2단계(Jev 라우팅)에서 개선·측정 |
