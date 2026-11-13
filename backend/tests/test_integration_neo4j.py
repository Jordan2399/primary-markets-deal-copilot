"""Integration tests against a real Neo4j. They run only when TEST_NEO4J_URI is set.

    docker run -d --name neo4j-test -p 7688:7687 -e NEO4J_AUTH=neo4j/testpassword neo4j:5.26-community
    TEST_NEO4J_URI=bolt://localhost:7688 TEST_NEO4J_USER=neo4j TEST_NEO4J_PASSWORD=testpassword \
        pytest -m integration

WARNING: every test wipes the database it points at. Never use a database you care about.
"""

import os
from collections.abc import AsyncIterator
from datetime import date

import pytest

from app.allocation.repository import Neo4jAllocationRepository
from app.allocation.service import AllocationService
from app.audit.repository import Neo4jAuditRepository
from app.audit.service import AuditService
from app.core.errors import ConflictError, ForbiddenError
from app.core.security import CurrentUser, Role
from app.db.neo4j import Neo4jClient
from app.db.schema import ensure_schema
from app.deals.models import TaskStatus
from app.deals.repository import Neo4jDealRepository
from app.deals.service import DealService
from app.documents.repository import Neo4jDocumentRepository
from app.documents.service import DocumentService
from app.llm.fake import FakeLLM
from app.orderbook.repository import Neo4jOrderBookRepository
from app.orderbook.service import OrderBookService
from app.seed.runner import PLAYBOOK_DIR, seed_database
from app.termsheets.repository import Neo4jTermSheetRepository
from app.termsheets.service import TermSheetService
from tests.fakes import MARKETER, SYNDICATE

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not os.getenv("TEST_NEO4J_URI"), reason="TEST_NEO4J_URI is not set"),
]


@pytest.fixture
async def db() -> AsyncIterator[Neo4jClient]:
    client = Neo4jClient(
        os.environ["TEST_NEO4J_URI"],
        os.getenv("TEST_NEO4J_USER", "neo4j"),
        os.environ["TEST_NEO4J_PASSWORD"],
        os.getenv("TEST_NEO4J_DATABASE", "neo4j"),
    )
    yield client
    await client.close()


@pytest.fixture
async def seeded(db: Neo4jClient) -> Neo4jClient:
    llm = FakeLLM()
    docs = DocumentService(
        Neo4jDocumentRepository(db),
        llm,
        query_prefix="search_query: ",
        document_prefix="search_document: ",
    )
    await seed_database(db, docs, today=date.today(), reset=True)
    return db


async def test_schema_is_idempotent(db: Neo4jClient) -> None:
    first = await ensure_schema(db, 768)
    assert first == await ensure_schema(db, 768)


async def test_seed_creates_the_pipeline_and_is_repeatable(seeded: Neo4jClient) -> None:
    service = DealService(Neo4jDealRepository(seeded))
    deals = await service.list_deals()
    assert len(deals) == 12
    demo = await service.get_deal("D-DEMO-001")
    assert (demo.stage_code, demo.tasks_total, demo.tasks_done) == ("documentation", 34, 7)

    report = await seed_database(seeded, None, today=date.today())
    assert report.deals_created == 0 and report.deals_skipped == 12


async def test_advance_flow_against_neo4j(seeded: Neo4jClient) -> None:
    service = DealService(Neo4jDealRepository(seeded))
    with pytest.raises(ConflictError):
        await service.advance("D-DEMO-001", SYNDICATE)
    for key in ("d_sub", "d_opinions"):
        await service.update_task(f"D-DEMO-001:{key}", TaskStatus.DONE, SYNDICATE)
    assert (await service.advance("D-DEMO-001", SYNDICATE)).stage_code == "pre_marketing"
    events = await Neo4jAuditRepository(seeded).query(
        deal_id="D-DEMO-001", action_prefix=None, limit=10
    )
    assert events[0].action == "deal.advance"


async def test_dependency_rule_against_neo4j(seeded: Neo4jClient) -> None:
    service = DealService(Neo4jDealRepository(seeded))
    with pytest.raises(ConflictError):
        await service.update_task("D-DEMO-001:p_sop", TaskStatus.DONE, SYNDICATE)


async def test_vector_search_ranks_the_right_page_first(seeded: Neo4jClient) -> None:
    docs = DocumentService(
        Neo4jDocumentRepository(seeded), FakeLLM(), query_prefix="search_query: "
    )
    hits = await docs.search("how does allocation and scale back of orders work")
    assert hits and hits[0].doc_id == "playbook-allocation"
    assert len(list(PLAYBOOK_DIR.glob("*.md"))) >= 10


APPROVER = CurrentUser(name="demo.approver", role=Role.approver)
SYNDICATE_USER = CurrentUser(name="demo.syndicate", role=Role.syndicate)


async def test_seed_loads_investors_and_books_and_is_repeatable(seeded: Neo4jClient) -> None:
    repo = Neo4jOrderBookRepository(seeded)
    assert len(await repo.list_investors()) == 150
    assert await repo.count_orders("D-2026-007") > 30  # a deal at book building has a book
    assert await repo.count_orders("D-DEMO-001") == 0  # a deal at documentation does not
    report = await seed_database(seeded, None, today=date.today())
    assert report.books_created == 0


