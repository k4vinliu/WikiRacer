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
HARD_MODEL_ENV = "WIKIRACER_HARD_MODEL"
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
class Tier:
    model: str
    use_find_target: bool


def tiers(env: Mapping[str, str] | None = None) -> dict[str, Tier]:
    """FRONTEND.md §5.5: difficulty moves two honest levers, the pair and the agent, and never
    a handicap. Easy switches find_target off, so the agent doesn't look ahead. Hard is Sonnet 5
    unless WIKIRACER_HARD_MODEL says otherwise (FRONTEND.md §12.2 is still an open question)."""
    env = os.environ if env is None else env
    return {
        "easy": Tier(model=DEFAULT_MODEL, use_find_target=False),
        "medium": Tier(model=DEFAULT_MODEL, use_find_target=True),
        "hard": Tier(model=(env.get(HARD_MODEL_ENV) or HARD_MODEL).strip(), use_find_target=True),
    }


def load_env(path: Path | str = REPO_ROOT / ".env") -> None:
    """Read `.env` into os.environ. Never overrides a variable that is already set."""
    from dotenv import load_dotenv

    load_dotenv(path, override=False)


def make_client() -> Any:
    """The one Anthropic client, injected into the picker: 8 s timeout, 1 retry (PLAN.md §4.C).
    The SDK defaults are 10 minutes and 2 retries, and timeouts are retried, which is ~30
    minutes of dead air on stage before the picker's fallback could fire."""
    load_env()
    if not (os.environ.get("ANTHROPIC_API_KEY") or "").strip():
        raise ConfigError("ANTHROPIC_API_KEY is not set. Copy .env.example to .env and put your key "
                          "after the '=' (or export ANTHROPIC_API_KEY=...).")
    import anthropic

    return anthropic.Anthropic(timeout=LLM_TIMEOUT_S, max_retries=LLM_MAX_RETRIES)


def preflight_anthropic(client: Any, models: Iterable[str]) -> None:
    """Fail at the terminal in a second, not on hop 1 on the projector. Asking the Models API
    about each model proves the key AND catches a typo'd model name, and it spends no tokens."""
    import anthropic

    for model in sorted(set(models)):
        try:
            client.models.retrieve(model)
        except anthropic.AuthenticationError as e:
            raise ConfigError(f"Anthropic rejected the API key ({e.message}). "
                              "Check ANTHROPIC_API_KEY in .env.") from None
        except anthropic.PermissionDeniedError as e:
            raise ConfigError(f"This Anthropic key isn't allowed to use {model!r} ({e.message}).") from None
        except anthropic.NotFoundError:
            raise ConfigError(f"Anthropic has no model called {model!r}. "
                              f"Check --model / {HARD_MODEL_ENV}.") from None
        except anthropic.APIConnectionError as e:  # includes APITimeoutError
            raise ConfigError(f"Couldn't reach api.anthropic.com ({type(e).__name__}). "
                              "Check the network.") from None
        except anthropic.APIStatusError as e:
            raise ConfigError(f"Anthropic answered HTTP {e.status_code} checking {model!r}: {e.message}") from None


def preflight_steel() -> tuple[bool, str]:
    """`steel doctor --preflight`. Never a STEEL_API_KEY check (PLAN.md §4.E)."""
    return steel_client.doctor()
