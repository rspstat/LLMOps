# evals

라우팅 평가 모듈. "어떤 라우팅 설정(모드 × 임계값 τ)이 비용을 얼마나 줄이고 정확도를 얼마나 잃는가"를 재현 가능하게 측정한다. 설계와 결정 근거는 [docs/architecture.md §6](../../../docs/architecture.md)을 참고한다.

## 현재 상태

도구는 mock으로 검증했고, 2026-10-13에 Qwen(소형 `qwen3.7-flash`, 상용 `qwen3.8-max`)과 Jev로 80문항을 처음 실측했다(약 $0.009). 결과와 한계는 [docs/evals/2026-10-13_qwen-first-run.md](../../../docs/evals/2026-10-13_qwen-first-run.md)에 있다. mock으로 만든 리포트의 숫자는 여전히 의미가 없으며, 리포트 상단에 경고가 표시된다.

## 흐름

```
routing_v1.jsonl ──collect──▶ cache/<이름>.jsonl ──report──▶ reports/<이름>/report.md
 (80 프롬프트)   판정기·소형·상용   (항목별 응답·토큰·지연·비용·판정 확률)   (설정별 비교, 판정기 품질, …)
                  각 1회 호출         캐시 재생: 호출 0회
```

## 사용법

```bash
uv run python -m evals.run validate                          # 데이터셋 검사
uv run python -m evals.run collect --name sample --limit 20    # 기본 mock: 키 없이 전체 흐름 확인
uv run python -m evals.run report  --name sample             # 리포트 생성

# 실제 모델: .env 에 SMALL_PROVIDER / FRONTIER_PROVIDER / JUDGE_PROVIDER 와 키를 설정한 뒤
uv run python -m evals.run collect --name real --dry-run     # 호출 수·예상 비용 상한만 출력
ALLOW_LIVE_CALLS=1 uv run python -m evals.run collect --name real --budget-usd 0.25
```

- mock이 아닌 provider는 `ALLOW_LIVE_CALLS=1`(셸에서만)과 `--budget-usd`가 둘 다 있어야 실행된다.
- 중단해도 캐시에서 이어서 실행되고, 모델·프롬프트·정책·`max_tokens`가 바뀐 항목만 다시 수집된다.
- `report`는 캐시만 읽는다. `--taus 0.5,0.7,0.9`로 임계값을 바꿀 수 있다.
- `cache/`와 `reports/`는 `.gitignore` 대상이다. 의미 있는 결과는 `docs/`로 복사해 커밋한다.

## 실측 (실제 모델로 수집)

`.env`에 아래 항목을 채운다. **키는 채팅이나 커밋에 넣지 말고 `.env`에만** 둔다. 단가(USD / 100만 토큰)는 각 제공사의 가격표에서 직접 확인해 넣는다. 단가가 0이면 예산 가드가 작동하지 않아서 과금되는 모델은 단가 없이는 수집이 거부된다.

```
# 소형(small) 모델: 호스팅 OpenAI 호환 API의 저가 "채팅" 모델 (추론 모델은 피하세요, 아래 참고)
SMALL_PROVIDER=slm
SLM_BASE_URL=<엔드포인트>        # 예: https://api.openai.com/v1
SLM_MODEL=<모델명>
SLM_API_KEY=<키>
SMALL_PRICE_IN_PER_MTOK=<입력 단가>
SMALL_PRICE_OUT_PER_MTOK=<출력 단가>

# 상용(frontier) 모델
FRONTIER_PROVIDER=openai
FRONTIER_BASE_URL=https://api.openai.com/v1
FRONTIER_MODEL=<모델명>
OPENAI_API_KEY=<키>
FRONTIER_PRICE_IN_PER_MTOK=<입력 단가>
FRONTIER_PRICE_OUT_PER_MTOK=<출력 단가>

# 판정기: Jev (접근 경로마다 URL·모델명이 다릅니다)
JUDGE_PROVIDER=jev
JEV_API_KEY=<키>
JEV_BASE_URL=<엔드포인트 전체 URL>
JEV_MODEL=<모델명>
JEV_PRICE_IN_PER_MTOK=0.042       # 회사 발표 단가. 가격표를 확인하세요
```

