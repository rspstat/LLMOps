# router

라우팅 엔진. 요청마다 소형 모델과 상용 모델 중 무엇으로 보낼지 정한다. 모드와 승격 규칙, `reason` 값은 [docs/architecture.md §3](../../../docs/architecture.md), 정책 문구의 모든 버전은 [docs/prompts/router-policy.md](../../../docs/prompts/router-policy.md)에 있다.

## 모드

`.env`의 `ROUTER_MODE`로 고른다. 기본값 `rules`는 규칙만 쓰고 판정기를 호출하지 않는다.

| 모드 | 동작 |
|---|---|
| `rules` | 길이·키워드 규칙만 (기본) |
| `hybrid` | 규칙에 걸리면 확정, 아니면 판정기(Jev)가 easy/hard와 확률을 판정. `p(easy) ≥ ROUTER_PROMOTE_THRESHOLD`(0.7)일 때만 소형 모델, 아니면 상용 모델로 승격 |
| `judge_only` | 항상 판정기에 질의 (규칙과 비교 실험용) |

## 판정 정책

판정기에 보내는 정책 문구는 `ROUTER_POLICY`로 고르며 기본은 `v2a`이다. v1은 Jev가 거의 모든 요청에 `easy`를 높은 확률로 답해 기본 임계값 0.7이 구분력을 잃었고, v2a는 "정답에 필요한 의존 단계 수"를 묻는다. 비교와 한계는 [정책 v2 검증](../../../docs/evals/2026-10-19_policy-v2.md)에 있다. 2026-10-13 측정을 재현하려면 `ROUTER_POLICY=v1`(평가 도구는 `--policy v1`)을 쓴다.

## 판정기

`JUDGE_PROVIDER`의 기본값은 오프라인 mock(요청 길이만 보는 가짜)이라 키 없이 동작을 볼 수 있지만, 라우팅 품질의 근거는 아니다. 실제 Jev는 `JUDGE_PROVIDER=jev`와 `JEV_API_KEY`가 필요하며, 어댑터는 서드파티 문서를 기준으로 작성했고 2026-10-13에 실제 호출로 확인했다. 판정 호출은 trace에 `judge` 이벤트(확률, 토큰, 비용, 지연, 정책 버전)로 남는다.
