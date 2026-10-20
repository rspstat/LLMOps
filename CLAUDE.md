# LLMOps — Claude Code 작업 가이드

## 프로젝트

FastAPI 기반 **LLM 게이트웨이**: 입력 가드 → 라우팅 엔진 → 모델 호출 → 출력 가드, 전 단계 trace 기록, 설정 변경 시 자동 평가.
라우팅 대상은 코드 규칙 · Jev · 소형 오픈소스 모델(HF Transformers/vLLM) · 상용 API LLM.
상세 구조와 로드맵은 `README.md`, 설계 결정은 `docs/architecture.md`를 따른다.

## 우선순위

"화려하게 많이 만들기"보다 **끝까지 동작하는 한 줄 관통 + 개선·디버깅 과정의 기록**을 우선한다.

## 아키텍처 원칙

- **역할 분리**: 계산은 코드, 선택지가 정해진 판정(분류·yes/no+확률·점수)은 Jev, 쉬운 질의 생성은 소형 오픈소스 모델, 어려운 추론·긴 생성은 상용 API.
- Jev는 글쓰기·깊은 추론·산술에 쓰지 않는다. 판단 근거가 되는 정책은 반드시 입력(state)에 포함한다.
- **provider 추상화**: 모든 모델 호출은 `providers/`의 공통 인터페이스 뒤에 둔다. Jev 접근 권한이 없거나 장애여도 시스템이 동작해야 하므로, 판정기는 규칙 결과로 대체하고 모델 호출은 다른 경로의 실제 모델로 대체한다. mock은 개발·테스트 모드에서만 쓰고 운영 응답의 대체 수단으로 쓰지 않는다.
- 모든 단계(가드 판정, 라우팅 결정, 모델 호출)는 요청 ID와 함께 trace로 남긴다: 선택된 경로, 판정 확률, 토큰, 비용, 지연.
- 라우팅·가드의 임계값은 코드에 하드코딩하지 말고 설정으로 분리한다 (평가 모듈이 값을 바꿔 가며 측정하기 때문).

## 기술 스택

- Python 3.11+, FastAPI, Pydantic v2, pytest, ruff
- 웹 화면: React + Vite + TypeScript, vitest (`code/frontend`). 의존성은 `package.json`/`package-lock.json`으로 관리한다.
- 저장소: PostgreSQL(+pgvector 또는 Qdrant) 예정. 확정되면 `docs/architecture.md`의 결정 기록에 남긴다.
- 의존성은 `pyproject.toml`로 관리하고 꼭 필요한 것만 추가한다. 새 의존성을 추가할 땐 이유를 한 줄로 설명한다.

## 명령어

> 새 명령이 생기면 **즉시 이 섹션을 갱신**한다. 실행해 본 적 없는 명령을 추측해서 적지 않는다.

Python은 uv로 관리한다 (`.python-version` = 3.12, `uv.lock` 커밋). 백엔드 코드는 `code/backend/`, 프런트엔드는 `code/frontend/`, 문서는 루트의 `docs/`에 둔다. 아래 Python 명령은 모두 `code/backend/`에서 실행하고, `.env`·`.venv`·`data/`·`evals/cache`도 그 폴더 아래에 있다.

```bash
cd code/backend                                           # 이하 Python 명령은 여기서 실행
uv sync                                                   # 환경 생성/동기화
uv run pytest                                             # 테스트 (전부 mock, 네트워크 없음)
uv run ruff check . && uv run ruff format --check .       # 린트 + 포맷 검사
uv run uvicorn gateway.app:create_app --factory --port 8000   # 게이트웨이 실행 (.env 필요)

# 실제 모델 1회 호출 — 비용 발생. 내가 요청할 때만 실행한다.
ALLOW_LIVE_CALLS=1 uv run python -m scripts.smoke_live --target slm   # 또는 frontier, jev
```

- `--target jev`는 실제 라우팅 질문(easy/hard)을 Jev에 1회 보낸다. 2026-10-13에 실제로 실행해 어댑터가 맞는 것을 확인했다.

```bash
# 라우팅 평가 (code/backend/evals/README.md)
uv run python -m evals.run validate                         # 데이터셋 검사
uv run python -m evals.run collect --name sample --limit 20   # 기본 mock, 호출 없음
uv run python -m evals.run report  --name sample            # code/backend/evals/reports/sample/report.md
uv run python -m evals.run collect --name real --dry-run    # 실제 provider: 예상 호출 수·비용 상한만 출력
# 실호출 수집 — 비용 발생. 내가 요청할 때만 실행한다 (ALLOW_LIVE_CALLS=1 과 --budget-usd 필수).
ALLOW_LIVE_CALLS=1 uv run python -m evals.run collect --name real --budget-usd 0.25
```

