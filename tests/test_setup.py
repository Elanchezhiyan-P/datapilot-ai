"""Gemini setup: missing key, setting it from the chat page, saving to .env. No Gemini calls."""
import pytest
from fastapi.testclient import TestClient

from datapilot import api, gemini_client
from datapilot.config import ConfigError, set_values
from datapilot.gemini_client import GeminiError, GeminiNotConfiguredError, gemini_status
from tests.test_api import FakeAgent

FAKE_KEY = "AIzaTEST-not-a-real-key-1234"


@pytest.fixture
def no_gemini(monkeypatch: pytest.MonkeyPatch) -> None:
    # Present-but-empty, so load_dotenv() cannot fill them in from the real .env.
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("GEMINI_MODEL", "")


def _client(monkeypatch: pytest.MonkeyPatch, host: str) -> TestClient:
    monkeypatch.setattr(api, "_build_agent", FakeAgent)
    monkeypatch.setattr(api, "_build_fast", lambda agent: agent)
    return TestClient(api.app, client=(host, 50000))


# --- config.set_values -------------------------------------------------------

def test_set_values_replaces_and_appends_but_keeps_other_lines(tmp_path, monkeypatch) -> None:
    env = tmp_path / ".env"
    env.write_text("# comment\nAPP_NAME=DataPilot AI\nGEMINI_API_KEY=old\n", encoding="utf-8")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("GEMINI_MODEL", "")

    set_values({"GEMINI_API_KEY": "new", "GEMINI_MODEL": "m"}, save_to_env_file=True, env_file=env)

    assert env.read_text(encoding="utf-8").splitlines() == [
        "# comment", "APP_NAME=DataPilot AI", "GEMINI_API_KEY=new", "GEMINI_MODEL=m"]


def test_set_values_rejects_multi_line_values(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "")
    with pytest.raises(ConfigError):
        set_values({"GEMINI_API_KEY": "a\nDB_PASSWORD=x"}, save_to_env_file=False, env_file=tmp_path / ".env")


# --- gemini_client -----------------------------------------------------------

def test_calls_fail_clearly_without_a_key(no_gemini) -> None:
    with pytest.raises(GeminiNotConfiguredError, match="GEMINI_API_KEY and GEMINI_MODEL not set"):
        gemini_client.ask("hello")


def test_status_shows_only_the_last_four_characters(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", FAKE_KEY)
    monkeypatch.setenv("GEMINI_MODEL", "gemini-test")
    status = gemini_status()
    assert status == {"configured": True, "model": "gemini-test", "key_hint": "…1234"}


def test_verify_keeps_the_client_open_until_the_request_is_sent(monkeypatch) -> None:
    # Regression: genai.Client(...).models.get(...) on a temporary client failed with
    # "client has been closed" before any request, and was reported as a network error.
    events = []

    class FakeModels:
        def get(self, model):
            events.append(("get", model))

    class FakeClient:
        def __init__(self, api_key):
            self.models = FakeModels()

        def close(self):
            events.append(("close",))

    monkeypatch.setattr(gemini_client.genai, "Client", FakeClient)
    gemini_client.verify_credentials(FAKE_KEY, "gemini-test")
    assert events == [("get", "gemini-test"), ("close",)]


# --- API ---------------------------------------------------------------------

def test_status_endpoint_reports_not_configured(monkeypatch, no_gemini) -> None:
    with _client(monkeypatch, "127.0.0.1") as client:
        body = client.get("/setup/status").json()
    assert body["gemini_configured"] is False and body["key_hint"] is None


def test_ask_without_key_returns_setup_hint(monkeypatch, no_gemini) -> None:
    class NotConfiguredAgent(FakeAgent):
        def run(self, question, history=None):
            gemini_client.ask(question)   # raises GeminiNotConfiguredError

    monkeypatch.setattr(api, "_build_agent", NotConfiguredAgent)
    monkeypatch.setattr(api, "_build_fast", lambda agent: agent)
    with TestClient(api.app, client=("127.0.0.1", 50000)) as client:
        response = client.post("/ask", json={"question": "How many students?"})
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "gemini_not_configured"


def test_setting_the_key_from_this_computer(monkeypatch, no_gemini) -> None:
    checked = []
    monkeypatch.setattr(api, "verify_credentials", lambda key, model: checked.append((key, model)))

    with _client(monkeypatch, "127.0.0.1") as client:
        response = client.post("/setup/gemini", json={
            "api_key": f"  {FAKE_KEY} ", "model": "gemini-test", "save_to_env_file": False})

    assert response.status_code == 200
    assert checked == [(FAKE_KEY, "gemini-test")]
    body = response.json()
    assert body["gemini_configured"] is True and body["key_hint"] == "…1234"
    assert FAKE_KEY not in response.text   # the key is never sent back


def test_setting_the_key_from_another_computer_is_refused(monkeypatch, no_gemini) -> None:
    monkeypatch.setattr(api, "verify_credentials", lambda key, model: pytest.fail("must not be checked"))
    with _client(monkeypatch, "192.168.1.50") as client:
        response = client.post("/setup/gemini", json={"api_key": FAKE_KEY, "model": "m-test",
                                                       "save_to_env_file": False})
    assert response.status_code == 403
    assert gemini_status()["configured"] is False


def test_rejected_key_is_not_applied_or_echoed(monkeypatch, no_gemini) -> None:
    def reject(key, model):
        raise GeminiError("Google rejected this API key. Copy it again from Google AI Studio.")

    monkeypatch.setattr(api, "verify_credentials", reject)
    with _client(monkeypatch, "127.0.0.1") as client:
        response = client.post("/setup/gemini", json={"api_key": FAKE_KEY, "model": "m-test",
                                                       "save_to_env_file": False})
    assert response.status_code == 400
    assert FAKE_KEY not in response.text
    assert gemini_status()["configured"] is False
