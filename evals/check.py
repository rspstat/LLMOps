"""`evals.run check`: explain what the current .env will actually do, without printing any secret.

The failure it exists for: an API key is filled in but its provider switch is still `mock`, so
nothing is ever called and nothing says why. Only variable names, on/off states and URL hosts are
printed; values of keys are never read into the output.
"""

from collections.abc import Mapping
from urllib.parse import urlsplit

from gateway.settings import Settings

# Variables .env.example lists that no adapter in this project reads (yet).
NOT_READ_BY_PROJECT = ("ANTHROPIC_API_KEY", "GOOGLE_API_KEY", "HF_TOKEN")
# Listed in .env.example for tools around the app (uvicorn flags, caches), not read via Settings.
KNOWN_EXTRAS = {"HF_HOME", "GATEWAY_HOST", "GATEWAY_PORT", "VECTOR_DB_URL"}


def _host(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.hostname}" + (f":{parts.port}" if parts.port else "")


def _filled(value: str | None) -> bool:
    return bool((value or "").strip())


def diagnose(
    settings: Settings, defined: Mapping[str, str | None], env_file_exists: bool
) -> tuple[list[str], list[str]]:
    """Return (status lines, problems). No problems means the configuration is coherent."""
    s = settings
    out: list[str] = []
    problems: list[str] = []

    def has(name: str) -> bool:
        return _filled(defined.get(name))

    if not env_file_exists:
        problems.append(".env 파일이 없습니다. `Copy-Item .env.example .env` 로 만든 뒤 채우세요.")

    # small model
    if s.small_provider == "mock":
        out.append("소형(small)   : mock (오프라인 가짜 모델)")
        if has("SLM_MODEL") or has("SLM_API_KEY"):
            problems.append(
                "SLM_MODEL / SLM_API_KEY 가 채워져 있지만 SMALL_PROVIDER=mock 이라 사용되지 않습니다. "
                "SMALL_PROVIDER=slm 으로 바꾸세요."
            )
    else:
        hosted = bool(s.slm_api_key.get_secret_value())
        priced = s.small_price_in_per_mtok > 0 or s.small_price_out_per_mtok > 0
        kind = "호스팅 API (키 있음)" if hosted else "자체 서빙 (키 없음, 무료로 간주)"
        out.append(f"소형(small)   : slm  model={s.slm_model}  url={_host(s.slm_base_url)}  {kind}")
        if hosted and not priced:
            problems.append(
                "소형 모델이 호스팅 API인데 SMALL_PRICE_IN/OUT_PER_MTOK 단가가 0 입니다 "
                "(단가가 없으면 예산 가드가 작동하지 않아 수집이 거부됩니다)."
            )

    # frontier model
    if s.frontier_provider == "mock":
        out.append("상용(frontier): mock (오프라인 가짜 모델)")
        if has("OPENAI_API_KEY") or has("FRONTIER_MODEL"):
            problems.append(
                "OPENAI_API_KEY / FRONTIER_MODEL 이 채워져 있지만 FRONTIER_PROVIDER=mock 이라 사용되지 않습니다. "
                "FRONTIER_PROVIDER=openai 로 바꾸세요."
            )
    else:
        priced = s.frontier_price_in_per_mtok > 0 or s.frontier_price_out_per_mtok > 0
        out.append(
            f"상용(frontier): openai  model={s.frontier_model}  url={_host(s.frontier_base_url)}  키 있음"
        )
        if not priced:
            problems.append(
                "FRONTIER_PRICE_IN/OUT_PER_MTOK 단가가 0 입니다 (제공사 가격표를 보고 채우세요)."
            )

    # judge
    if s.judge_provider == "mock":
        out.append("판정기(judge) : mock (오프라인 가짜 판정기)")
        if has("JEV_API_KEY"):
            problems.append(
                "JEV_API_KEY 가 채워져 있지만 JUDGE_PROVIDER=mock 이라 Jev 가 호출되지 않습니다. "
                "JUDGE_PROVIDER=jev 로 바꾸세요."
            )
    else:
        priced = s.jev_price_in_per_mtok > 0 or s.jev_price_out_per_mtok > 0
        out.append(
            f"판정기(judge) : jev  model={s.jev_model}  url={_host(s.jev_base_url)}  키 있음"
        )
        if not priced:
            problems.append("JEV_PRICE_IN_PER_MTOK 단가가 0 입니다 (회사 발표 단가는 0.042).")

    out.append(f"라우터 모드   : {s.router_mode}")
    if s.judge_provider == "jev" and s.router_mode == "rules":
        out.append(
            "  (참고) ROUTER_MODE=rules 라서 게이트웨이 서버는 판정기를 부르지 않습니다. "
            "평가 도구(evals)는 이 설정과 무관하게 판정기를 사용합니다."
        )
    if not s.gateway_api_key.get_secret_value():
        out.append(
            "GATEWAY_API_KEY: 비어 있음 (게이트웨이 서버로 요청을 받을 때만 필요, 평가 도구에는 불필요)"
        )

    for name in NOT_READ_BY_PROJECT:
        if has(name):
            problems.append(
                f"{name} 는 채워져 있지만 이 프로젝트가 읽지 않습니다 (해당 제공사용 어댑터가 없음). "
                "OpenAI 호환 엔드포인트라면 SLM_API_KEY / OPENAI_API_KEY 를 쓰세요."
            )

    known = (
        {name.upper() for name in Settings.model_fields} | set(NOT_READ_BY_PROJECT) | KNOWN_EXTRAS
    )
    for name in defined:
        if name.upper() not in known:
            problems.append(f"{name}: 알 수 없는 변수 이름입니다 (오타?). 앱은 이 줄을 무시합니다.")

    return out, problems