**Qwen(Alibaba Cloud Model Studio)으로 구성할 때**: 키는 `Model Studio → Create API Key`(싱가포르 리전)에서 만들고, 키와 함께 표시되는 API Host를 복사한다. 키는 만든 리전에서만 동작한다. 소형·상용이 같은 키와 엔드포인트를 쓰므로 `OPENAI_API_KEY` 칸(상용 모델용 일반 키 칸)에도 같은 키를 넣는다. Qwen 최신 모델은 추론이 기본으로 켜져 있어 `*_EXTRA_BODY`로 꺼야 한다.

```
SLM_BASE_URL=<API Host>/compatible-mode/v1
SLM_MODEL=qwen3.7-flash
SLM_API_KEY=<Alibaba 키>
SLM_EXTRA_BODY={"enable_thinking": false}
SMALL_PRICE_IN_PER_MTOK=0.03
SMALL_PRICE_OUT_PER_MTOK=0.13

FRONTIER_BASE_URL=<API Host>/compatible-mode/v1
FRONTIER_MODEL=qwen3.8-max
OPENAI_API_KEY=<같은 Alibaba 키>
FRONTIER_EXTRA_BODY={"enable_thinking": false}
FRONTIER_PRICE_IN_PER_MTOK=2.00
FRONTIER_PRICE_OUT_PER_MTOK=6.00
```

- 추가 필드 없이 쓰려면 `qwen-flash`(추론 기본 꺼짐)와 `qwen-max`(비추론 전용)로 바꾸고 `*_EXTRA_BODY`를 비운다. 단가는 각각 0.05 / 0.40, 1.60 / 6.40이다.
- `qwen3.7-flash`의 0.03 / 0.13은 입력 32K 토큰 이하 구간 단가이다(이 평가의 프롬프트는 모두 해당).
- 엔드포인트 주소가 맞는지는 아래 1번 어댑터 확인이 알려 준다(틀리면 404/401과 응답 본문 앞부분이 출력된다).

실행 순서 (PowerShell):

```powershell
# 0. .env 점검: 호출 없이, 키 값을 출력하지 않고 "무엇이 켜져 있고 무엇이 비어 있는지"를 알려 줍니다.
#    키를 채웠는데 provider 스위치가 mock 이라 아무 일도 안 일어나는 경우가 가장 흔합니다.
uv run python -m evals.run check

# 1. 어댑터가 각 서비스와 실제로 맞는지 1회씩 확인 (호출 3번)
$env:ALLOW_LIVE_CALLS = "1"
uv run python -m scripts.smoke_live --target slm
uv run python -m scripts.smoke_live --target frontier
uv run python -m scripts.smoke_live --target jev --prompt "What is the capital of France?"

# 2. 호출 없이 예상 호출 수와 비용 상한 확인 (단가 경고가 없어야 합니다)
uv run python -m evals.run collect --name real --dry-run

# 3. 작게 먼저 (10개, 예산 $0.10), 이상 없으면 같은 이름으로 전체를 이어서 수집 (이미 한 항목은 재사용)
uv run python -m evals.run collect --name real --limit 10 --budget-usd 0.10
uv run python -m evals.run collect --name real --budget-usd 0.50

# 4. 리포트
uv run python -m evals.run report --name real
```

- 소형·상용 모델은 `max_tokens=64`로 호출하므로 **숨은 추론에 토큰을 쓰는 모델은 답이 비어** 오답으로 채점된다. 수집 중과 리포트에 "빈 응답" 경고가 나오면 추론 기능이 없는 채팅 모델로 바꾸거나 `--max-tokens`를 올려 다시 수집한다(모델이 바뀌면 캐시 키가 달라져 자동으로 다시 수집된다).
- 일부 최신 모델은 `max_tokens`나 `temperature=0`을 거부한다. 어댑터는 오류 본문이 해당 파라미터를 지목할 때만(과금되지 않는 400) 한 번씩 맞춰서 다시 보낸다. 이 동작은 mock HTTP로만 검증했고 실제 API에서는 확인하지 못했다.
- Jev가 아직 없으면 `JUDGE_PROVIDER=mock`으로 두고 소형·상용 수치만 먼저 수집한다. 리포트가 "판정기가 mock"이라고 표시하고 `hybrid`·`judge_only` 행은 무효라고 알려 준다. 나중에 Jev를 연결하면 판정기 identity가 캐시 키에 들어 있어서 **항목 전체(판정기·소형·상용)가 다시 수집된다.** 구성 요소별로 따로 캐시하지는 않는다(이번 규모에서는 몇 센트 수준이고 예산 가드가 적용된다).

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
