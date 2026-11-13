"""Shared fixtures: an API app wired to in-memory fakes, so no database or GPU is needed."""

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.allocation.service import AllocationService
from app.audit.service import AuditService
from app.auth.service import AuthService, LoginGuard
from app.conversations.service import ConversationService
from app.core.config import Settings, get_settings
from app.deals.service import DealService
from app.deps import (
    get_allocation_service,
    get_audit_service,
    get_auth_service,
    get_conversation_service,
    get_deal_service,
    get_document_service,
    get_llm,
    get_orderbook_service,
    get_termsheet_service,
)
from app.documents.service import DocumentService
from app.llm.fake import FakeLLM
from app.main import create_app
from app.orderbook.service import OrderBookService
from app.termsheets.service import TermSheetService
from tests.fakes import (
    FakeAllocationRepository,
    FakeAuditRepository,
    FakeConversationRepository,
    FakeDealRepository,
    FakeOrderBookRepository,
    FakeTermSheetRepository,
    FakeUserRepository,
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
    book_repo: FakeOrderBookRepository
    alloc_repo: FakeAllocationRepository
    ts_repo: FakeTermSheetRepository
    users: FakeUserRepository
    threads: FakeConversationRepository
    settings: Settings


JWT_SECRET = "test-secret-test-secret-test-secret-0123456789"


def build_env(llm: FakeLLM, auth_mode: str = "demo") -> Env:
    """`demo` trusts the X-Demo headers (used by most tests); `jwt` needs a real login."""
    settings = Settings(auth_mode=auth_mode, jwt_secret=JWT_SECRET)  # type: ignore[arg-type]
    repo = FakeDealRepository()
    docs_repo = InMemoryDocumentRepository()
    audit = FakeAuditRepository(repo.events)
    docs = DocumentService(
        docs_repo, llm, query_prefix="search_query: ", document_prefix="search_document: "
    )
    book_repo = FakeOrderBookRepository(repo.events)
    alloc_repo = FakeAllocationRepository(repo.events)
    ts_repo = FakeTermSheetRepository(repo.events)
    users = FakeUserRepository()
    threads = FakeConversationRepository(repo.events)
    guard = LoginGuard()
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_deal_service] = lambda: DealService(repo)
    app.dependency_overrides[get_audit_service] = lambda: AuditService(audit)
    app.dependency_overrides[get_document_service] = lambda: docs
    app.dependency_overrides[get_llm] = lambda: llm

    def deals() -> DealService:
        return DealService(repo)

    def book() -> OrderBookService:
        return OrderBookService(book_repo, deals())

    thread_service = ConversationService(threads, AuditService(audit))
    app.dependency_overrides[get_conversation_service] = lambda: thread_service
    app.dependency_overrides[get_auth_service] = lambda: AuthService(
        users, AuditService(audit), settings, guard
    )
    app.dependency_overrides[get_orderbook_service] = book
    app.dependency_overrides[get_allocation_service] = lambda: AllocationService(
        alloc_repo, book(), llm
    )
    app.dependency_overrides[get_termsheet_service] = lambda: TermSheetService(
        ts_repo, deals(), llm, AuditService(audit)
    )
    return Env(
        app,
        TestClient(app),
        repo,
        docs_repo,
        llm,
        book_repo,
        alloc_repo,
        ts_repo,
        users,
        threads,
        settings,
    )


@pytest.fixture
def env() -> Iterator[Env]:
    yield build_env(FakeLLM())
