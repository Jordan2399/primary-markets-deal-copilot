"""Report endpoints. Any signed-in user may read the roll-ups; investor-level detail stays on the
investor pages (viewers cannot open those)."""

from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import Response

from app.audit.models import build_event
from app.audit.service import AuditService
from app.core.security import CurrentUser, get_current_user
from app.deps import get_audit_service, get_report_service
from app.reports.models import ReportOverview
from app.reports.service import ReportService

router = APIRouter(prefix="/reports", tags=["reports"])

Service = Annotated[ReportService, Depends(get_report_service)]
User = Annotated[CurrentUser, Depends(get_current_user)]


@router.get("/overview", response_model=ReportOverview)
async def overview(service: Service, _user: User) -> ReportOverview:
    return await service.overview()


@router.get("/pipeline.csv")
async def pipeline_csv(
    service: Service, user: User, audit: Annotated[AuditService, Depends(get_audit_service)]
) -> Response:
    """Download the deal table. Exports are recorded in the audit trail."""
    body = await service.pipeline_csv()
    await audit.record(build_event(user, "report.export", "report", "pipeline"))
    return Response(
        content=body,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="deal-pipeline.csv"'},
    )
