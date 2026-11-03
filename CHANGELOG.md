# 변경 내역

[Keep a Changelog](https://keepachangelog.com/ko/1.1.0/) 형식을 따른다. 아직 릴리스(태그)가 없어서 모든 변경이 `Unreleased`에 있고, 날짜는 커밋 기준이다.

## [Unreleased]

### 추가

- **게이트웨이** (2026-10-13): OpenAI 호환 `POST /v1/chat/completions`(비스트리밍), Bearer 인증, 서버가 만드는 요청 ID(`X-Request-ID`), `GET /healthz`.
- **입력 가드**: 빈 입력, 길이 초과, 영어·한국어 프롬프트 인젝션 규칙. 응답에는 범주만 알린다.
- **라우팅**: 규칙 라우터, 판정기(Jev) 기반 `hybrid`/`judge_only` 라우터와 신뢰도 임계값 승격, 판정 실패 시 규칙 결과로 대체.
- **provider 추상화**: mock, OpenAI 호환(요청 파라미터 자동 적응, 모델별 추가 필드), Jev 어댑터.
- **장애 대체**: 고른 모델이 실패하면 다른 경로의 실제 모델이 대신 답하고, 모두 실패하면 502.
- **trace**: 단계별(가드, 판정, 라우팅, 모델 호출) 판정·토큰·비용·지연을 SQLite에 기록. 프롬프트 본문은 기본으로 저장하지 않는다.
- **응답 헤더**: `X-LLMOps-Route`, `-Fallback`, `-Route-Reason`, `-P-Easy`, `-Cost-USD`, `-Baseline-Cost-USD`.
- **평가 도구** (`python -m evals.run`): `validate`/`collect`/`report`/`check`. 캐시 재생으로 임계값별 비교, 신뢰구간, 판정기 정밀도·재현율, 예산·단가 가드, 비밀을 보여 주지 않는 설정 점검.
- **데이터셋**: `routing_v1` 80문항과 동결한 보류 데이터 `routing_v1_holdout` 60문항(영어·한국어).
- **판정 정책 버전 관리** (2026-10-19): 정책 v1, v2a, v2b를 해시로 고정해 등록하고 `ROUTER_POLICY`와 `collect --policy`로 선택. 검증 결과는 [docs/evals/2026-10-19_policy-v2.md](docs/evals/2026-10-19_policy-v2.md).
- **웹 화면** (2026-10-13~11-03): React + Vite + TypeScript. 요청이 지나간 단계 애니메이션, 결과 카드, 이력 표, 라이트/다크 모드, 모바일 폭 지원, 상용만 썼을 때 대비 **아낀 금액** 표시.
- **Docker 실행 파일** (2026-11-03): `Dockerfile`, `compose.yaml`, `.dockerignore`. 작성 환경에 Docker가 없어 이미지 빌드는 직접 실행해 보지 못했다.
- **오픈소스 저장소 문서**: LICENSE(MIT), CONTRIBUTING, SECURITY, CHANGELOG, 문서 색인, 이슈·PR 템플릿.

### 변경

- 기본 판정 정책을 v1에서 **v2a**로 바꿨다(2026-11-03). v1은 `ROUTER_POLICY=v1`로 재현할 수 있다.
- 모든 오류 응답을 OpenAI 오류 형식 `{"error": {message, type, param, code}}`로 통일했다(401, 404, 405, 422, 500 포함).
- 저장소를 `code/backend`와 `code/frontend`로 나눴다.
- 웹 화면을 `/`에서 서빙한다. 환경변수는 `WEB_UI_ENABLED`이다. 이전의 `/demo`와 `DEMO_UI_ENABLED`는 별칭 없이 제거되었다.
- 문서 문체를 "~이다/~한다"로 통일했다.
- README를 80줄 안팎으로 줄였다. 라우팅 모드, 웹 화면, 응답 헤더 전체, 오류 형식 등 세부 내용은 모듈별 README와 `docs/architecture.md`로 옮겼다.

### 수정

- 클라이언트가 보낸 요청 ID를 trace 키로 쓰던 결함을 고쳤다. 서버가 항상 새 ID를 만들고 클라이언트 값은 상관관계용으로만 기록한다.
- 프롬프트를 그대로 따라 말하는 응답과 선택지를 나열하는 얼버무림이 정답으로 채점되던 구멍을 닫았다.
- 설정 검증 오류가 `.env`의 API 키를 그대로 출력하던 문제를 고쳤다.
- 리포트가 모델 엔드포인트의 계정·워크스페이스 ID를 그대로 보여 주던 문제를 고쳤다.
- 모델 호출이 실패하면 질문을 따라 말하는 가짜 응답이 HTTP 200으로 나가던 문제를 고쳤다(아래 "제거").

### 제거

- 운영 응답의 대체 수단으로 쓰이던 mock fallback.
- 과거 대회 제출용 문서와 대화 기록(`docs/contest/`, `docs/ai-log/`).
