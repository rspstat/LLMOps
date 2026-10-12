# 아키텍처 설계 노트

> 설계가 확정되는 대로 이 문서를 채웁니다. 중간발표 자료의 근거 문서로 사용합니다.

## 1. 요청 흐름

> 2단계(구현됨) 기준. 출력 가드, 스트리밍은 이후 단계. 판정기(Jev)는 `ROUTER_MODE=hybrid` 또는 `judge_only`일 때만 사용되고, 기본(`rules`)은 1단계와 같다.

`POST /v1/chat/completions` (Bearer 인증, 비스트리밍)

| 순서 | 단계 | 입력 → 출력 | 실패/차단 시 동작 |
|---|---|---|---|
| 0 | 요청 ID | 서버가 `request_id` 생성, 응답 헤더 `X-Request-ID`로 반환. 클라이언트가 보낸 `X-Request-ID`는 안전한 값일 때만 `client_request_id`로 trace에 기록 | 항상 서버 생성 (trace 키 충돌·위조 방지) |
| 1 | 입력 가드 | 모든 메시지 본문 → `allow` / `block` + 사유 + 점수 | 400 `input_blocked`. 응답에는 범주만(`prompt_injection` 등), 세부 규칙은 trace에만 |
| 2 | 라우터 (+ 판정기) | 사용자 메시지 → `small` / `frontier` + 사유 + 신뢰도. 판정기를 불렀다면 `judge` 이벤트가 `router` 이벤트 바로 앞에 기록됨 | 규칙 hit이면 판정기를 부르지 않고 확정. 아니면 판정 → 임계값 승격(§3). 판정이 실패하면 규칙 결과로 대체하고 사유를 trace에 기록 |
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

### 판정 provider (`providers/decision.py`)

글을 생성하지 않는 닫힌 선택지 판정(Jev의 역할)은 별도 프로토콜이다: `DecisionProvider.decide(state, ChoiceQuestion) -> ChoiceDecision`.

- 입력: `state`(판정 근거 전부. 정책 포함)와 `ChoiceQuestion`(질문 키, 지시문, `선택지 → 설명`). 출력: `choice`, 선택지별 `probabilities`, `confidence`, 모델명, 입력·출력 토큰.
- `validate_decision()`이 라우터에서 한 번 더 검증한다: 모르는 선택지·확률 범위(0~1) 밖·확률 합 1.05 초과는 `ProviderError`로 처리해 잘못된 판정기가 라우팅을 움직이지 못하게 한다.
- 구현: `MockDecisionProvider`(요청 길이만 보는 결정적 가짜, 장애 주입 가능, 기본값), `JevProvider`(`POST {JEV_BASE_URL}`에 `model` + `state` + `questions{키:{type:"choice", instructions, criteria}}`, 응답 `answers.<키>.{choice, probabilities, confidence}` + `usage`).
- **`JevProvider`는 공식 문서가 아닌 서드파티 문서(LiteLLM, DigitalOcean)를 근거로 구현했고, 실제 키로 호출해 확인하지 않았다.** `confidence`의 의미와 오류 응답 형식은 문서에 없다. 접근 경로(공식, Vercel AI Gateway, DigitalOcean)마다 URL·모델명이 달라 둘 다 설정이다.

## 3. 라우팅 정책

`ROUTER_MODE`로 세 가지 방식을 고른다.

| 모드 | 동작 | 용도 |
|---|---|---|
| `rules` (기본) | 규칙만. 길이 ≥ `ROUTER_LONG_PROMPT_CHARS` 또는 키워드 → `frontier`, 아니면 `small`(신뢰도 0.5). 판정기를 만들지도 않음 | 1단계 동작, 비용 0 |
| `hybrid` | 규칙이 `frontier`로 확정하면 그대로(판정기 호출 없음). 아니면 판정기에 easy/hard를 질의 | 운영 후보 |
| `judge_only` | 규칙 hit이어도 항상 판정기에 질의(규칙 결과는 `detail.rule_hint`에 기록) | 3단계에서 같은 트래픽으로 규칙 대 판정기를 비교 |

**승격 규칙 (단일 임계값)**: 판정기의 `choice == "easy"`이고 `p(easy) ≥ ROUTER_PROMOTE_THRESHOLD`(기본 0.7)일 때만 `small`. 그 외는 모두 `frontier`이며 사유로 구분한다.

| `reason` | 의미 |
|---|---|
| `judge_easy` | 확신 있는 easy → small |
| `judge_hard` | 판정기가 hard로 판정 → frontier |
| `promoted_low_confidence` | easy라고 했지만 확률이 임계값 미만 → 안전하게 frontier로 승격 |
| `judge_unavailable` | 판정기 실패(오류·타임아웃·잘못된 응답) → 규칙 결과를 그대로 사용 |
| `long_prompt`, `keyword:*`, `default_small` | 규칙 결과 |

