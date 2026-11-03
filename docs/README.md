# 문서 색인

| 문서 | 내용 |
|---|---|
| [product.md](product.md) | 이 서비스가 무엇을 제공하는지: 기능 요구사항(FR-1~17)과 구현 상태, 범위 밖, 성공 기준, 용어 |
| [architecture.md](architecture.md) | 요청 흐름, 구성 요소, trace 스키마, 평가 설계, **결정 기록 표**(날짜순, 근거 포함) |
| [api-pricing-2026-10.md](api-pricing-2026-10.md) | 소형·상용 모델과 판정기를 고르기 위한 2026년 10월 API 가격 비교와 권장 조합 |
| [prompts/router-policy.md](prompts/router-policy.md) | 판정 정책 문구의 모든 버전(v1, v2a, v2b), 바꾼 이유, 검증 규칙, 기본 정책 결정 |

## 평가 보고서 (`evals/`)

| 보고서 | 내용 |
|---|---|
| [2026-10-13_qwen-first-run.md](evals/2026-10-13_qwen-first-run.md) | 첫 실측: Qwen + Jev, 80문항. 소형 모델 91%, 상용 97.5%, 임계값별 비교 |
| [2026-10-13_gateway-live-run.md](evals/2026-10-13_gateway-live-run.md) | 게이트웨이 서버를 실제 모델로 켜서 확인, 발견한 문제와 수정, 웹 화면과 장애 대체 재확인 |
| [2026-10-19_policy-v2.md](evals/2026-10-19_policy-v2.md) | 판정 정책 v2 검증: 개발용 80문항 + 동결한 보류 60문항, 사전 등록한 규칙과 그 허점 |

## 트러블슈팅 기록 (`troubleshooting/`)

증상 → 원인 → 시도한 것 → 해결 → 배운 점 형식이다. 파일명은 `YYYY-MM-DD_제목.md`이다.

- [요청 ID 충돌](troubleshooting/2026-10-13_request-id-충돌.md)
- [채점 에코 통과](troubleshooting/2026-10-13_채점-에코-통과.md)
- [설정 오류에 키 노출](troubleshooting/2026-10-13_설정-오류에-키-노출.md)
- [fallback 가짜 응답이 200으로 나간다](troubleshooting/2026-10-13_fallback-가짜-응답이-200으로-나간다.md)

## 코드 옆의 문서

- [평가 도구 사용법과 실측 절차](../code/backend/evals/README.md), [데이터셋 설명](../code/backend/evals/datasets/README.md)
- 모듈별 안내: [gateway](../code/backend/gateway/README.md), [router](../code/backend/router/README.md), [providers](../code/backend/providers/README.md), [guards](../code/backend/guards/README.md)
- 개발 안내: [백엔드](../code/backend/README.md), [프런트엔드](../code/frontend/README.md)

## 문서 규칙

- 한국어로 쓰고 "~이다/~한다" 체를 쓴다.
- 측정 결과에는 표본 크기, 라벨 상태, 확인하지 못한 것을 함께 적는다.
- 구조나 기술 선택을 바꾸면 [architecture.md](architecture.md)의 결정 기록 표에 한 줄을 추가한다. 자세한 규칙은 [CONTRIBUTING.md](../CONTRIBUTING.md)에 있다.
