## 무엇을 바꿨나

<!-- 변경 내용과 이유를 짧게 적는다. 관련 이슈가 있으면 `Closes #번호` -->

## 어떻게 확인했나

<!-- 실행한 명령과 결과를 적는다. 직접 확인하지 못한 것은 확인하지 못했다고 적는다. -->

- [ ] `uv run pytest`, `uv run ruff check . && uv run ruff format --check .` (code/backend)
- [ ] `npm run typecheck`, `npm test`, `npm run build` (code/frontend, 화면을 바꾼 경우)

## 체크리스트

- [ ] 동작이 바뀌면 문서(README, docs/)를 갱신했다
- [ ] 구조나 기술 선택을 바꿨다면 `docs/architecture.md`의 결정 기록에 한 줄을 추가했다
- [ ] 새 환경변수는 값 없이 `code/backend/.env.example`에도 추가했다
- [ ] 새 의존성은 이유를 한 줄로 적었다
- [ ] 비밀, 개인정보, 대용량 데이터가 들어 있지 않다
