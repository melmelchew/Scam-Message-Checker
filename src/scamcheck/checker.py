import time
from dataclasses import dataclass
from functools import cache
from importlib import resources

import anthropic
from dotenv import load_dotenv

from scamcheck import rules
from scamcheck.config import OPUS, CheckerConfig, DEFAULT_CONFIG
from scamcheck.models import Verdict
from scamcheck.providers import jev

load_dotenv()


class CheckError(Exception):
    """Raised when the message could not be checked. The text is safe to show to users."""


@dataclass
class CheckResult:
    verdict: Verdict
    signals: list[str]
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    latency_s: float
    confidence: float | None = None
    # Provider-specific breakdown shown in the UI's Details section (Jev only).
    details: dict | None = None


@cache
def load_prompt(version: str) -> str:
    return resources.files("scamcheck.prompts").joinpath(f"{version}.md").read_text()


@cache
def _client() -> anthropic.Anthropic:
    return anthropic.Anthropic()


def build_user_content(message: str, signals: list[str]) -> str:
    hints = "\n".join(f"- {s}" for s in signals) or "- none"
    return f"<rule_signals>\n{hints}\n</rule_signals>\n\n<message>\n{message}\n</message>"


def check(message: str, config: CheckerConfig = DEFAULT_CONFIG, client=None) -> CheckResult:
    if not message.strip():
        raise CheckError("Paste a message to check.")
    found = rules.signals(message)
    if config.provider == "jev":
        return _check_jev(message, found, config, client)
    return _check_anthropic(message, found, config, client or _client())


def _check_jev(message: str, found: list[str], config: CheckerConfig, client) -> CheckResult:
    start = time.perf_counter()
    try:
        data = jev.call(jev.build_request(config.model, config.prompt_version, message, found), client)
        verdict, details = jev.to_verdict(data["answers"])
    except jev.JevError as e:
        raise CheckError(str(e)) from e
    except (KeyError, ValueError) as e:
        raise CheckError("The model returned an answer in an unexpected format. Try again.") from e
    usage = data.get("usage", {})
    return CheckResult(
        verdict=verdict,
        signals=found,
        input_tokens=usage.get("input_tokens", 0),
        output_tokens=usage.get("output_tokens", 0),
        cache_read_tokens=0,
        latency_s=time.perf_counter() - start,
        confidence=details["confidence"],
        details=details,
    )


def _check_anthropic(message: str, found: list[str], config: CheckerConfig, client: anthropic.Anthropic) -> CheckResult:
    kwargs: dict = {}
    if config.effort:
        kwargs["output_config"] = {"effort": config.effort}
    if config.model == OPUS:
        # Route safety-classifier refusals to a fallback model instead of failing.
        kwargs["betas"] = ["server-side-fallback-2026-07-01"]
        kwargs["fallbacks"] = "default"

    start = time.perf_counter()
    try:
        response = client.beta.messages.parse(
            model=config.model,
            max_tokens=config.max_tokens,
            system=[{"type": "text", "text": load_prompt(config.prompt_version), "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": build_user_content(message, found)}],
            output_format=Verdict,
            **kwargs,
        )
    except anthropic.RateLimitError as e:
        raise CheckError("The checker is busy right now. Try again in a minute.") from e
    except anthropic.APIStatusError as e:
        raise CheckError(f"The checking service returned an error ({e.status_code}).") from e
    except anthropic.APIConnectionError as e:
        raise CheckError("Could not reach the checking service. Check your connection.") from e
    latency = time.perf_counter() - start

    if response.stop_reason == "refusal":
        raise CheckError("The model declined to assess this message.")
    if response.stop_reason == "max_tokens" or response.parsed_output is None:
        raise CheckError("The model returned an incomplete answer. Try again.")

    usage = response.usage
    return CheckResult(
        verdict=response.parsed_output,
        signals=found,
        input_tokens=usage.input_tokens + (usage.cache_creation_input_tokens or 0) + (usage.cache_read_input_tokens or 0),
        output_tokens=usage.output_tokens,
        cache_read_tokens=usage.cache_read_input_tokens or 0,
        latency_s=latency,
    )
