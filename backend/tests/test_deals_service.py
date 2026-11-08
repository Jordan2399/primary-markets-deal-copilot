"""Business rules of the deal workflow, tested against the in-memory repository."""

from datetime import date, timedelta

import pytest

from app.core.errors import ConflictError, NotFoundError
from app.deals.models import CreateDealRequest, TaskStatus
from app.deals.service import DealService
from tests.fakes import ADMIN, MARKETER, SYNDICATE, FakeDealRepository, add_deal


def new_request(**overrides: object) -> CreateDealRequest:
    data: dict[str, object] = {
        "issuer_id": "ISS-002",
        "name": "Aurelia EUR 500m 10Y",
        "currency": "EUR",
        "size_mm": 500,
        "tenor_years": 10,
        "format": "Domestic",
        "launch_date": date.today() + timedelta(days=30),
    }
    data.update(overrides)
    return CreateDealRequest(**data)  # type: ignore[arg-type]


@pytest.fixture
def repo() -> FakeDealRepository:
    return FakeDealRepository()


@pytest.fixture
def service(repo: FakeDealRepository) -> DealService:
    return DealService(repo)


# ----------------------------------------------------------------------- create


async def test_create_deal_starts_at_mandate_with_the_full_checklist(
    service: DealService, repo: FakeDealRepository
) -> None:
    deal = await service.create_deal(new_request(), MARKETER)
    assert deal.id.startswith("D-")
    assert deal.stage_code == "mandate"
    assert deal.tasks_total == 34
    assert deal.tasks_done == 0
    assert deal.tranches[0].tenor_years == 10
    assert deal.tranches[0].maturity is not None
    event = repo.events[-1]
    assert (event.action, event.actor, event.role) == ("deal.create", "mia.marketer", "marketer")
    assert event.deal_id == deal.id


async def test_create_deal_rejects_past_launch_dates(service: DealService) -> None:
    with pytest.raises(ConflictError, match="past"):
        await service.create_deal(
            new_request(launch_date=date.today() - timedelta(days=1)), MARKETER
        )


async def test_create_deal_rejects_unknown_issuer(service: DealService) -> None:
    with pytest.raises(NotFoundError, match="ISS-999"):
        await service.create_deal(new_request(issuer_id="ISS-999"), MARKETER)


# ----------------------------------------------------------------------- tasks


async def test_task_cannot_be_done_while_a_dependency_is_open(
    service: DealService, repo: FakeDealRepository
) -> None:
    await add_deal(repo, stage_code="documentation", done_in_stage=0)
    # d_terms depends on d_prospectus, which is still TODO
    with pytest.raises(ConflictError) as error:
        await service.update_task("D-DEMO-001:d_terms", TaskStatus.DONE, SYNDICATE)
    assert error.value.details["open_dependencies"][0]["id"] == "D-DEMO-001:d_prospectus"


async def test_task_can_be_done_once_dependencies_are_done(
    service: DealService, repo: FakeDealRepository
) -> None:
    await add_deal(repo, stage_code="documentation", done_in_stage=0)
    await service.update_task("D-DEMO-001:d_prospectus", TaskStatus.DONE, SYNDICATE)
    task = await service.update_task("D-DEMO-001:d_terms", TaskStatus.DONE, SYNDICATE)
    assert task.status is TaskStatus.DONE


async def test_task_update_writes_an_audit_event_with_before_and_after(
    service: DealService, repo: FakeDealRepository
) -> None:
    await add_deal(repo)
    before = len(repo.events)
    await service.update_task("D-DEMO-001:d_sub", TaskStatus.IN_PROGRESS, SYNDICATE)
    assert len(repo.events) == before + 1
    event = repo.events[-1]
    assert event.action == "task.update"
    assert event.details == {
        "title": "Subscription and fiscal agency agreements agreed",
        "from": "TODO",
        "to": "IN_PROGRESS",
    }


async def test_setting_the_same_status_changes_nothing(
    service: DealService, repo: FakeDealRepository
) -> None:
    await add_deal(repo)
    before = len(repo.events)
    await service.update_task("D-DEMO-001:d_sub", TaskStatus.TODO, SYNDICATE)
    assert len(repo.events) == before


async def test_unknown_task_is_not_found(service: DealService) -> None:
    with pytest.raises(NotFoundError):
        await service.update_task("nope", TaskStatus.DONE, SYNDICATE)


# ----------------------------------------------------------------------- advance


async def test_advance_is_blocked_by_open_blocking_tasks(
    service: DealService, repo: FakeDealRepository
) -> None:
    await add_deal(repo)  # documentation, d_sub and d_opinions are open and blocking
    with pytest.raises(ConflictError) as error:
        await service.advance("D-DEMO-001", SYNDICATE)
    blockers = {b["key"] for b in error.value.details["blockers"]}
    assert blockers == {"d_sub", "d_opinions"}
    assert (await service.get_deal("D-DEMO-001")).stage_code == "documentation"


async def test_non_blocking_tasks_do_not_stop_advance(
    service: DealService, repo: FakeDealRepository
) -> None:
    await add_deal(repo)  # d_listing is not blocking and stays open
    for key in ("d_sub", "d_opinions"):
        await service.update_task(f"D-DEMO-001:{key}", TaskStatus.DONE, SYNDICATE)
    deal = await service.advance("D-DEMO-001", SYNDICATE)
    assert deal.stage_code == "pre_marketing"
    event = repo.events[-1]
    assert (event.action, event.details) == (
        "deal.advance",
        {"from": "documentation", "to": "pre_marketing"},
    )


async def test_advance_from_the_last_stage_is_refused(
    service: DealService, repo: FakeDealRepository
) -> None:
    await add_deal(repo, stage_code="booking", done_in_stage=5)
    with pytest.raises(ConflictError, match="last stage"):
        await service.advance("D-DEMO-001", SYNDICATE)
    assert (await service.get_deal("D-DEMO-001")).is_complete


async def test_advance_unknown_deal(service: DealService) -> None:
    with pytest.raises(NotFoundError):
        await service.advance("D-NOPE", ADMIN)


# ----------------------------------------------------------------------- readiness


async def test_launch_readiness_for_the_demo_deal(
    service: DealService, repo: FakeDealRepository
) -> None:
    await add_deal(repo)
    readiness = await service.launch_readiness("D-DEMO-001")
    assert readiness.deal.tasks_done == 7  # five mandate tasks plus two documentation tasks
    assert readiness.ready_to_launch is False
    assert readiness.open_before_launch == 11  # 3 documentation + 5 pre-marketing + 3 launch
    assert readiness.blocking_open_before_launch == 8
    assert len(readiness.open_tasks) == 27


async def test_ready_to_launch_when_pre_launch_blocking_tasks_are_done(
    service: DealService, repo: FakeDealRepository
) -> None:
    await add_deal(repo, stage_code="launch", done_in_stage=0)
    readiness = await service.launch_readiness("D-DEMO-001")
    assert readiness.ready_to_launch is True  # only launch-stage tasks remain
    assert readiness.open_before_launch == 3


async def test_unknown_deal_readiness(service: DealService) -> None:
    with pytest.raises(NotFoundError):
        await service.launch_readiness("D-NOPE")
