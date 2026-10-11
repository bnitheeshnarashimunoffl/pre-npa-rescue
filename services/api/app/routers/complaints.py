from fastapi import APIRouter, status

from app.fixtures import load_fixture
from app.routers._common import PROTECTED, roles
from npa_contracts.api import ComplaintCreateRequest, ComplaintUpdateRequest
from npa_contracts.models import Complaint

router = APIRouter(prefix="/complaints", tags=["complaints"], **PROTECTED)


def _fixture() -> Complaint:
    return Complaint.model_validate(load_fixture("complaint.json"))


@router.post(
    "",
    response_model=Complaint,
    status_code=status.HTTP_201_CREATED,
    openapi_extra=roles("customer", "hardship_officer", "admin"),
)
def open_complaint(body: ComplaintCreateRequest) -> Complaint:
    """Open a complaint with docket number and 30-day SLA (IS/ISO 10002:2018)."""
    return _fixture()


@router.get(
    "/{docket_no}",
    response_model=Complaint,
    openapi_extra=roles("customer", "hardship_officer", "admin", "auditor"),
)
def get_complaint(docket_no: str) -> Complaint:
    return _fixture().model_copy(update={"docket_no": docket_no})


@router.patch(
    "/{docket_no}", response_model=Complaint, openapi_extra=roles("hardship_officer", "admin")
)
def update_complaint(docket_no: str, body: ComplaintUpdateRequest) -> Complaint:
    return _fixture().model_copy(update={"docket_no": docket_no})
