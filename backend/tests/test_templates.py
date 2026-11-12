"""The workflow definition is data, so these tests protect its rules."""

from datetime import date

import pytest

from app.deals.templates import (
    LAUNCH_POSITION,
    STAGE_BY_CODE,
    STAGES,
    TASK_TEMPLATES,
    add_years,
    initial_statuses,
    instantiate_tasks,
)


def test_stage_positions_are_consecutive() -> None:
    assert [s.position for s in STAGES] == list(range(1, len(STAGES) + 1))
    assert STAGES[LAUNCH_POSITION - 1].code == "launch"


def test_template_keys_are_unique() -> None:
    keys = [t.key for t in TASK_TEMPLATES]
    assert len(keys) == len(set(keys))


def test_every_template_uses_a_known_stage() -> None:
    assert all(t.stage_code in STAGE_BY_CODE for t in TASK_TEMPLATES)


def test_every_stage_has_a_blocking_task() -> None:
    for stage in STAGES:
        assert any(t.blocking for t in TASK_TEMPLATES if t.stage_code == stage.code), stage.code


def test_dependencies_point_backwards() -> None:
    """A task may only depend on a task listed before it, in the same or an earlier stage.

    This guarantees there are no cycles and that `initial_statuses` can mark tasks DONE in list order.
    """
    seen: dict[str, int] = {}
    for template in TASK_TEMPLATES:
        position = STAGE_BY_CODE[template.stage_code].position
        for dep in template.depends_on:
            assert dep in seen, f"{template.key} depends on {dep}, which is not listed before it"
            assert seen[dep] <= position, f"{template.key} depends on a later stage"
        seen[template.key] = position


def test_stages_appear_in_order() -> None:
    positions = [STAGE_BY_CODE[t.stage_code].position for t in TASK_TEMPLATES]
    assert positions == sorted(positions)


def test_instantiate_tasks_builds_ids_dates_and_dependencies() -> None:
    tasks, deps = instantiate_tasks("D-1", date(2026, 12, 1))
    assert len(tasks) == len(TASK_TEMPLATES) == 34
    by_key = {t.key: t for t in tasks}
    assert by_key["m_kyc"].id == "D-1:m_kyc"
    assert by_key["m_kyc"].due == "2026-11-10"  # launch minus 21 days
    assert by_key["l_ipt"].due == "2026-12-01"  # launch day
    assert ("D-1:d_terms", "D-1:d_prospectus") in deps
    assert all(t.status == "TODO" for t in tasks)


@pytest.mark.parametrize(
    ("stage", "done"), [("documentation", 2), ("pre_marketing", 5), ("launch", 0), ("booking", 5)]
)
def test_initial_statuses_never_leave_a_done_task_with_an_open_dependency(
    stage: str, done: int
) -> None:
    statuses = initial_statuses(stage, done)
    for template in TASK_TEMPLATES:
        if statuses.get(template.key) == "DONE":
            for dep in template.depends_on:
                assert statuses.get(dep) == "DONE", f"{template.key} is done but {dep} is not"


def test_initial_statuses_for_the_demo_deal() -> None:
    statuses = initial_statuses("documentation", 2)
    done = sorted(k for k, v in statuses.items() if v == "DONE")
    assert done == sorted(
        ["m_kyc", "m_letter", "m_structure", "m_ratings", "m_team", "d_prospectus", "d_terms"]
    )


def test_add_years_handles_leap_day() -> None:
    assert add_years(date(2028, 2, 29), 1) == date(2029, 2, 28)
    assert add_years(date(2026, 11, 3), 5) == date(2031, 11, 3)
