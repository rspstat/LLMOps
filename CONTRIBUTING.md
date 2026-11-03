# 기여 안내

이 프로젝트에 관심을 가져 주어 고맙다. 버그 제보, 문서 수정, 기능 제안, 코드 기여 모두 환영한다.

## 시작하기

필요한 것: [uv](https://docs.astral.sh/uv/)(Python 3.12는 uv가 자동으로 받는다)와 Node.js(웹 화면 작업 시).

```bash
git clone https://github.com/rspstat/LLMOps.git
cd LLMOps/code/backend
uv sync                                  # 백엔드 의존성 설치
cp .env.example .env                     # 테스트에는 키가 필요 없다. 기본값은 모두 오프라인 mock이다
                                         # (게이트웨이를 직접 띄울 때만 GATEWAY_API_KEY 를 채운다)
uv run pytest                            # 테스트 (네트워크 없음)
uv run ruff check . && uv run ruff format --check .   # 린트와 포맷 검사

cd ../frontend
npm ci                                   # 웹 화면 의존성 설치
npm run typecheck && npm test            # 타입 검사와 단위 테스트
npm run build                            # 게이트웨이가 / 로 서빙하는 dist 생성
```

저장소 구조는 [README](README.md)의 "디렉터리 구조", 설계 결정은 [docs/architecture.md](docs/architecture.md)를 본다.

## 기여 흐름

1. 큰 변경은 먼저 이슈로 방향을 맞춘다. 작은 수정은 바로 PR을 열어도 된다.
2. 작은 단위로 변경하고 테스트를 함께 추가한다. 버그 수정에는 그 버그를 재현하는 테스트를 넣는다.
3. PR을 열기 전에 위 테스트·린트 명령을 실행하고 결과를 확인한다.
4. 실패하는 것이 있으면 숨기지 말고 원인과 함께 PR에 적는다.

## 커밋 메시지

[Conventional Commits](https://www.conventionalcommits.org/) 형식의 영어 한 줄이다: `feat:`, `fix:`, `docs:`, `refactor:`, `chore:`, `test:`.

## 기록 규칙

이 프로젝트는 "무엇을 바꿨는가"뿐 아니라 "왜 그랬고 어떻게 틀렸는가"를 문서로 남긴다.

- **결정**: 구조나 기술 선택을 바꾸면 [docs/architecture.md](docs/architecture.md)의 결정 기록 표에 한 줄을 추가한다.
- **프롬프트·정책 문구**: 판정 정책을 고치면 기존 버전을 수정하지 말고 새 버전을 등록하고(`router/policy.py`, 문구는 해시 테스트로 고정되어 있다), 이전/이후와 이유를 [docs/prompts/router-policy.md](docs/prompts/router-policy.md)에 남긴다.
- **트러블슈팅**: 의미 있는 오류를 해결하면 `docs/troubleshooting/YYYY-MM-DD_제목.md`에 증상 → 원인 → 시도한 것 → 해결 → 배운 점을 적는다.
- **측정 결과**: 평가 결과는 한계(표본 크기, 라벨 상태, 확인하지 못한 것)와 함께 `docs/evals/`에 적는다. 결과를 보기 전에 판정 규칙을 정해 두면 가장 믿을 만하다.

## 외부 API 호출과 비밀

- 테스트는 mock만 쓴다. 실제 모델 호출은 비용이 들기 때문에 `ALLOW_LIVE_CALLS=1`을 켜야만 실행되고, 평가 수집에는 `--budget-usd`가 반드시 필요하다.
- `.env`와 API 키는 절대 커밋하지 않는다. 새 환경변수를 추가하면 값 없이 `code/backend/.env.example`에도 추가한다.
- 평가 데이터에 개인정보나 비공개 자료를 넣지 않는다.
- 커밋 전에 `git status`와 `git diff --staged`로 비밀이 섞이지 않았는지 확인한다.

## 코드와 문서 스타일

- 코드 식별자, 주석, 커밋 메시지는 영어로 쓴다. 문서는 한국어로 쓰고 "~이다/~한다" 체를 쓴다.
- 모든 모델 호출은 `providers/`의 공통 인터페이스 뒤에 둔다. 임계값은 코드에 하드코딩하지 않고 설정으로 분리한다.
- 새 의존성은 꼭 필요한 것만 추가하고, PR 설명에 이유를 한 줄로 적는다.
- Python은 ruff(줄 길이 100), 웹 화면은 TypeScript strict 모드를 따른다.

## PR 체크리스트

- [ ] 테스트와 린트가 통과한다 (백엔드 `uv run pytest`, `ruff`, 프런트엔드 `npm test`, `npm run build`)
- [ ] 동작이 바뀌면 문서(README, docs/)와 필요하면 결정 기록을 갱신했다
- [ ] 비밀, 개인정보, 대용량 데이터가 들어 있지 않다
- [ ] 직접 확인하지 못한 것은 확인하지 못했다고 적었다

## 라이선스

기여한 내용은 이 저장소와 같은 [MIT License](LICENSE)로 배포된다.
