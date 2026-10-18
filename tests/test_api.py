"""API endpoint tests via FastAPI TestClient. No network, model, or token needed."""
import zipfile
from io import BytesIO

import pytest
from fastapi.testclient import TestClient

from api.main import app
from config import settings
from hackpack.engine.pitch_builder import build_fallback_pitch
from hackpack.models import HackathonBrief, RepoEvidence, TeamContext


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


def synthetic_evidence(**kwargs) -> RepoEvidence:
    defaults = dict(
        repo_url="https://github.com/acme/synthetic-demo",
        repo_name="synthetic-demo",
        description="A synthetic repository used only for tests",
        file_tree=["app/main.py", "tests/test_main.py"],
        source_excerpts={"app/main.py": "def main():\n    return 'demo pipeline ready'\n"},
        test_files=["tests/test_main.py"],
        test_excerpts={"tests/test_main.py": "def test_main():\n    assert True\n"},
        has_tests=True,
    )
    defaults.update(kwargs)
    return RepoEvidence(**defaults)


# --- health -----------------------------------------------------------------


def test_health_endpoint(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["app"] == "HackPack"
    assert body["version"] == settings.APP_VERSION
    assert "llm_model" in body


# --- analyze ----------------------------------------------------------------


def test_analyze_rejects_invalid_body(client):
    assert client.post("/api/analyze", json={}).status_code == 422
    assert client.post("/api/analyze", json={"repo_url": ""}).status_code == 422


def test_analyze_rejects_non_github_url(client):
    response = client.post("/api/analyze", json={"repo_url": "https://gitlab.com/owner/repo"})
    assert response.status_code == 400
    assert "github.com" in response.json()["detail"]


def test_analyze_mocked_repository(client, monkeypatch):
    import api.routes.analyze as analyze_module

    expected = synthetic_evidence()
    monkeypatch.setattr(analyze_module, "analyze_repository", lambda url: expected)
    response = client.post("/api/analyze", json={"repo_url": "https://github.com/acme/synthetic-demo"})
    assert response.status_code == 200
    body = response.json()
    assert body["evidence"]["repo_name"] == "synthetic-demo"
    assert body["summary"]["tests_detected"] is True


# --- pitch ------------------------------------------------------------------


def test_pitch_requires_evidence(client):
    response = client.post("/api/pitch", json={})
    assert response.status_code == 422


def test_pitch_uses_fallback_when_model_unavailable(client, monkeypatch):
    import api.routes.pitch as pitch_module

    class Unreachable:
        def generate_structured(self, *args, **kwargs):
            from hackpack.llm_client import LLMConfigurationError
            raise LLMConfigurationError("no local model running")

    monkeypatch.setattr(pitch_module, "LLMClient", Unreachable)
    response = client.post(
        "/api/pitch",
        json={
            "evidence": synthetic_evidence().model_dump(mode="json"),
            "brief": HackathonBrief(pitch_duration_minutes=3).model_dump(mode="json"),
            "team": TeamContext(problem_statement="Clinics lose hours to manual intake.").model_dump(mode="json"),
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["generation_mode"] == "fallback"
    assert len(body["deck"]["slides"]) == 6
    assert body["warnings"]


def test_pitch_returns_503_when_model_down_and_fallback_disabled(client, monkeypatch):
    import api.routes.pitch as pitch_module

    class Unreachable:
        def generate_structured(self, *args, **kwargs):
            from hackpack.llm_client import LLMConfigurationError
            raise LLMConfigurationError("no local model running")

    monkeypatch.setattr(pitch_module, "LLMClient", Unreachable)
    monkeypatch.setattr(settings, "LLM_FALLBACK_ENABLED", False)
    response = client.post(
        "/api/pitch",
        json={"evidence": synthetic_evidence().model_dump(mode="json")},
    )
    assert response.status_code == 503


def test_pitch_deck_is_verified(client, monkeypatch):
    import api.routes.pitch as pitch_module

    class Unreachable:
        def generate_structured(self, *args, **kwargs):
            from hackpack.llm_client import LLMConfigurationError
            raise LLMConfigurationError("offline")

    monkeypatch.setattr(pitch_module, "LLMClient", Unreachable)
    response = client.post(
        "/api/pitch",
        json={
            "evidence": synthetic_evidence().model_dump(mode="json"),
            "team": TeamContext(impact_claims=["We have 10,000 users"]).model_dump(mode="json"),
        },
    )
    assert response.status_code == 200
    deck = response.json()["deck"]
    flagged = deck["unverified_claims"]
    assert isinstance(flagged, list)


# --- generate ---------------------------------------------------------------


def test_generate_returns_valid_zip(client):
    evidence = synthetic_evidence()
    deck = build_fallback_pitch(evidence, HackathonBrief(pitch_duration_minutes=2), TeamContext())
    response = client.post(
        "/api/generate",
        json={
            "deck": deck.model_dump(mode="json"),
            "evidence": evidence.model_dump(mode="json"),
            "demo_duration_seconds": 120,
        },
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert "attachment" in response.headers["content-disposition"]
    with zipfile.ZipFile(BytesIO(response.content)) as archive:
        assert set(archive.namelist()) == {
            "pitch_deck.pptx", "pitch_script.md", "demo_checklist.md", "generation_summary.json",
        }


def test_generate_rejects_invalid_deck(client):
    response = client.post("/api/generate", json={"deck": {"project_name": "X"}})
    assert response.status_code == 422


def test_request_size_guard(client, monkeypatch):
    monkeypatch.setattr(settings, "MAX_REQUEST_BODY_BYTES", 10)
    response = client.post("/api/analyze", json={"repo_url": "https://github.com/owner/repo"})
    assert response.status_code == 413
