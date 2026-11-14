"""Term sheet endpoints. Any role may use the lab; every call is audited."""

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile

from app.core.errors import BadRequestError
from app.core.security import CurrentUser, get_current_user
from app.deps import get_termsheet_service
from app.termsheets.models import ExtractionOut, SampleOut, ValidationReport
from app.termsheets.parser import MAX_BYTES
from app.termsheets.service import TermSheetService

router = APIRouter(tags=["documents"], dependencies=[Depends(get_current_user)])

Service = Annotated[TermSheetService, Depends(get_termsheet_service)]
User = Annotated[CurrentUser, Depends(get_current_user)]


@router.post("/documents/extract", response_model=ExtractionOut, status_code=201)
async def extract_term_sheet(
    service: Service,
    user: User,
    file: Annotated[UploadFile | None, File()] = None,
    text: Annotated[str | None, Form()] = None,
    deal_id: Annotated[str | None, Form()] = None,
) -> ExtractionOut:
    """Upload a .txt, .md or .pdf term sheet, or paste its text, and get a typed record back."""
    content: bytes | None = None
    if file is not None:
        content = await file.read(MAX_BYTES + 1)  # one byte more than allowed, to detect oversize
        if not content:
            raise BadRequestError("The uploaded file is empty.")
    return await service.extract(
        filename=file.filename if file else None,
        content=content,
        text=text,
        deal_id=deal_id or None,
        user=user,
    )


@router.post("/documents/{doc_id}/validate", response_model=ValidationReport)
async def validate_term_sheet(
    doc_id: str, service: Service, user: User, deal_id: str | None = None
) -> ValidationReport:
    """Run the validation rules and, when a deal is known, the field-by-field booking diff."""
    return await service.validate(doc_id, deal_id, user)


@router.get("/deals/{deal_id}/termsheet-sample", response_model=SampleOut)
async def term_sheet_sample(deal_id: str, service: Service, variant: str = "good") -> SampleOut:
    """A synthetic term sheet built from the deal's booking: 'good' matches, 'bad' has errors."""
    return await service.make_sample(deal_id, variant)
