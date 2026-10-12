# evals

라우팅 평가 모듈. "어떤 라우팅 설정(모드 × 임계값 τ)이 비용을 얼마나 줄이고 정확도를 얼마나 잃는가"를 재현 가능하게 측정합니다. 설계와 결정 근거는 [docs/architecture.md §6](../docs/architecture.md)을 보세요.

## 현재 상태

도구는 모두 구현되어 mock으로 검증했습니다. **실제 모델로 수집한 결과는 아직 없습니다.** 리포트의 숫자는 실제 소형·상용 모델과 Jev로 `collect`를 돌린 뒤에야 의미가 있습니다.

## 흐름

```
routing_v1.jsonl ──collect──▶ cache/<이름>.jsonl ──report──▶ reports/<이름>/report.md
 (80 프롬프트)   판정기·소형·상용   (항목별 응답·토큰·지연·비용·판정 확률)   (설정별 비교, 판정기 품질, …)
                  각 1회 호출         캐시 재생: 호출 0회
```

## 사용법

```bash
uv run python -m evals.run validate                          # 데이터셋 검사
uv run python -m evals.run collect --name demo --limit 20    # 기본 mock: 키 없이 전체 흐름 확인
uv run python -m evals.run report  --name demo               # 리포트 생성

# 실제 모델: .env 에 SMALL_PROVIDER / FRONTIER_PROVIDER / JUDGE_PROVIDER 와 키를 설정한 뒤
uv run python -m evals.run collect --name real --dry-run     # 호출 수·예상 비용 상한만 출력
ALLOW_LIVE_CALLS=1 uv run python -m evals.run collect --name real --budget-usd 0.25
```

- mock이 아닌 provider는 `ALLOW_LIVE_CALLS=1`(셸에서만)과 `--budget-usd`가 둘 다 있어야 실행됩니다.
- 중단해도 캐시에서 이어서 실행되고, 모델·프롬프트·정책·`max_tokens`가 바뀐 항목만 다시 수집됩니다.
- `report`는 캐시만 읽습니다. `--taus 0.5,0.7,0.9`로 임계값을 바꿀 수 있습니다.
- `cache/`와 `reports/`는 `.gitignore` 대상입니다. 의미 있는 결과는 `docs/`로 복사해 커밋하세요.

## 구성

| 파일 | 역할 |
|---|---|
| `schema.py` | `EvalItem`(프롬프트, 참조 답, 난이도 라벨, `options`) |
| `scorers.py` | 규칙 채점기: exact / number / choice(얼버무림 거부) / contains |
| `collect.py` | 실호출 수집, 캐시 키, 예산 가드, 예상 비용 |
| `cache.py` | append-only JSONL 캐시와 메타데이터 |
| `replay.py` | 게이트웨이의 실제 라우터를 녹화된 판정과 함께 실행 |
| `metrics.py` | 정확도(Wilson 구간), 비용·지연, 판정기 정밀도·재현율 |
| `report.py` | Markdown / CSV / JSON 리포트 |
| `run.py` | CLI |
| `datasets/` | `routing_v1.jsonl`과 [README](datasets/README.md)(출처·한계) |

예정(이후 단계): 같은 판정의 다중 방식 비교(Jev / 파인튜닝 분류기 / LLM judge), 가드 방어율 측정, LLM-as-judge.
