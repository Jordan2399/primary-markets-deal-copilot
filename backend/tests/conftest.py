"""Shared fixtures: an API app wired to in-memory fakes, so no database or GPU is needed."""

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.audit.service import AuditService
from app.deals.service import DealService
from app.deps import get_audit_service, get_deal_service, get_document_service, get_llm
from app.documents.service import DocumentService
from app.llm.fake import FakeLLM
from app.main import create_app
from tests.fakes import (
    FakeAuditRepository,
    FakeDealRepository,
    InMemoryDocumentRepository,
)

PLAYBOOK = Path(__file__).resolve().parents[1] / "app" / "seed" / "playbook"


@dataclass
class Env:
    app: FastAPI
    client: TestClient
    repo: FakeDealRepository
    docs_repo: InMemoryDocumentRepository
    llm: FakeLLM


def build_env(llm: FakeLLM) -> Env:
    repo = FakeDealRepository()
    docs_repo = InMemoryDocumentRepository()
    audit = FakeAuditRepository(repo.events)
    docs = DocumentService(
        docs_repo, llm, query_prefix="search_query: ", document_prefix="search_document: "
    )
    app = create_app()
    app.dependency_overrides[get_deal_service] = lambda: DealService(repo)
    app.dependency_overrides[get_audit_service] = lambda: AuditService(audit)
    app.dependency_overrides[get_document_service] = lambda: docs
    app.dependency_overrides[get_llm] = lambda: llm
    return Env(app, TestClient(app), repo, docs_repo, llm)


@pytest.fixture
def env() -> Iterator[Env]:
    yield build_env(FakeLLM())
