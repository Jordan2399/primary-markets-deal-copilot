"""Dependency wiring: how services are built for each request.

Tests replace these functions with `app.dependency_overrides` so no database is needed.
"""

from typing import Annotated, cast

from fastapi import Depends, Request

from app.allocation.repository import Neo4jAllocationRepository
from app.allocation.service import AllocationService
from app.audit.repository import Neo4jAuditRepository
from app.audit.service import AuditService
from app.auth.repository import Neo4jUserRepository
from app.auth.service import AuthService
from app.conversations.repository import Neo4jConversationRepository
from app.conversations.service import ConversationService
from app.copilot.service import CopilotService
from app.core.config import Settings, get_settings
from app.db.neo4j import Neo4jClient
from app.deals.repository import Neo4jDealRepository
from app.deals.service import DealService
from app.documents.repository import Neo4jDocumentRepository
from app.documents.service import DocumentService
from app.llm.base import LLMProvider
from app.orderbook.repository import Neo4jOrderBookRepository
from app.orderbook.service import OrderBookService
from app.termsheets.repository import Neo4jTermSheetRepository
from app.termsheets.service import TermSheetService


def get_db(request: Request) -> Neo4jClient:
    return cast(Neo4jClient, request.app.state.neo4j)


def get_llm(request: Request) -> LLMProvider:
    return cast(LLMProvider, request.app.state.llm)


Db = Annotated[Neo4jClient, Depends(get_db)]
Llm = Annotated[LLMProvider, Depends(get_llm)]
Config = Annotated[Settings, Depends(get_settings)]


def get_deal_service(db: Db) -> DealService:
    return DealService(Neo4jDealRepository(db))


def get_audit_service(db: Db) -> AuditService:
    return AuditService(Neo4jAuditRepository(db))


def get_document_service(db: Db, llm: Llm, settings: Config) -> DocumentService:
    return DocumentService(
        Neo4jDocumentRepository(db),
        llm,
        query_prefix=settings.query_prefix,
        document_prefix=settings.document_prefix,
        default_k=settings.retrieval_k,
        dimensions=settings.embed_dimensions,
    )


# Day 2b wiring: build each service with its Neo4j repository. Tests replace these functions
# through dependency_overrides to use in-memory fakes instead.
def get_auth_service(
    db: Db, audit: Annotated[AuditService, Depends(get_audit_service)], settings: Config
) -> AuthService:
    # Settings carry the JWT secret and token lifetime used when issuing tokens.
    return AuthService(Neo4jUserRepository(db), audit, settings)


def get_conversation_service(
    db: Db, audit: Annotated[AuditService, Depends(get_audit_service)]
) -> ConversationService:
    return ConversationService(Neo4jConversationRepository(db), audit)


def get_copilot_service(
    deals: Annotated[DealService, Depends(get_deal_service)],
    docs: Annotated[DocumentService, Depends(get_document_service)],
    audit: Annotated[AuditService, Depends(get_audit_service)],
    threads: Annotated[ConversationService, Depends(get_conversation_service)],
    llm: Llm,
) -> CopilotService:
    # `threads` lets the Copilot load history and save each turn.
    return CopilotService(deals, docs, llm, audit, threads)


def get_orderbook_service(
    db: Db, deals: Annotated[DealService, Depends(get_deal_service)]
) -> OrderBookService:
    return OrderBookService(Neo4jOrderBookRepository(db), deals)


def get_allocation_service(
    db: Db, book: Annotated[OrderBookService, Depends(get_orderbook_service)], llm: Llm
) -> AllocationService:
    return AllocationService(Neo4jAllocationRepository(db), book, llm)


def get_termsheet_service(
    db: Db,
    deals: Annotated[DealService, Depends(get_deal_service)],
    audit: Annotated[AuditService, Depends(get_audit_service)],
    llm: Llm,
) -> TermSheetService:
    return TermSheetService(Neo4jTermSheetRepository(db), deals, llm, audit)