- 판정 시 `router` 이벤트의 `confidence`는 `p(easy)`이다. 임계값 하나만 훑으면 되도록 이렇게 정했고, 3단계 평가에서 τ를 바꿔 가며 비용·정확도를 측정한다.
- 판정 정책(문구, 선택지 설명)은 `router/policy.py`에 있고 버전을 가진다 → [docs/prompts/router-policy-v1.md](prompts/router-policy-v1.md). 정책은 `state`에 포함되어 요청마다 판정기에 전달된다.
- 판정기가 실패하면 규칙 결과로 대체한다(안전하게 `frontier`로 보내는 대안은 비용 때문에 택하지 않았다). 오분류 위험이 있으므로 `judge_unavailable` 비율을 trace로 감시한다.
- 범위 밖: 응답을 받은 뒤 품질을 보고 상위 모델로 재시도하는 cascade는 하지 않는다(6단계 벤치마크 후보).

## 4. 가드레일

(탐지 대상, 차단/마스킹/경고 정책, 오탐·미탐 처리)

## 5. Trace 스키마

요청 하나가 단계(guard / judge / router / provider)마다 한 행씩 `trace_events`에 쌓인다. 이후 단계의 이벤트(출력 가드, 평가 등)도 스키마 변경 없이 `stage` 값만 늘려 기록한다.

| 컬럼 | 타입 | 설명 |
|---|---|---|
| `request_id` | TEXT | 서버 생성 ID (= 응답 헤더 `X-Request-ID`). PK 일부 |
| `seq` | INTEGER | 요청 안에서의 순서(0부터). PK 일부 |
| `stage` | TEXT | `guard` / `judge` / `router` / `provider` |
| `decision` | TEXT | guard: `allow`·`block`, judge: 선택지(`easy`·`hard`) 또는 `error`, router: 선택한 라우트, provider: `ok`·`error` |
| `confidence` | DOUBLE PRECISION | guard는 위험 점수(규칙은 0 또는 1), judge는 판정기의 `confidence`, router는 규칙 신뢰도 또는 판정 시 `p(easy)` |
| `model` | TEXT | 실제 응답한 모델 (judge·provider 단계) |
| `prompt_tokens`, `completion_tokens` | INTEGER | judge에서는 입력·출력 토큰. 서버가 `usage`를 주지 않으면 추정값 |
| `cost_usd` | DOUBLE PRECISION | 토큰 × 단가(설정; 라우트별, 판정기는 `JEV_PRICE_*`). fallback·mock은 0 |
| `latency_ms` | INTEGER | 단계별 소요 시간. `router`의 값은 판정기 호출을 포함한 라우팅 전체 |
| `detail_json` | TEXT | 사유, provider 이름, fallback 여부, 오류 요약, `client_request_id`, 입력 길이·해시, 판정 시 `probabilities`·`policy_version`·`threshold`·`p_easy`·`rule_hint` 등 |
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
| 2026-10-13 | 승격 규칙은 단일 임계값: 판정기가 easy이고 `p(easy) ≥ ROUTER_PROMOTE_THRESHOLD`(0.7)일 때만 소형 모델, 그 외는 상용 모델 | 3단계 평가에서 조정할 값이 τ 하나라 비용·정확도 곡선을 단순하게 훑을 수 있음. 불확실하면 비싼 쪽으로 가는 보수적 방향 |
| 2026-10-13 | 판정기 실패 시 규칙 결과로 대체하고 `judge_unavailable`로 기록 (안전하게 frontier로 보내지 않음) | 판정기 장애가 곧 비용 급증이 되지 않게 함. 대신 오분류 위험이 있어 발생 비율을 trace로 감시 |
| 2026-10-13 | `ROUTER_MODE=judge_only` 포함 (규칙 단락 없이 항상 판정기에 질의) | 3단계·6단계에서 같은 트래픽으로 규칙 대 Jev를 비교하려면 필요. 코드는 몇 줄 |
| 2026-10-13 | 판정용 `DecisionProvider`를 생성용 `Provider`와 별도 프로토콜로 분리 | Jev는 `messages`를 받아 글을 쓰는 모델이 아니라 `state`+`questions` → 선택지·확률을 돌려주는 API이고, 역할 분리 원칙(Jev는 판정만)을 타입으로 강제 |
| 2026-10-13 | 기본값은 `ROUTER_MODE=rules`, `JUDGE_PROVIDER=mock`. `JevProvider`는 서드파티 문서 기반이며 실호출 미검증 | Jev 접근 권한 여부 불명, 실수로 인한 호출 방지. 접근이 승인되면 `scripts/smoke_live.py --target jev`로 1회 확인 후 이 행을 갱신 |
| 2026-10-13 | 판정 정책을 `state`에 포함하고 `POLICY_VERSION`을 모든 `judge` 이벤트에 기록 (`docs/prompts/router-policy-v1.md`) | CLAUDE.md 원칙(판단 근거 정책은 입력에 포함)과 평가 재현성 |
| 2026-10-13 | Docker는 0~2단계에서 사용하지 않음. PostgreSQL·Qdrant 도입 시점(3단계 전후)에 docker compose 도입을 다시 검토 | 지금은 SQLite·mock으로 충분하고 로컬에 Docker가 없음. vLLM은 Windows 네이티브가 안 되어 WSL2 또는 Docker가 필요하며 GPU 사양 확인 후 결정 |
