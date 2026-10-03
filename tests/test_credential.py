"""The credential line names what a run bills to and never shows a value."""
from mainsheet.agent.config import CREDENTIALS, credential


def clear(monkeypatch):
    for variable, _ in CREDENTIALS:
        monkeypatch.delenv(variable, raising=False)


def test_nothing_set_means_the_stored_login(monkeypatch):
    clear(monkeypatch)
    assert credential() == "stored Claude login"


def test_an_api_key_is_named_and_not_shown(monkeypatch):
    clear(monkeypatch)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "not-a-real-key")
    assert credential() == "API key (ANTHROPIC_API_KEY)"
    assert "not-a-real-key" not in credential()


def test_a_bearer_token_outranks_an_api_key(monkeypatch):
    clear(monkeypatch)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "a")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "b")
    assert credential().startswith("bearer token")