- `uv run python -m evals.run check`는 `.env`가 실제로 무엇을 켜는지(provider 스위치, 키 유무, 단가, 오타 난 변수)를 값 없이 보여 준다. `.env` 확인은 이 명령으로 한다.
- 모델 선택 근거와 단가 비교: `docs/api-pricing-2026-10.md`.
- 실호출 전에 `.env`에 모델명·키·**단가**(`*_PRICE_*`)가 필요하다. 과금되는 모델에 단가가 없으면 수집이 거부된다. 항목과 실행 순서는 `code/backend/evals/README.md`의 "실측" 절. `.env`는 내가 읽지 않고, 확인은 `collect --dry-run`(키를 출력하지 않음)으로 한다.
- 소형 모델이 호스팅 API이면 `SLM_API_KEY`를 채운다 (자체 서빙이면 비움).
- 라우팅 모드는 `ROUTER_MODE`(rules | hybrid | judge_only), 판정기는 `JUDGE_PROVIDER`(mock | jev). 기본은 `rules` + `mock`이라 외부 호출이 없다.

웹 화면(`code/frontend`)은 npm으로 관리한다. 게이트웨이가 빌드 결과를 `/`로 서빙한다(`WEB_UI_ENABLED`).

```bash
cd code/frontend
npm ci            # 의존성 설치
npm run typecheck # 타입 검사 (tsc --noEmit)
npm test          # 단위 테스트 (vitest)
npm run build     # code/frontend/dist 생성
npm run dev       # 개발 서버 http://localhost:5173/ (API는 8000 포트로 프록시)
```

- Windows PowerShell에서는 `$env:ALLOW_LIVE_CALLS = "1"; uv run python -m scripts.smoke_live --target slm`.
- provider 기본값은 mock이라 `.env`에 키가 있어도 `SMALL_PROVIDER` / `FRONTIER_PROVIDER`를 바꾸기 전에는 외부 호출이 없다.
- 테스트는 `Settings(_env_file=None)`로 `.env`를 읽지 않고, trace DB는 `tmp_path`에 만든다.

## 작업 방식

- 사소하지 않은 작업은 **구현 전에 계획을 먼저 제시**하고 승인을 받는다.
- 한 번에 작은 단위로 진행하고, 변경 후에는 테스트·린트를 실제로 실행해 결과를 확인한다. 실패하면 숨기지 말고 원인과 함께 보고한다.
- 현재 단계는 README 로드맵의 **3단계(평가 v1)까지 도구 구현 완료, 다음은 4단계(가드 고도화)**다. 평가는 2026-10-13에 Qwen + Jev로 첫 실측을 했다(`docs/evals/2026-10-13_qwen-first-run.md`, n=80, 라벨 검토 전이라 관찰로 읽을 것).
- 외부 API(Jev, 상용 LLM)를 실제로 호출하면 비용이 든다. 테스트는 기본적으로 mock을 쓰고, 실제 호출은 내가 요청할 때만 한다.
- 파인튜닝은 GPU 제약상 1B 이하 모델 위주로 설계한다.

## Git 규칙

- 작은 단위로 자주 커밋한다. 메시지는 Conventional Commits 형식(`feat:`, `fix:`, `docs:`, `chore:`, `test:`)의 영어 한 줄.
- `git push`는 내가 요청할 때만 한다.
- 이 레포는 **Public**이다. 커밋 전 `git status`와 `git diff --staged`로 비밀키·개인정보가 없는지 확인한다.

## 보안

- `.env`는 읽거나 출력하거나 커밋하지 않는다. 새 환경변수를 추가하면 값 없이 `.env.example`에도 추가한다.
- 모델 가중치, 대용량 데이터, 체크포인트는 커밋하지 않는다 (`.gitignore` 참고).
- 학교 비공개 자료나 개인정보를 데이터셋·테스트에 넣지 않는다.

## 기록 규칙 (놓치기 쉬우므로 꼭 지킨다)

- **트러블슈팅**: 의미 있는 오류를 해결하면 `docs/troubleshooting/YYYY-MM-DD_제목.md`에 *증상 → 원인 → 시도한 것 → 해결 → 배운 점*을 기록한다. 작업이 끝날 때 초안을 먼저 제안한다.
- **프롬프트 개선**: 프롬프트를 고쳤다면 이전/이후 버전과 바꾼 이유를 `docs/prompts/`에 남긴다.
- **결정**: 구조나 기술 선택을 바꾸면 `docs/architecture.md`의 결정 기록 표에 한 줄 추가한다.

## 언어

- 나와의 대화와 문서는 한국어로, 코드 식별자·주석·커밋 메시지는 영어로 쓴다.
