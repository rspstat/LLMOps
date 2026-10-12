import re
import unicodedata
from dataclasses import dataclass

from guards.base import GuardAction, GuardResult

# Minimal first-pass filter: obvious, high-precision phrases only. Real detection (classifier,
# Jev, attack-prompt benchmarks) arrives in roadmap stage 4.
_INJECTION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (label, re.compile(pattern, re.IGNORECASE))
    for label, pattern in (
        (
            "ignore_previous",
            r"\b(ignore|disregard|forget)\s+(all\s+|any\s+)?(the\s+)?(previous|prior|above|earlier)"
            r"\s+(instructions?|prompts?|rules|directions)\b",
        ),
        (
            "reveal_system_prompt",
            r"\b(reveal|show|print|repeat|output)\s+(me\s+)?(your\s+|the\s+)?"
            r"(system|hidden|initial)\s+prompt\b",
        ),
        ("jailbreak_persona", r"\byou\s+are\s+now\s+(dan|in\s+developer\s+mode)\b"),
        (
            "ignore_previous_ko",
            r"(이전|위의|앞의|기존)\s*(모든\s*)?(지시|명령|지침|규칙)(사항)?\s*(을|를)?\s*(모두\s*)?"
            r"(무시|잊어)",
        ),
        (
            "reveal_system_prompt_ko",
            r"시스템\s*프롬프트\s*(를|을)?\s*(알려|보여|출력|공개)",
        ),
    )
)


@dataclass(frozen=True, slots=True)
class InputGuardConfig:
    max_input_chars: int = 8000
    block_injection: bool = True


class InputGuard:
    def __init__(self, config: InputGuardConfig | None = None) -> None:
        self.config = config or InputGuardConfig()

    def check(self, text: str) -> GuardResult:
        if not text.strip():
            return self._block("empty_input")
        if len(text) > self.config.max_input_chars:
            return self._block("input_too_long")
        if self.config.block_injection:
            # NFKC folds full-width letters etc. so trivial obfuscation does not slip through.
            normalized = " ".join(unicodedata.normalize("NFKC", text).split())
            for label, pattern in _INJECTION_PATTERNS:
                if pattern.search(normalized):
                    return self._block(f"prompt_injection:{label}")
        return GuardResult(GuardAction.ALLOW, "ok", 0.0)

    @staticmethod
    def _block(reason: str) -> GuardResult:
        return GuardResult(GuardAction.BLOCK, reason, 1.0)
