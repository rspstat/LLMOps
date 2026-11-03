# 백엔드 (`code/backend`)

FastAPI 게이트웨이와 라우팅 평가 도구이다. 프로젝트 전체 소개는 [루트 README](../../README.md)에 있고, 이 문서는 백엔드를 개발할 때 쓰는 안내이다.

## 실행

```bash
cd code/backend
uv sync                                  # 의존성 설치 (.venv 생성)
cp .env.example .env                     # PowerShell: Copy-Item .env.example .env
                                         # GATEWAY_API_KEY 에 임의의 긴 문자열을 채운다
uv run uvicorn gateway.app:create_app --factory --port 8000
```

설정은 환경변수나 이 폴더의 `.env`에서 읽는다. 항목과 설명은 [`.env.example`](.env.example)에 있고, `uv run python -m evals.run check`가 `.env`가 실제로 무엇을 켜는지 값 없이 보여 준다. 기본값은 모두 오프라인 mock이라 키 없이 시작할 수 있다.

웹 화면(`../frontend`)을 빌드해 두면 같은 서버가 `/`에서 서빙한다. 빌드하지 않아도 API는 동작한다.

## 동작

- 응답 헤더 `X-Request-ID`가 trace의 키이다. 기본 저장소는 `data/traces.sqlite3`(SQLite, 커밋되지 않음)이며 단계별(`guard` → `router` → `provider`) 판정·토큰·비용·지연이 기록된다.
- 입력 가드가 막으면 400이다. 라우팅된 모델이 실패하면 다른 경로의 실제 모델이 대신 답하고(응답 헤더 `X-LLMOps-Fallback: true`, trace에 기록), 모두 실패하면 502이다.
- 실제 모델 연결은 `.env`의 `SMALL_PROVIDER` / `FRONTIER_PROVIDER` / `JUDGE_PROVIDER`로 켠다([라우터 문서](router/README.md)).

## 개발

```bash
uv run pytest                                        # 테스트 (전부 mock, 네트워크 없음)
uv run ruff check . && uv run ruff format --check .  # 린트와 포맷 검사
```

- 테스트는 `Settings(_env_file=None)`로 `.env`를 읽지 않고, trace DB는 임시 폴더에 만든다.
- 외부 모델을 실제로 부르는 것은 `scripts/smoke_live.py`와 `evals.run collect`뿐이고, `ALLOW_LIVE_CALLS=1`을 켜야만 실행된다(비용이 든다).

## 구조

| 폴더 | 역할 |
|---|---|
| [`gateway/`](gateway/README.md) | FastAPI 앱, 라우트, 인증, 오류 형식, trace 저장, 웹 화면 서빙 |
| [`guards/`](guards/README.md) | 입력 가드 |
| [`router/`](router/README.md) | 규칙 라우터, 하이브리드 라우터, 판정 정책(`policy.py`) |
| [`providers/`](providers/README.md) | provider 인터페이스, mock, OpenAI 호환, Jev |
| [`evals/`](evals/README.md) | 데이터셋, 채점, 수집·재생·리포트, 설정 점검 |
| `scripts/` | 실제 모델을 한 번 호출해 확인하는 스모크 스크립트 |
| `tests/` | 테스트 |

요청 한 건의 흐름은 [docs/architecture.md](../../docs/architecture.md)의 "요청 흐름"에 있다.
