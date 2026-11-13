"""Load the synthetic dataset into Neo4j.

Behaviour you can rely on:
- Reference data (stages, issuers, playbook pages) is upserted every time, so it is safe to re-run.
- A deal that already exists is NEVER touched, so your edits to tasks and stages survive a re-run.
- `reset=True` deletes everything first. That is for development only.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from pathlib import Path

import structlog
from neo4j import AsyncManagedTransaction

from app.audit.models import AuditEvent, build_event
from app.audit.repository import write_in_tx
from app.auth.models import DEMO_USERS, User
from app.auth.repository import Neo4jUserRepository
from app.core.passwords import hash_password
from app.core.security import CurrentUser, Role
from app.db.neo4j import Neo4jClient
from app.db.schema import ensure_schema
from app.deals.models import NewDeal
from app.deals.repository import create_deal_in_tx
from app.deals.templates import (
    STAGES,
    NewTask,
    add_years,
    initial_statuses,
    instantiate_tasks,
)
from app.documents.service import DocumentService
from app.investors.generator import build_investors
from app.orderbook.generator import default_params, generate_orders
from app.orderbook.repository import Neo4jOrderBookRepository
from app.seed.data import DEALS, ISSUERS, deal_name, launch_date, pricing_terms

log = structlog.get_logger()

PLAYBOOK_DIR = Path(__file__).parent / "playbook"
SEED_USER = CurrentUser(name="seed", role=Role.admin)

UPSERT_STAGES = """
UNWIND $stages AS s
MERGE (n:Stage {code: s.code})
SET n.name = s.name, n.position = s.position
"""

LINK_STAGES = """
MATCH (a:Stage), (b:Stage)
WHERE b.position = a.position + 1
MERGE (a)-[:NEXT]->(b)
"""

UPSERT_ISSUERS = """
UNWIND $issuers AS i
MERGE (n:Issuer {id: i.id})
SET n.name = i.name, n.sector = i.sector, n.country = i.country, n.rating_band = i.rating_band,
    n.synthetic = true
"""

EXISTING_DEALS = "MATCH (d:Deal) RETURN d.id AS id"


@dataclass
class SeedReport:
    stages: int = 0
    issuers: int = 0
    deals_created: int = 0
    deals_skipped: int = 0
    users_created: int = 0  # how many demo users this run added (0 on a repeat run)
    investors: int = 0
    books_created: int = 0
    playbook_pages: int = 0
    playbook_chunks: int = 0


async def _create_deal(
    db: Neo4jClient,
    deal: NewDeal,
    stage_code: str,
    tasks: list[NewTask],
    deps: list[tuple[str, str]],
    event: AuditEvent,
) -> bool:
    """Create one deal with its tasks and audit event in a single transaction."""

    async def work(tx: AsyncManagedTransaction) -> bool:
        if not await create_deal_in_tx(tx, deal, stage_code, tasks, deps):
            return False
        await write_in_tx(tx, event)
        return True

    return await db.execute_write(work)


async def _seed_users(db: Neo4jClient, password: str, report: SeedReport) -> None:
    """Create the demo users. An existing user is never changed, so a password you set stays."""
    repo = Neo4jUserRepository(db)
    # One hash is reused for all demo users: they share one development password.
    hashed = hash_password(password)
    for username, display_name, role in DEMO_USERS:
        user = User(username=username, display_name=display_name, role=role, password_hash=hashed)
        # create_if_missing returns True only when the user did not exist before.
        if await repo.create_if_missing(user):
            report.users_created += 1


BOOK_STAGES = ("book_building", "pricing", "allocation", "booking")


async def _seed_books(db: Neo4jClient, today: date, report: SeedReport) -> None:
    """Load the 150 investors, then give every deal that has reached book building an order book.

    A deal that already has orders is left alone, so re-running the seed keeps your edits.
    """
    repo = Neo4jOrderBookRepository(db)
    investors = build_investors()
    await repo.upsert_investors(investors)
    report.investors = len(investors)

    for index, spec in enumerate(d for d in DEALS if d.stage_code in BOOK_STAGES):
        if await repo.count_orders(spec.deal_id) > 0:
            continue
        launch = datetime.combine(launch_date(spec, today), time(0), tzinfo=UTC)
        params = default_params(spec.deal_id, launch)
        orders = generate_orders(
            deal_id=spec.deal_id,
            deal_size_k=spec.size_mm * 1000,
            investors=investors,
            params=params,
            seed=1,
            target_cover=2.2 + 0.4 * index,
            anomalies=4,
        )
        event = build_event(
            SEED_USER,
            "orderbook.simulate",
            "deal",
            spec.deal_id,
            deal_id=spec.deal_id,
            details={"seeded": True, "orders_created": len(orders)},
        )
        await repo.save_book(spec.deal_id, params, orders, replace=True, event=event)
        report.books_created += 1


async def seed_database(
    db: Neo4jClient,
    docs: DocumentService | None,
    *,
    today: date,
    embed_dimensions: int = 768,
    reset: bool = False,
    demo_password: str | None = None,  # None = do not create demo users
) -> SeedReport:
    report = SeedReport()

    if reset:
        await db.write("MATCH (n) DETACH DELETE n")
        log.info("seed_reset")

    await ensure_schema(db, embed_dimensions)

    await db.write(
        UPSERT_STAGES,
        {"stages": [{"code": s.code, "name": s.name, "position": s.position} for s in STAGES]},
    )
    await db.write(LINK_STAGES)
    report.stages = len(STAGES)

    await db.write(
        UPSERT_ISSUERS,
        {
            "issuers": [
                {
                    "id": i.id,
                    "name": i.name,
                    "sector": i.sector,
                    "country": i.country,
                    "rating_band": i.rating_band,
                }
                for i in ISSUERS
            ]
        },
    )
    report.issuers = len(ISSUERS)

    existing = {r["id"] for r in await db.read(EXISTING_DEALS)}
    for spec in DEALS:
        if spec.deal_id in existing:
            report.deals_skipped += 1
            continue
        launch = launch_date(spec, today)
        coupon, isin = pricing_terms(spec)
        deal = NewDeal(
            deal_id=spec.deal_id,
            issuer_id=spec.issuer_id,
            name=deal_name(spec),
            currency=spec.currency,
            size_mm=spec.size_mm,
            launch_date=launch,
            tranche_id=f"{spec.deal_id}-T1",
            tenor_years=spec.tenor_years,
            format=spec.format,
            maturity=add_years(launch, spec.tenor_years),
            coupon=coupon,
            isin=isin,
        )
        tasks, deps = instantiate_tasks(
            spec.deal_id, launch, initial_statuses(spec.stage_code, spec.done_in_stage)
        )
        event = build_event(
            SEED_USER,
            "deal.create",
            "deal",
            spec.deal_id,
            deal_id=spec.deal_id,
            details={"name": deal.name, "seeded": True, "stage": spec.stage_code},
        )

        if not await _create_deal(db, deal, spec.stage_code, tasks, deps, event):
            raise RuntimeError(f"Could not create {spec.deal_id}: issuer or stage missing.")
        report.deals_created += 1

    # Users are seeded last and only when a password was provided by the caller.
    if demo_password:
        await _seed_users(db, demo_password, report)
    await _seed_books(db, today, report)

    if docs is not None:
        for path in sorted(PLAYBOOK_DIR.glob("*.md")):
            report.playbook_chunks += await docs.ingest_markdown(path, kind="playbook")
            report.playbook_pages += 1
        await db.write("CALL db.awaitIndexes(30)")

    log.info("seed_done", **report.__dict__)
    return report
