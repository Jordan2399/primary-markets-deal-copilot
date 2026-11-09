"""The issuance process as data: eight stages and the checklist of tasks inside them.

This is the single source of truth for the workflow. To add a stage or a task, edit this
file (and the tests will tell you if you break an ordering rule). Nothing else in the code
hard-codes stage names or task titles.

The process here is a generic, illustrative new-issue workflow. It is not any bank's policy.
"""

from dataclasses import dataclass
from datetime import date, timedelta


@dataclass(frozen=True)
class StageDef:
    code: str
    name: str
    position: int


STAGES: tuple[StageDef, ...] = (
    StageDef("mandate", "Mandate", 1),
    StageDef("documentation", "Documentation", 2),
    StageDef("pre_marketing", "Pre-marketing", 3),
    StageDef("launch", "Launch", 4),
    StageDef("book_building", "Book building", 5),
    StageDef("pricing", "Pricing", 6),
    StageDef("allocation", "Allocation", 7),
    StageDef("booking", "Booking", 8),
)

STAGE_BY_CODE = {s.code: s for s in STAGES}
STAGE_COUNT = len(STAGES)
FIRST_STAGE = STAGES[0].code
LAUNCH_POSITION = STAGE_BY_CODE["launch"].position  # "before launch" = positions up to this one


@dataclass(frozen=True)
class TaskTemplate:
    key: str
    stage_code: str
    title: str
    owner_role: str
    blocking: bool  # a blocking task must be DONE before the deal may leave its stage
    offset_days: int  # due date = launch date + offset (negative = before launch)
    depends_on: tuple[str, ...] = ()


TASK_TEMPLATES: tuple[TaskTemplate, ...] = (
    # Mandate
    TaskTemplate(
        "m_kyc", "mandate", "Issuer KYC and onboarding completed", "compliance", True, -21
    ),
    TaskTemplate("m_letter", "mandate", "Mandate letter signed by the issuer", "dcm", True, -20),
    TaskTemplate(
        "m_structure",
        "mandate",
        "Deal structure agreed (currency, tenor, format)",
        "dcm",
        True,
        -19,
        ("m_letter",),
    ),
    TaskTemplate(
        "m_ratings",
        "mandate",
        "Issuer ratings confirmed with the rating agencies",
        "dcm",
        False,
        -19,
    ),
    TaskTemplate(
        "m_team", "mandate", "Syndicate and transaction team staffed", "syndicate", False, -18
    ),
    # Documentation
    TaskTemplate(
        "d_prospectus",
        "documentation",
        "Base prospectus or programme update approved",
        "legal",
        True,
        -14,
        ("m_structure",),
    ),
    TaskTemplate(
        "d_terms",
        "documentation",
        "Draft final terms prepared",
        "legal",
        True,
        -10,
        ("d_prospectus",),
    ),
    TaskTemplate(
        "d_sub",
        "documentation",
        "Subscription and fiscal agency agreements agreed",
        "legal",
        True,
        -9,
        ("m_structure",),
    ),
    TaskTemplate(
        "d_listing",
        "documentation",
        "Listing application submitted",
        "ops",
        False,
        -8,
        ("d_prospectus",),
    ),
    TaskTemplate(
        "d_opinions",
        "documentation",
        "Legal opinions and comfort letter arrangements confirmed",
        "legal",
        True,
        -7,
        ("d_sub",),
    ),
    # Pre-marketing
    TaskTemplate(
        "p_window",
        "pre_marketing",
        "Issuance window checked (blackouts, holidays, market conditions)",
        "syndicate",
        True,
        -5,
    ),
    TaskTemplate(
        "p_soundings",
        "pre_marketing",
        "Investor soundings completed and feedback logged",
        "syndicate",
        False,
        -4,
    ),
    TaskTemplate(
        "p_marketing",
        "pre_marketing",
        "Marketing material and market update finalised",
        "dcm",
        False,
        -3,
    ),
    TaskTemplate(
        "p_sop",
        "pre_marketing",
        "Sales desks briefed and initial price thoughts prepared",
        "syndicate",
        True,
        -3,
        ("p_window",),
    ),
    TaskTemplate(
        "p_approval",
        "pre_marketing",
        "Internal commitment and compliance approvals obtained",
        "compliance",
        True,
        -2,
        ("d_terms",),
    ),
    # Launch
    TaskTemplate(
        "l_announce",
        "launch",
        "Launch announcement approved by issuer and compliance",
        "dcm",
        True,
        0,
        ("p_approval",),
    ),
    TaskTemplate(
        "l_ipt",
        "launch",
        "Initial price thoughts released to investors",
        "syndicate",
        True,
        0,
        ("l_announce",),
    ),
    TaskTemplate(
        "l_book",
        "launch",
        "Order book opened and order capture checked",
        "syndicate",
        True,
        0,
        ("l_ipt",),
    ),
    # Book building
    TaskTemplate(
        "b_updates",
        "book_building",
        "Book updates sent to the issuer at agreed intervals",
        "syndicate",
        False,
        0,
    ),
    TaskTemplate(
        "b_quality",
        "book_building",
        "Order book quality checks completed (duplicates, inflated orders)",
        "syndicate",
        True,
        0,
    ),
    TaskTemplate(
        "b_guidance",
        "book_building",
        "Pricing guidance revised and communicated",
        "syndicate",
        False,
        0,
    ),
    TaskTemplate(
        "b_close",
        "book_building",
        "Book closed and final size agreed with the issuer",
        "syndicate",
        True,
        0,
        ("b_quality",),
    ),
    # Pricing
    TaskTemplate(
        "pr_spread",
        "pricing",
        "Final spread and coupon agreed with the issuer",
        "syndicate",
        True,
        0,
    ),
    TaskTemplate(
        "pr_terms", "pricing", "Pricing term sheet released", "syndicate", True, 0, ("pr_spread",)
    ),
    TaskTemplate(
        "pr_final", "pricing", "Final terms signed off by legal", "legal", True, 0, ("pr_spread",)
    ),
    # Allocation
    TaskTemplate(
        "a_principles",
        "allocation",
        "Allocation principles agreed with the issuer",
        "syndicate",
        True,
        1,
    ),
    TaskTemplate(
        "a_proposal",
        "allocation",
        "Allocation proposal prepared and checked (four-eyes)",
        "syndicate",
        True,
        1,
        ("a_principles",),
    ),
    TaskTemplate(
        "a_approval",
        "allocation",
        "Issuer approves the allocation",
        "dcm",
        True,
        1,
        ("a_proposal",),
    ),
    TaskTemplate(
        "a_confirm",
        "allocation",
        "Allocations communicated to investors",
        "syndicate",
        True,
        1,
        ("a_approval",),
    ),
    # Booking
    TaskTemplate("k_isin", "booking", "ISIN and deal static data confirmed", "ops", True, 2),
    TaskTemplate(
        "k_book",
        "booking",
        "Trade booked and checked against the final terms",
        "ops",
        True,
        2,
        ("k_isin",),
    ),
    TaskTemplate(
        "k_settle",
        "booking",
        "Settlement instructions sent and closing arranged",
        "ops",
        True,
        4,
        ("k_book",),
    ),
    TaskTemplate("k_fees", "booking", "Fees and net proceeds confirmed", "ops", False, 4),
    TaskTemplate(
        "k_report", "booking", "Post-deal report prepared for DCM and the issuer", "dcm", False, 5
    ),
)


