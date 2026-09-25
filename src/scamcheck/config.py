from dataclasses import dataclass

TYPESAFE_BASE_URL = "https://api.typesafe.ai/v1"

JEV = "jev-latest"
JEV_PREVIEW = "jev-preview"
OPUS = "claude-opus-5"
HAIKU = "claude-haiku-4-5"

PROVIDERS = {JEV: "jev", JEV_PREVIEW: "jev", OPUS: "anthropic", HAIKU: "anthropic"}

# USD per million tokens (input, output), used for eval cost reporting.
PRICING = {JEV: (0.042, 0.0), JEV_PREVIEW: (0.042, 0.0), OPUS: (5.00, 25.00), HAIKU: (1.00, 5.00)}


@dataclass(frozen=True)
class CheckerConfig:
    model: str = JEV
    # For Jev this names a question set (scamcheck.providers.jev); for Claude, a prompt file.
    prompt_version: str = "v2_checklist"
    # Effort is only used for Anthropic models that support it (not Haiku 4.5).
    effort: str | None = None
    max_tokens: int = 4096

    @property
    def provider(self) -> str:
        return PROVIDERS[self.model]


def config_for(model: str, prompt_version: str) -> CheckerConfig:
    return CheckerConfig(model=model, prompt_version=prompt_version, effort="low" if model == OPUS else None)


# Provisional until the evaluation picks one; see evals/results/REPORT.md.
DEFAULT_CONFIG = CheckerConfig()
