"""Health endpoint tests. Dependencies are replaced with fakes, so no services are needed."""

import pytest
from fastapi.testclient import TestClient

from app.health import service
from app.health.service import CheckResult
from app.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_live_is_always_ok(client: TestClient) -> None:
    response = client.get("/api/v1/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_ok_when_dependencies_ok(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_neo4j(_settings: object) -> CheckResult:
        return CheckResult(ok=True, detail="connected")

    async def fake_ollama(_settings: object) -> CheckResult:
        return CheckResult(ok=True, detail="reachable, models present")

    monkeypatch.setattr(service, "check_neo4j", fake_neo4j)
    monkeypatch.setattr(service, "check_ollama", fake_ollama)

    body = client.get("/api/v1/health").json()
    assert body["status"] == "ok"
    assert body["dependencies"]["neo4j"]["ok"] is True
    assert body["dependencies"]["ollama"]["ok"] is True


def test_health_degraded_when_a_dependency_is_down(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_neo4j(_settings: object) -> CheckResult:
        return CheckResult(ok=False, detail="ServiceUnavailable: down")

    async def fake_ollama(_settings: object) -> CheckResult:
        return CheckResult(ok=True, detail="reachable, models present")

    monkeypatch.setattr(service, "check_neo4j", fake_neo4j)
    monkeypatch.setattr(service, "check_ollama", fake_ollama)

    response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert body["dependencies"]["neo4j"]["ok"] is False


@pytest.mark.parametrize(
    ("installed", "wanted", "expected"),
    [
        ({"qwen2.5:7b-instruct"}, "qwen2.5:7b-instruct", True),
        ({"nomic-embed-text:latest"}, "nomic-embed-text", True),
        ({"llama3.1:8b"}, "qwen2.5:7b-instruct", False),
        ({"qwen2.5:3b"}, "qwen2.5:7b-instruct", False),
    ],
)
def test_model_name_matching(installed: set[str], wanted: str, expected: bool) -> None:
    assert service._has_model(installed, wanted) is expected
