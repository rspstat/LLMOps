"""Manual smoke test that makes ONE real model call. Costs money for paid targets.

It refuses to run unless the shell sets ALLOW_LIVE_CALLS=1 for this invocation (do not put it in
.env). Never run it from tests or CI.

    PowerShell:  $env:ALLOW_LIVE_CALLS = "1"; uv run python -m scripts.smoke_live --target slm
    bash:        ALLOW_LIVE_CALLS=1 uv run python -m scripts.smoke_live --target frontier

Targets use the SLM_* / FRONTIER_* / OPENAI_API_KEY settings; `--target jev` uses JEV_* and asks
the real routing question (easy/hard) about --prompt. Safety limits: one request, no retries,
15 s timeout, max_tokens capped at 64 (jev: prompt cut to 500 chars; --max-tokens is ignored).
"""

import argparse
import asyncio
import os
import sys
from collections.abc import Mapping, Sequence

import httpx

from evals.check import url_for_display
from gateway.settings import Settings
from providers.base import ChatMessage, Provider, ProviderError, ProviderRequest
from providers.jev import JevProvider
from providers.openai_compat import OpenAICompatProvider
from router.policy import POLICY_VERSION, QUESTION, build_state

TIMEOUT_S = 15.0
JEV_PROMPT_LIMIT = 500  # keep the one judged request small
MAX_TOKENS_CAP = 64
DEFAULT_MAX_TOKENS = 16
DEFAULT_PROMPT = "Say hello in one word."
OUTPUT_LIMIT = 200

EXIT_OK, EXIT_CALL_FAILED, EXIT_REFUSED = 0, 1, 2


_host = url_for_display  # hides an account id in the host; shows a plain path, never a query


def build_provider(
    target: str, settings: Settings, transport: httpx.AsyncBaseTransport | None = None
) -> tuple[Provider, str] | str:
    """Return (provider, target description), or an error message if config is missing."""
    if target == "slm":
        if not settings.slm_model:
            return "SLM_MODEL is not set"
        provider = OpenAICompatProvider(
            "slm",
            base_url=settings.slm_base_url,
            model=settings.slm_model,
            api_key=settings.slm_api_key.get_secret_value() or None,
            timeout_s=TIMEOUT_S,
            transport=transport,
            extra_body=settings.slm_extra_body,
        )
        return provider, f"slm {_host(settings.slm_base_url)} model={settings.slm_model}"

    if not settings.frontier_model:
        return "FRONTIER_MODEL is not set"
    key = settings.openai_api_key.get_secret_value()
    if not key:
        return "OPENAI_API_KEY is not set"
    provider = OpenAICompatProvider(
        "frontier",
        base_url=settings.frontier_base_url,
        model=settings.frontier_model,
        api_key=key,
        timeout_s=TIMEOUT_S,
        transport=transport,
        extra_body=settings.frontier_extra_body,
    )
    return provider, f"frontier {_host(settings.frontier_base_url)} model={settings.frontier_model}"


def _smoke_jev(
    prompt: str, settings: Settings, transport: httpx.AsyncBaseTransport | None = None
) -> int:
    """One real Jev call using the actual routing policy and question (not a toy prompt)."""
    key = settings.jev_api_key.get_secret_value()
    if not key:
        print("Cannot run: JEV_API_KEY is not set.", file=sys.stderr)
        return EXIT_REFUSED
    jev = JevProvider(
        "jev",
        url=settings.jev_base_url,
        model=settings.jev_model,
        api_key=key,
        timeout_s=TIMEOUT_S,
        transport=transport,
    )
    state = build_state(prompt[:JEV_PROMPT_LIMIT])
    print(
        f"Calling jev {_host(settings.jev_base_url)} model={settings.jev_model} "
        f"(policy {POLICY_VERSION}, timeout={TIMEOUT_S:.0f}s)"
    )
    try:
        decision = asyncio.run(jev.decide(state, QUESTION))
    except ProviderError as exc:
        print(f"Call failed: {exc}", file=sys.stderr)
        return EXIT_CALL_FAILED

    print(f"model:   {decision.model}")
    print(f"choice:  {decision.choice} (confidence={decision.confidence})")
    print(f"probs:   {dict(decision.probabilities)}")
    print(f"tokens:  input={decision.input_tokens} output={decision.output_tokens}")
    return EXIT_OK


def main(
    argv: Sequence[str] | None = None,
    environ: Mapping[str, str] | None = None,
    *,
    settings: Settings | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> int:
    environ = os.environ if environ is None else environ
    parser = argparse.ArgumentParser(description="Make one real model call (opt-in).")
    parser.add_argument("--target", choices=["slm", "frontier", "jev"], required=True)
    parser.add_argument("--prompt", default=DEFAULT_PROMPT)
    parser.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS)
    args = parser.parse_args(argv)

    if environ.get("ALLOW_LIVE_CALLS") != "1":
        print(
            "Refusing to make a live call: set ALLOW_LIVE_CALLS=1 in the shell for this run.",
            file=sys.stderr,
        )
        return EXIT_REFUSED

    if args.target == "jev":
        return _smoke_jev(args.prompt, settings or Settings(), transport)

    built = build_provider(args.target, settings or Settings(), transport)
    if isinstance(built, str):
        print(f"Cannot run: {built}.", file=sys.stderr)
        return EXIT_REFUSED
    provider, description = built

    max_tokens = max(1, min(args.max_tokens, MAX_TOKENS_CAP))
    request = ProviderRequest(
        messages=(ChatMessage("user", args.prompt),), max_tokens=max_tokens, temperature=0.0
    )
    print(f"Calling {description} (max_tokens={max_tokens}, timeout={TIMEOUT_S:.0f}s)")
    try:
        response = asyncio.run(provider.complete(request))
    except ProviderError as exc:
        print(f"Call failed: {exc}", file=sys.stderr)
        return EXIT_CALL_FAILED

    print(f"model:   {response.model}")
    print(f"reply:   {response.content[:OUTPUT_LIMIT]!r}")
    print(f"tokens:  prompt={response.prompt_tokens} completion={response.completion_tokens}")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
