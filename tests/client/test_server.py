"""D75: Grupo Sazón's service: its own client and database, the key from the environment."""
from fastapi.testclient import TestClient

from sazon import server
from tests.support.fakes import ScriptedLLM


def test_the_sazon_service_starts_candidates_in_its_own_database(tmp_path, monkeypatch):
    monkeypatch.setenv("SAZON_DB", str(tmp_path / "s.db"))
    monkeypatch.setenv("SAZON_API_KEY", "k")
    http = TestClient(server.build_app(ScriptedLLM()))
    assert http.post("/candidates").status_code == 401
    started = http.post("/candidates", headers={"X-API-Key": "k"})
    assert started.status_code == 201 and "Sofía" in started.json()["reply"]
    assert (tmp_path / "s.db").exists()


def test_without_a_key_in_the_environment_the_service_refuses_to_start(tmp_path, monkeypatch):
    monkeypatch.setenv("SAZON_DB", str(tmp_path / "s.db"))
    monkeypatch.delenv("SAZON_API_KEY", raising=False)
    import pytest
    with pytest.raises(RuntimeError, match="SAZON_API_KEY"):
        server.build_app(ScriptedLLM())