@dataclass(frozen=True)
class NewTask:
    id: str
    key: str
    stage_code: str
    title: str
    owner_role: str
    due: str  # ISO date
    blocking: bool
    status: str = "TODO"


def task_id(deal_id: str, key: str) -> str:
    return f"{deal_id}:{key}"


def instantiate_tasks(
    deal_id: str, launch_date: date, statuses: dict[str, str] | None = None
) -> tuple[list[NewTask], list[tuple[str, str]]]:
    """Create the task list for one deal. Returns (tasks, dependency pairs).

    A dependency pair is (task_id, depends_on_task_id).
    """
    statuses = statuses or {}
    tasks = [
        NewTask(
            id=task_id(deal_id, t.key),
            key=t.key,
            stage_code=t.stage_code,
            title=t.title,
            owner_role=t.owner_role,
            due=(launch_date + timedelta(days=t.offset_days)).isoformat(),
            blocking=t.blocking,
            status=statuses.get(t.key, "TODO"),
        )
        for t in TASK_TEMPLATES
    ]
    deps = [
        (task_id(deal_id, t.key), task_id(deal_id, dep))
        for t in TASK_TEMPLATES
        for dep in t.depends_on
    ]
    return tasks, deps


def initial_statuses(current_stage_code: str, done_in_current_stage: int = 0) -> dict[str, str]:
    """Statuses for a deal that is already part-way through the process (used by the seed).

    Everything in earlier stages is DONE. In the current stage the first N tasks (in template
    order, which always lists a task after the tasks it depends on) are DONE. The rest is TODO.
    """
    current = STAGE_BY_CODE[current_stage_code].position
    statuses: dict[str, str] = {}
    remaining = done_in_current_stage
    for template in TASK_TEMPLATES:
        position = STAGE_BY_CODE[template.stage_code].position
        if position < current:
            statuses[template.key] = "DONE"
        elif position == current and remaining > 0:
            statuses[template.key] = "DONE"
            remaining -= 1
    return statuses


def add_years(start: date, years: int) -> date:
    """Same day and month `years` later (29 February becomes 28 February)."""
    try:
        return start.replace(year=start.year + years)
    except ValueError:
        return start.replace(year=start.year + years, day=28)
