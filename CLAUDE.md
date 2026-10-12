# LLMOps — Claude Code 작업 가이드

## 프로젝트

FastAPI 기반 **LLM 게이트웨이**: 입력 가드 → 라우팅 엔진 → 모델 호출 → 출력 가드, 전 단계 trace 기록, 설정 변경 시 자동 평가.
라우팅 대상은 코드 규칙 · Jev · 소형 오픈소스 모델(HF Transformers/vLLM) · 상용 API LLM.
상세 구조와 로드맵은 `README.md`, 설계 결정은 `docs/architecture.md`를 따른다.

## 대회 맥락 (판단 기준)

2026-2학기 충북대 SW학부 CUVIC 바이브 코딩 대회 출품작이다.

- 중간발표: 11/5(목) 19:00 예정(조율 중), 5~7분. 구성: 프로젝트 기획안 / AI 워크플로우·환경 설정 / 초기 프롬프트 전략 / 향후 계획
- 최종발표: 12월 말 예정, 7~10분
- 최종 평가 비중: 프롬프팅·트러블슈팅 40% · 결과물 완성도(핵심 기능이 작동하는 프로토타입) 30% · 경험과 성장 20% · 발표 10%
- 제출물: 중간발표 PPT와 함께 **AI chat log**와 **GitHub 링크**

따라서 "화려하게 많이 만들기"보다 **끝까지 동작하는 한 줄 관통 + 개선·디버깅 과정의 기록**을 우선한다.

## 아키텍처 원칙

- **역할 분리**: 계산은 코드, 선택지가 정해진 판정(분류·yes/no+확률·점수)은 Jev, 쉬운 질의 생성은 소형 오픈소스 모델, 어려운 추론·긴 생성은 상용 API.
- Jev는 글쓰기·깊은 추론·산술에 쓰지 않는다. 판단 근거가 되는 정책은 반드시 입력(state)에 포함한다.
- **provider 추상화**: 모든 모델 호출은 `providers/`의 공통 인터페이스 뒤에 둔다. Jev 접근 권한이 없거나 장애여도 시스템이 동작해야 하므로 mock/오픈소스 fallback을 항상 유지한다.
- 모든 단계(가드 판정, 라우팅 결정, 모델 호출)는 요청 ID와 함께 trace로 남긴다: 선택된 경로, 판정 확률, 토큰, 비용, 지연.
- 라우팅·가드의 임계값은 코드에 하드코딩하지 말고 설정으로 분리한다 (평가 모듈이 값을 바꿔 가며 측정하기 때문).

## 기술 스택

- Python 3.11+, FastAPI, Pydantic v2, pytest, ruff
- 저장소: PostgreSQL(+pgvector 또는 Qdrant) 예정. 확정되면 `docs/architecture.md`의 결정 기록에 남긴다.
- 의존성은 `pyproject.toml`로 관리하고 꼭 필요한 것만 추가한다. 새 의존성을 추가할 땐 이유를 한 줄로 설명한다.

## 명령어

> 새 명령이 생기면 **즉시 이 섹션을 갱신**한다. 실행해 본 적 없는 명령을 추측해서 적지 않는다.

Python은 uv로 관리한다 (`.python-version` = 3.12, `uv.lock` 커밋).

```bash
uv sync                                                   # 환경 생성/동기화
uv run pytest                                             # 테스트 (전부 mock, 네트워크 없음)
uv run ruff check . && uv run ruff format --check .       # 린트 + 포맷 검사
uv run uvicorn gateway.app:create_app --factory --port 8000   # 게이트웨이 실행 (.env 필요)

# 실제 모델 1회 호출 — 비용 발생. 내가 요청할 때만 실행한다.
ALLOW_LIVE_CALLS=1 uv run python -m scripts.smoke_live --target slm   # 또는 frontier, jev
```

- `--target jev`는 실제 라우팅 질문(easy/hard)을 Jev에 1회 보낸다. 아직 한 번도 실행하지 않았다(접근 권한·키 없음).

