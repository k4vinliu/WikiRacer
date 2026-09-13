"""speedrun/config.py — settings, the difficulty tiers, and the two preflights. Offline: the
Anthropic client is faked, but the errors are the SDK's real exception classes. The 1.x SDK
is built on httpx2, not httpx, which is why the import below is the way it is."""

from __future__ import annotations

import os

import anthropic
import httpx2 as httpx
import pytest

from speedrun import config


def _status_error(cls, status: int):
    request = httpx.Request("GET", "https://api.anthropic.com/v1/models/claude-haiku-4-5")
    return cls("boom", response=httpx.Response(status, request=request), body=None)


class FakeModels:
    def __init__(self, fail: Exception | None = None):
        self.fail, self.asked = fail, []

    def retrieve(self, model_id: str, **kwargs):
        self.asked.append(model_id)
        if self.fail:
            raise self.fail
        return {"id": model_id}


class FakeClient:
    def __init__(self, fail: Exception | None = None):
        self.models = FakeModels(fail)


# --------------------------------------------------------------------------- tiers (FRONTEND.md §5.5)


def test_easy_turns_off_find_target_and_the_others_keep_it():
    tiers = config.tiers(env={})
    assert tiers["easy"].use_find_target is False
    assert tiers["medium"].use_find_target is True
    assert tiers["hard"].use_find_target is True


def test_the_default_model_is_the_haiku_alias_without_a_date():
    assert config.DEFAULT_MODEL == "claude-haiku-4-5"
    assert config.tiers(env={})["easy"].model == config.tiers(env={})["medium"].model == "claude-haiku-4-5"


def test_hard_runs_sonnet_unless_the_team_overrides_it():
    assert config.tiers(env={})["hard"].model == "claude-sonnet-5"
    assert config.tiers(env={"WIKIRACER_HARD_MODEL": "claude-haiku-4-5"})["hard"].model == "claude-haiku-4-5"


# --------------------------------------------------------------------------- the Anthropic client


def test_make_client_without_a_key_says_where_to_put_it(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(config, "load_env", lambda *a, **k: None)
    with pytest.raises(config.ConfigError, match=r"\.env"):
        config.make_client()


def test_make_client_uses_an_8s_timeout_and_one_retry(monkeypatch):
    # The SDK defaults are 10 minutes and 2 retries, and timeouts are retried: ~30 minutes of
    # dead air on stage before the picker's fallback could fire (PLAN.md §4.C).
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-a-real-one")  # nothing key-shaped for scanners
    monkeypatch.setattr(config, "load_env", lambda *a, **k: None)
    client = config.make_client()
    assert (client.timeout, client.max_retries) == (8.0, 1)


def test_preflight_checks_each_model_once():
    client = FakeClient()
    config.preflight_anthropic(client, ["claude-haiku-4-5", "claude-sonnet-5", "claude-haiku-4-5"])
    assert sorted(client.models.asked) == ["claude-haiku-4-5", "claude-sonnet-5"]


@pytest.mark.parametrize("exc, needle", [
    (_status_error(anthropic.AuthenticationError, 401), "API key"),
    (_status_error(anthropic.PermissionDeniedError, 403), "claude-haiku-4-5"),
    (_status_error(anthropic.NotFoundError, 404), "claude-haiku-4-5"),
    (anthropic.APIConnectionError(request=httpx.Request("GET", "https://api.anthropic.com")), "reach"),
])
def test_preflight_turns_api_errors_into_one_readable_line(exc, needle):
    with pytest.raises(config.ConfigError, match=needle):
        config.preflight_anthropic(FakeClient(fail=exc), ["claude-haiku-4-5"])


# --------------------------------------------------------------------------- .env and Steel


def test_load_env_reads_dotenv_without_overriding_the_shell(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("ANTHROPIC_API_KEY=from-file\nWIKIRACER_TEST_ONLY=from-file\n")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "from-shell")
    monkeypatch.delenv("WIKIRACER_TEST_ONLY", raising=False)
    config.load_env(env_file)
    assert os.environ["ANTHROPIC_API_KEY"] == "from-shell"
    assert os.environ["WIKIRACER_TEST_ONLY"] == "from-file"


def test_the_steel_preflight_is_steel_doctor_not_a_steel_api_key_check(monkeypatch):
    # PLAN.md §4.E: a teammate who ran `steel login` has no STEEL_API_KEY and must not be blocked.
    monkeypatch.delenv("STEEL_API_KEY", raising=False)
    monkeypatch.setattr(config.steel_client, "doctor", lambda: (True, "steel doctor --preflight: pass"))
    assert config.preflight_steel() == (True, "steel doctor --preflight: pass")
