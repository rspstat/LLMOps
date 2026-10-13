"""`evals.run check`: explain what the current .env will actually do, without printing any secret.

The failure it exists for: an API key is filled in but its provider switch is still `mock`, so
nothing is ever called and nothing says why. Only variable names, on/off states and URL hosts are
printed; values of keys are never read into the output.
"""

import ipaddress
import re
from collections.abc import Mapping
from urllib.parse import urlsplit

from pydantic import ValidationError
from pydantic_settings.exceptions import SettingsError

from gateway.settings import Settings

# Variables .env.example lists that no adapter in this project reads (yet).
NOT_READ_BY_PROJECT = ("ANTHROPIC_API_KEY", "GOOGLE_API_KEY", "HF_TOKEN")
# Listed in .env.example for tools around the app (uvicorn flags, caches), not read via Settings.
KNOWN_EXTRAS = {"HF_HOME", "GATEWAY_HOST", "GATEWAY_PORT", "VECTOR_DB_URL"}


# Letters, digits, dots, hyphens and underscores (workspace ids may contain `_`).
_HOSTNAME = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9._-]*[A-Za-z0-9])?$")


def _valid_url(url: str) -> bool:
    """http(s) with a plain hostname. A leftover placeholder like `<API Host>` is not one."""
    parts = urlsplit(url.strip())
    try:
        host = parts.hostname
    except ValueError:
        return False
    return parts.scheme in ("http", "https") and bool(host) and bool(_HOSTNAME.match(host))


def url_problem_reason(url: str) -> str:
    """Why a URL is rejected, described by kind. The value itself is never part of the text."""
    text = url.strip()
    if not text:
        return "값이 비어 있음"
    parts = urlsplit(text)
    reasons = []
    if not parts.scheme:
        reasons.append("주소가 `https://` 로 시작하지 않음")
    elif parts.scheme not in ("http", "https"):
        reasons.append("앞부분이 `http://` 또는 `https://` 가 아님")
    try:
        host = parts.hostname
    except ValueError:
        host = None
        reasons.append("호스트 부분을 해석할 수 없음 (대괄호 등)")
    if not host:
        if not any("해석" in r for r in reasons):
            reasons.append("도메인(호스트) 부분이 비어 있음")
    else:
        bad = sorted({c for c in host if not (c.isalnum() or c in ".-_")})
        if bad:
            reasons.append("도메인에 허용되지 않는 문자가 있음: " + " ".join(repr(c) for c in bad))
        elif not _HOSTNAME.match(host):
            reasons.append("도메인이 점이나 하이픈으로 시작하거나 끝남")
    if any(c.isspace() for c in text):
        reasons.append("공백이 들어 있음")
    if "<" in text or ">" in text or "{" in text or "}" in text:
        reasons.append("자리표시자(`<API Host>`, `{WorkspaceId}`)가 그대로 남아 있을 수 있음")
    return "; ".join(reasons) or "형식을 해석할 수 없음"


def host_for_display(url: str) -> str:
    """scheme://host[:port] for printing. A leading label is hidden when the host has more than
    three labels (`ws-<id>.region.vendor.com` -> `*.region.vendor.com`): that label is usually an
    account or workspace id. Plain hosts (`api.openai.com`, `localhost`, IPs) are shown whole."""
    if not _valid_url(url):
        return "(URL 형식이 아님)"
    parts = urlsplit(url.strip())
    host = parts.hostname
    try:
        ipaddress.ip_address(host)
        is_ip = True
    except ValueError:
        is_ip = False
    labels = host.split(".")
    if not is_ip and len(labels) > 3:
        host = "*." + ".".join(labels[1:])
    return f"{parts.scheme}://{host}" + (f":{parts.port}" if parts.port else "")


_SAFE_PATH = re.compile(r"^[A-Za-z0-9._~/-]{0,80}$")


def url_for_display(url: str) -> str:
    """host_for_display plus the path, when the path is plain. Queries, fragments and credentials
    (which could carry a token) are never shown; an unusual path is left out entirely."""
    shown = host_for_display(url)
    if not _valid_url(url):
        return shown
    path = urlsplit(url.strip()).path
    return shown + (path if path and _SAFE_PATH.match(path) else "")


_host = url_for_display


def _alibaba_path_problem(name: str, url: str) -> str | None:
    """Alibaba's OpenAI-compatible endpoint lives under /compatible-mode/v1; the bare API host
    answers every other path with an empty 404."""
    if not _valid_url(url):
        return None
    parts = urlsplit(url.strip())
    if parts.hostname and parts.hostname.endswith(".aliyuncs.com"):
        if not parts.path.rstrip("/").endswith("/compatible-mode/v1"):
            return (
                f"{name} 의 경로가 `/compatible-mode/v1` 로 끝나지 않습니다. Alibaba 주소는 "
                "`https://<API Host>/compatible-mode/v1` 형식이어야 하고, 호스트만 쓰면 404가 납니다."
            )
    return None


