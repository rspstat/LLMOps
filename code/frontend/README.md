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

## 화면과 동작

질문을 보내면 경로·사유·`p(easy)`·모델·토큰·비용·아낀 금액·지연이 한 화면에 보인다. 게이트웨이가 빌드 결과를 `/`로 서빙하며, 키는 화면의 입력칸에 넣는다(저장되지 않는다).

- `p(easy)`는 `ROUTER_MODE=hybrid`(또는 `judge_only`)에서 판정기를 거친 요청에만 표시된다. 실제 Jev로 보려면 `JUDGE_PROVIDER=jev`와 `JEV_API_KEY`가 필요하다. 기본 정책(v2a)에서는 기본 임계값 0.7이 의미 있는 값이다.
- 화면을 끄려면 `WEB_UI_ENABLED=false`(API만 동작). 빌드하지 않으면 `/`는 빌드 안내와 함께 503을 돌려준다.
- 이력 표는 이번 접속에서 보낸 요청만 보여 주며 서버에 저장하지 않는다.
- **아낀 금액**: 모든 요청을 상용 모델로만 보냈다면 들었을 비용에서 실제 비용(판정 비용 포함)을 뺀 값이다. 같은 토큰 수로 계산한 추정치이고, 판정 비용이 큰 짧은 요청에서는 음수가 될 수 있다.
- **라이트/다크 모드**: 처음에는 OS 설정을 따르고, 오른쪽 위 토글로 바꾼다(선택은 이 브라우저에만 기억).
- **애니메이션**: 요청이 `입력 가드 → 라우터 → 모델 → 응답`을 지나는 과정, 답변 타이핑, `p(easy)` 게이지, 숫자 카운트업 등. OS에서 "동작 줄이기"를 켜 두면 모두 꺼진다.

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
