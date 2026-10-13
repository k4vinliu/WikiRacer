"""Settings, the difficulty tiers, and the two preflights. Lane C. PLAN.md §4.E, FRONTEND.md §5.5.

Two rules from PLAN.md §4.E that are easy to get wrong:

* Load `.env`. `.env.example` ships, so a teammate who fills in `.env` must not get our
  "key missing" error while staring at the key.
* Do NOT hard-check `STEEL_API_KEY`. Our code never reads it; it shells out to `steel`,
  which resolves its own credentials, and someone who ran `steel login` has no such
  variable. The Steel preflight is `steel doctor --preflight`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from speedrun import steel_client

REPO_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_MODEL = "claude-haiku-4-5"  # the alias; never append a date suffix (PLAN.md §2.4)
HARD_MODEL = "claude-sonnet-5"      # FRONTEND.md §5.5; picker.model_params() switches its thinking off
DEFAULT_LLM_BASE_URL = "https://api.anthropic.com"
LLM_API_KEY_ENV = "LLM_API_KEY"
ANTHROPIC_API_KEY_ENV = "ANTHROPIC_API_KEY"  # fallback for existing local .env files
LLM_BASE_URL_ENV = "LLM_BASE_URL"
LLM_EASY_MODEL_ENV = "LLM_EASY_MODEL"
LLM_MEDIUM_MODEL_ENV = "LLM_MEDIUM_MODEL"
LLM_HARD_MODEL_ENV = "LLM_HARD_MODEL"
HARD_MODEL_ENV = "WIKIRACER_HARD_MODEL"  # legacy fallback if LLM_HARD_MODEL is unset
DEFAULT_MAX_HOPS = 25
DEFAULT_SESSION_TIMEOUT_MS = 900_000
LLM_TIMEOUT_S = 8.0
LLM_MAX_RETRIES = 1
TARGET_MEDIAN_HOP_S = 3.5  # PLAN.md §4.E. Measured Steel hop: 1.03 s (docs/steel-json-shapes.md)
SERVER_HOST = "127.0.0.1"
SERVER_PORT = 8848


class ConfigError(RuntimeError):
    """A setup problem the host can fix. Print the message, never a stack trace."""


@dataclass(frozen=True)
class LlmSettings:
    """The Anthropic-compatible client settings. Provider is entirely env-driven."""

    api_key: str
    base_url: str


def _env_str(env: Mapping[str, str], key: str) -> str:
    return (env.get(key) or "").strip()


def llm_api_key(env: Mapping[str, str] | None = None) -> str:
    """LLM_API_KEY, falling back to ANTHROPIC_API_KEY so existing .env files still work."""
    env = os.environ if env is None else env
    return _env_str(env, LLM_API_KEY_ENV) or _env_str(env, ANTHROPIC_API_KEY_ENV)


def llm_base_url(env: Mapping[str, str] | None = None) -> str:
    env = os.environ if env is None else env
    return _env_str(env, LLM_BASE_URL_ENV) or DEFAULT_LLM_BASE_URL


def llm_settings(env: Mapping[str, str] | None = None) -> LlmSettings:
    env = os.environ if env is None else env
    return LlmSettings(api_key=llm_api_key(env), base_url=llm_base_url(env))


@dataclass(frozen=True)
class Tier:
    model: str
    use_find_target: bool
    hop_delay_s: float  # the agent waits this long on each page before it looks for a link


HOP_DELAY_S = {"easy": 10.0, "medium": 5.0, "hard": 2.0}


def tiers(env: Mapping[str, str] | None = None, hop_delay_s: float | None = None) -> dict[str, Tier]:
    """The three difficulty tiers (FRONTEND.md §5.5). Easy switches find_target off, so the agent
    doesn't look ahead. Models come from LLM_EASY_MODEL / LLM_MEDIUM_MODEL / LLM_HARD_MODEL,
    defaulting to Haiku / Haiku / Sonnet so the existing Claude setup still works.
    LLM_HARD_MODEL falls back to WIKIRACER_HARD_MODEL, then to HARD_MODEL.

    Every tier also makes the agent wait on each page before it looks for its next link: 10 s,
    5 s, 2 s. Once it has chosen, it clicks at once, so it never sits on a link it has already
    found. §5.5 ruled out any such handicap, but the team added one on 2026-09-13 after finding
    that no human could win on any tier. `hop_delay_s` (the `--hop-delay` flag) sets one wait for
    every tier, and 0 shows the agent at full speed."""
    env = os.environ if env is None else env

    def wait(tier: str) -> float:
        return HOP_DELAY_S[tier] if hop_delay_s is None else float(hop_delay_s)

    easy_model = _env_str(env, LLM_EASY_MODEL_ENV) or DEFAULT_MODEL
    medium_model = _env_str(env, LLM_MEDIUM_MODEL_ENV) or DEFAULT_MODEL
    hard_model = (_env_str(env, LLM_HARD_MODEL_ENV) or _env_str(env, HARD_MODEL_ENV) or HARD_MODEL)
    return {
        "easy": Tier(model=easy_model, use_find_target=False, hop_delay_s=wait("easy")),
        "medium": Tier(model=medium_model, use_find_target=True, hop_delay_s=wait("medium")),
        "hard": Tier(model=hard_model, use_find_target=True, hop_delay_s=wait("hard")),
    }


def load_env(path: Path | str = REPO_ROOT / ".env") -> None:
    """Read `.env` into os.environ. Never overrides a variable that is already set."""
    from dotenv import load_dotenv

    load_dotenv(path, override=False)


def make_client() -> Any:
    """The one Anthropic-SDK client, injected into the picker: 8 s timeout, 1 retry (PLAN.md §4.C).
    The SDK defaults are 10 minutes and 2 retries, and timeouts are retried, which is ~30
    minutes of dead air on stage before the picker's fallback could fire.

    `base_url` is env-driven so an Anthropic-compatible provider can be swapped without
    picker changes. Timeout and retries stay pinned regardless of provider."""
    load_env()
    settings = llm_settings()
    if not settings.api_key:
        raise ConfigError("LLM_API_KEY is not set. Copy .env.example to .env and put your key "
                          "after the '=' (or export LLM_API_KEY=...).")
    import anthropic

    return anthropic.Anthropic(
        api_key=settings.api_key,
        base_url=settings.base_url,
        timeout=LLM_TIMEOUT_S,
        max_retries=LLM_MAX_RETRIES,
    )


def preflight_anthropic(client: Any, models: Iterable[str]) -> None:
    """Fail at the terminal in a second, not on hop 1 on the projector. Asking the Models API
    about each model proves the key AND catches a typo'd model name, and it spends no tokens."""
    import anthropic

    for model in sorted(set(models)):
        try:
            client.models.retrieve(model)
        except anthropic.AuthenticationError as e:
            raise ConfigError(f"The LLM provider rejected the API key ({e.message}). "
                              "Check LLM_API_KEY in .env.") from None
        except anthropic.PermissionDeniedError as e:
            raise ConfigError(f"This API key isn't allowed to use {model!r} ({e.message}).") from None
        except anthropic.NotFoundError:
            raise ConfigError(f"The LLM provider has no model called {model!r}. "
                              f"Check --model / {LLM_EASY_MODEL_ENV} / {LLM_MEDIUM_MODEL_ENV} / "
                              f"{LLM_HARD_MODEL_ENV}.") from None
        except anthropic.APIConnectionError as e:  # includes APITimeoutError
            raise ConfigError(f"Couldn't reach the LLM API ({type(e).__name__}). "
                              "Check LLM_BASE_URL and the network.") from None
        except anthropic.APIStatusError as e:
            raise ConfigError(f"The LLM provider answered HTTP {e.status_code} checking {model!r}: "
                              f"{e.message}") from None


def preflight_steel() -> tuple[bool, str]:
    """`steel doctor --preflight`. Never a STEEL_API_KEY check (PLAN.md §4.E)."""
    return steel_client.doctor()