```bash
# 라우팅 평가 (evals/README.md)
uv run python -m evals.run validate                         # 데이터셋 검사
uv run python -m evals.run collect --name demo --limit 20   # 기본 mock, 호출 없음
uv run python -m evals.run report  --name demo              # evals/reports/demo/report.md
uv run python -m evals.run collect --name real --dry-run    # 실제 provider: 예상 호출 수·비용 상한만 출력
# 실호출 수집 — 비용 발생. 내가 요청할 때만 실행한다 (ALLOW_LIVE_CALLS=1 과 --budget-usd 필수).
ALLOW_LIVE_CALLS=1 uv run python -m evals.run collect --name real --budget-usd 0.25
```

- `uv run python -m evals.run check`는 `.env`가 실제로 무엇을 켜는지(provider 스위치, 키 유무, 단가, 오타 난 변수)를 값 없이 보여 준다. `.env` 확인은 이 명령으로 한다.
- 모델 선택 근거와 단가 비교: `docs/api-pricing-2026-10.md`.
- 실호출 전에 `.env`에 모델명·키·**단가**(`*_PRICE_*`)가 필요하다. 과금되는 모델에 단가가 없으면 수집이 거부된다. 항목과 실행 순서는 `evals/README.md`의 "실측" 절. `.env`는 내가 읽지 않고, 확인은 `collect --dry-run`(키를 출력하지 않음)으로 한다.
- 소형 모델이 호스팅 API이면 `SLM_API_KEY`를 채운다 (자체 서빙이면 비움).
- 라우팅 모드는 `ROUTER_MODE`(rules | hybrid | judge_only), 판정기는 `JUDGE_PROVIDER`(mock | jev). 기본은 `rules` + `mock`이라 외부 호출이 없다.

- Windows PowerShell에서는 `$env:ALLOW_LIVE_CALLS = "1"; uv run python -m scripts.smoke_live --target slm`.
- provider 기본값은 mock이라 `.env`에 키가 있어도 `SMALL_PROVIDER` / `FRONTIER_PROVIDER`를 바꾸기 전에는 외부 호출이 없다.
- 테스트는 `Settings(_env_file=None)`로 `.env`를 읽지 않고, trace DB는 `tmp_path`에 만든다.

## 작업 방식

- 사소하지 않은 작업은 **구현 전에 계획을 먼저 제시**하고 승인을 받는다.
- 한 번에 작은 단위로 진행하고, 변경 후에는 테스트·린트를 실제로 실행해 결과를 확인한다. 실패하면 숨기지 말고 원인과 함께 보고한다.
- 현재 단계는 README 로드맵의 **3단계(평가 v1)까지 도구 구현 완료, 다음은 4단계(가드 고도화)**다. 단, 평가는 mock으로만 검증했고 **실제 모델·Jev 수치는 아직 없다**(키·접근 권한 대기). 로드맵 밖의 기능은 추가하지 않는다.
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

## 대회용 기록 (놓치기 쉬우므로 꼭 지킨다)

- **트러블슈팅**: 의미 있는 오류를 해결하면 `docs/troubleshooting/YYYY-MM-DD_제목.md`에 *증상 → 원인 → 시도한 것 → 해결 → 배운 점*을 기록한다. 작업이 끝날 때 초안을 먼저 제안한다.
- **프롬프트 개선**: 프롬프트를 고쳤다면 이전/이후 버전과 바꾼 이유를 `docs/prompts/`에 남긴다.
- **결정**: 구조나 기술 선택을 바꾸면 `docs/architecture.md`의 결정 기록 표에 한 줄 추가한다.
- **AI 대화 기록**: 세션을 마치기 전에 `/export docs/ai-log/YYYY-MM-DD_주제.md`로 저장하자고 상기시켜 준다. 저장 후 키·개인정보가 섞였는지 확인해야 한다.

## 언어

- 나와의 대화와 문서는 한국어로, 코드 식별자·주석·커밋 메시지는 영어로 쓴다.