async def test_book_metrics_and_anomalies_against_neo4j(seeded: Neo4jClient) -> None:
    service = OrderBookService(
        Neo4jOrderBookRepository(seeded), DealService(Neo4jDealRepository(seeded))
    )
    book = await service.get_book("D-2026-007")
    assert book.metrics is not None and book.metrics.cover_ratio > 1
    assert {a.rule for a in book.anomalies} >= {"duplicate", "after_close"}


async def test_allocation_four_eyes_against_neo4j(seeded: Neo4jClient) -> None:
    deals = DealService(Neo4jDealRepository(seeded))
    book = OrderBookService(Neo4jOrderBookRepository(seeded), deals)
    service = AllocationService(
        Neo4jAllocationRepository(seeded), book, FakeLLM(chat_responses=["ok", "ok"])
    )
    proposal = await service.propose("D-2026-009", None, SYNDICATE_USER)
    assert proposal.total_allocated_k == proposal.deal_size_k
    with pytest.raises(ForbiddenError):
        await service.approve(proposal.id, SYNDICATE_USER)
    approved = await service.approve(proposal.id, APPROVER)
    assert approved.state == "APPROVED"
    with pytest.raises(ConflictError):
        await service.approve(proposal.id, APPROVER)


async def test_term_sheet_round_trip_against_neo4j(seeded: Neo4jClient) -> None:
    deals = DealService(Neo4jDealRepository(seeded))
    service = TermSheetService(
        Neo4jTermSheetRepository(seeded),
        deals,
        FakeLLM(fail=True),
        AuditService(Neo4jAuditRepository(seeded)),
    )
    sample = await service.make_sample("D-2026-008", "bad")
    doc = await service.extract(
        filename=None, content=None, text=sample.text, deal_id="D-2026-008", user=MARKETER
    )
    report = await service.validate(doc.document_id, None, MARKETER)
    assert report.has_errors and report.has_mismatch


async def test_demo_users_and_login_against_neo4j(seeded: Neo4jClient) -> None:
    from app.auth.repository import Neo4jUserRepository
    from app.auth.service import AuthService, LoginGuard
    from app.core.config import Settings
    from app.core.errors import UnauthorizedError

    first = await seed_database(seeded, None, today=date.today(), demo_password="Test-Passw0rd!")
    again = await seed_database(seeded, None, today=date.today(), demo_password="Other-Passw0rd!")
    assert first.users_created == 5 and again.users_created == 0  # never overwritten

    service = AuthService(
        Neo4jUserRepository(seeded),
        AuditService(Neo4jAuditRepository(seeded)),
        Settings(auth_mode="jwt", jwt_secret="s" * 40),
        LoginGuard(),
    )
    ok = await service.login("anna.syndicate", "Test-Passw0rd!")
    assert ok.user.role.value == "syndicate"
    with pytest.raises(UnauthorizedError):
        await service.login(
            "anna.syndicate", "Other-Passw0rd!"
        )  # the second seed did not change it


async def test_conversation_threads_against_neo4j(seeded: Neo4jClient) -> None:
    import uuid

    from app.conversations.repository import Neo4jConversationRepository
    from app.conversations.service import ConversationService
    from app.copilot.models import Source
    from app.core.errors import NotFoundError

    service = ConversationService(
        Neo4jConversationRepository(seeded), AuditService(Neo4jAuditRepository(seeded))
    )
    cid = uuid.uuid4().hex
    source = Source(id="S1", type="deal", ref="D-DEMO-001", title="Deal", snippet="x")
    for question in ("What is left?", "and who owns those?"):
        await service.save_turn(
            SYNDICATE,
            cid,
            "D-DEMO-001",
            question,
            "Answer [S1]",
            sources=[source],
            cited=["S1"],
            intent="deal",
            audit_id=None,
        )
    detail = await service.get(SYNDICATE, cid)
    assert [m.role for m in detail.messages] == ["user", "assistant", "user", "assistant"]
    assert detail.message_count == 4 and detail.title == "What is left?"
    assert detail.messages[1].sources[0].ref == "D-DEMO-001" and detail.messages[1].cited == ["S1"]

    _id, history, is_new = await service.context_for(SYNDICATE, cid)
    assert not is_new and [h.content for h in history][-2] == "and who owns those?"
    assert len(await service.list_mine(SYNDICATE)) == 1

    # another user: nothing visible, nothing writable
    with pytest.raises(NotFoundError):
        await service.get(MARKETER, cid)
    await service.save_turn(
        MARKETER, cid, None, "hijack", "x", sources=[], cited=[], intent="deal", audit_id=None
    )
    assert (await service.get(SYNDICATE, cid)).message_count == 4

    await service.delete(SYNDICATE, cid)
    with pytest.raises(NotFoundError):
        await service.get(SYNDICATE, cid)
