# 웹 화면 (`code/frontend`)

게이트웨이의 요청과 결과를 보여 주는 React + Vite + TypeScript 앱이다. 프로젝트 전체 소개는 [루트 README](../../README.md)에 있다.

## 명령

```bash
cd code/frontend
npm ci            # 의존성 설치
npm run dev       # 개발 서버 http://localhost:5173/ (API는 localhost:8000의 게이트웨이로 프록시)
npm run typecheck # 타입 검사 (tsc --noEmit)
npm test          # 단위 테스트 (vitest)
npm run build     # dist 생성 (게이트웨이가 / 로 서빙)
```

개발 서버를 쓸 때는 게이트웨이(`code/backend`)를 8000 포트로 함께 띄운다. 화면에서 게이트웨이 키(`GATEWAY_API_KEY`)를 입력해 요청을 보낸다.

## 구조

| 경로 | 역할 |
|---|---|
| `src/api.ts` | `/v1/chat/completions` 호출과 응답 헤더(`X-LLMOps-*`) 해석. 예외를 던지지 않고 실패도 값으로 돌려준다 |
| `src/summary.ts` | 이번 접속의 요청 요약과 아낀 금액 계산 |
| `src/pipeline.ts` | 요청이 지나간 단계(가드, 라우터, 모델, 응답)의 상태 계산 |
| `src/motion.ts`, `src/hooks/` | 카운트업, 타이핑, 테마, 동작 줄이기 처리 |
| `src/components/` | 화면 컴포넌트 |
| `src/style.css` | 라이트/다크 테마 변수, 애니메이션 |
| `public/theme-init.js` | 첫 화면이 깜빡이지 않도록 먼저 실행되는 테마 스크립트 |

순수 로직(`api`, `summary`, `pipeline`, `motion`, `theme`)은 vitest로 테스트한다. 컴포넌트 렌더링 테스트 라이브러리는 쓰지 않는다.

## 보안과 접근성

- 게이트웨이 키는 React 상태에만 두고 저장소나 URL에 남기지 않는다.
- 모델 출력과 오류 메시지는 텍스트로만 렌더링한다(`dangerouslySetInnerHTML`을 쓰지 않는다).
- 게이트웨이가 엄격한 Content-Security-Policy(인라인 스크립트·스타일 금지)로 서빙하므로 HTML에 인라인 `<script>`나 `style="..."`를 직접 쓰지 않는다. 테마 스크립트가 별도 파일인 이유이다. React의 `style` 속성 객체는 자바스크립트가 적용하므로 쓸 수 있다.
- OS의 "동작 줄이기" 설정이 켜져 있으면 CSS와 JS 애니메이션을 모두 끈다.