def _bad_url_problem(name: str, url: str) -> str:
    return (
        f"{name} 이 올바른 URL이 아닙니다 → {url_problem_reason(url)}. "
        "형식은 `https://도메인/경로` 입니다."
    )


def _filled(value: str | None) -> bool:
    return bool((value or "").strip())


def _extra_note(extra_body: Mapping[str, object]) -> str:
    """Names of the extra request fields, never their values."""
    return f"  추가 필드: {', '.join(sorted(extra_body))}" if extra_body else ""


_NUMBER_ERRORS = {"float_parsing", "int_parsing", "float_type", "int_type"}

# What can be shown from the raw file when it does not load: plain choices and model names,
# URL hosts, price numbers, and only whether a key is filled in. Key values are never shown.
_SHOWN_AS_IS = (
    "SMALL_PROVIDER",
    "FRONTIER_PROVIDER",
    "JUDGE_PROVIDER",
    "ROUTER_MODE",
    "SLM_MODEL",
    "FRONTIER_MODEL",
    "JEV_MODEL",
)
_URLS = ("SLM_BASE_URL", "FRONTIER_BASE_URL", "JEV_BASE_URL")
_KEYS = ("SLM_API_KEY", "OPENAI_API_KEY", "JEV_API_KEY", "GATEWAY_API_KEY")
_JSON_FIELDS = ("SLM_EXTRA_BODY", "FRONTIER_EXTRA_BODY")
_PRICES = (
    "SMALL_PRICE_IN_PER_MTOK",
    "SMALL_PRICE_OUT_PER_MTOK",
    "FRONTIER_PRICE_IN_PER_MTOK",
    "FRONTIER_PRICE_OUT_PER_MTOK",
    "JEV_PRICE_IN_PER_MTOK",
    "JEV_PRICE_OUT_PER_MTOK",
)


def describe_raw_values(defined: Mapping[str, str | None]) -> list[str]:
    """The non-secret settings as written in the file, for when the file cannot be loaded."""
    lines = []
    for name in _SHOWN_AS_IS:
        lines.append(f"{name} = {(defined.get(name) or '').strip() or '(비어 있음)'}")
    for name in _URLS:
        raw = (defined.get(name) or "").strip()
        lines.append(f"{name} = {_host(raw) if raw else '(비어 있음)'}")
    for name in _PRICES:
        raw = (defined.get(name) or "").strip()
        try:
            shown = str(float(raw)) if raw else "(비어 있음)"
        except ValueError:
            shown = "(숫자가 아님)"
        lines.append(f"{name} = {shown}")
    for name in _KEYS:
        lines.append(f"{name} = {'채워짐' if _filled(defined.get(name)) else '(비어 있음)'}")
    for name in _JSON_FIELDS:  # only whether it is set; the JSON itself may carry anything
        lines.append(f"{name} = {'설정됨' if _filled(defined.get(name)) else '(비어 있음)'}")
    return lines


def describe_load_errors(exc: ValidationError | SettingsError) -> list[str]:
    """One friendly line per bad setting, naming the .env variable. Values are never included."""
    if isinstance(exc, SettingsError):  # e.g. a JSON variable that is not valid JSON
        field = re.search(r'field "([^"]+)"', str(exc))
        name = field.group(1).upper() if field else "(알 수 없음)"
        return [f'{name}: JSON 형식이 아닙니다. 예: {name}={{"enable_thinking": false}}']
    lines = []
    for err in exc.errors(include_input=False, include_url=False, include_context=False):
        name = ".".join(str(part) for part in err["loc"]).upper()
        if err["type"] in _NUMBER_ERRORS:
            lines.append(
                f"{name}: 숫자여야 합니다. 설명 글자나 오타가 들어 있을 수 있으니 `{name}=0` 처럼 숫자만 쓰세요."
            )
        elif err["type"] == "literal_error":
            lines.append(f"{name}: 허용되지 않는 값입니다 ({err['msg']}).")
        elif name:
            lines.append(f"{name}: {err['msg']}")
        else:  # a rule across several settings
            lines.append(err["msg"].removeprefix("Value error, "))
    return lines


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
        out.append(
            f"소형(small)   : slm  model={s.slm_model}  url={_host(s.slm_base_url)}  {kind}"
            f"{_extra_note(s.slm_extra_body)}"
        )
        if not _valid_url(s.slm_base_url):
            problems.append(_bad_url_problem("SLM_BASE_URL", s.slm_base_url))
        elif path_problem := _alibaba_path_problem("SLM_BASE_URL", s.slm_base_url):
            problems.append(path_problem)
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
            f"{_extra_note(s.frontier_extra_body)}"
        )
        if not _valid_url(s.frontier_base_url):
            problems.append(_bad_url_problem("FRONTIER_BASE_URL", s.frontier_base_url))
        elif path_problem := _alibaba_path_problem("FRONTIER_BASE_URL", s.frontier_base_url):
            problems.append(path_problem)
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
        if not _valid_url(s.jev_base_url):
            problems.append(_bad_url_problem("JEV_BASE_URL", s.jev_base_url))
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
