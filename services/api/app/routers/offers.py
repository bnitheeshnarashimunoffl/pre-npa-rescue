from typing import Any

from fastapi import APIRouter, status

from app.fixtures import load_fixture
from app.routers._common import PROTECTED, access
from npa_contracts.api import OfferCreateRequest, OfferDecisionRequest
from npa_contracts.enums import OfferStatus
from npa_contracts.models import Offer

router = APIRouter(prefix="/offers", tags=["offers"], **PROTECTED)


def _fixture_offer(offer_id: str | None = None, **update: Any) -> Offer:
    offer = Offer.model_validate(load_fixture("offer.json"))
    if offer_id is not None:
        update["offer_id"] = offer_id
    return offer.model_copy(update=update)


@router.post(
    "",
    response_model=Offer,
    status_code=status.HTTP_201_CREATED,
    **access("hardship_officer", "admin", "system"),
)
def create_offer(body: OfferCreateRequest) -> Offer:
    """Propose an offer from a policy-permitted relief option."""
    return _fixture_offer(status=OfferStatus.PROPOSED, approved_by=None)


@router.post("/{offer_id}/approve", response_model=Offer, **access("hardship_officer", "admin"))
def approve_offer(offer_id: str, body: OfferDecisionRequest | None = None) -> Offer:
    """Human approval (IS/ISO/IEC 38507:2022); records ``approved_by``."""
    return _fixture_offer(offer_id, status=OfferStatus.APPROVED)


@router.post("/{offer_id}/accept", response_model=Offer, **access("customer"))
def accept_offer(offer_id: str, body: OfferDecisionRequest | None = None) -> Offer:
    return _fixture_offer(offer_id, status=OfferStatus.ACCEPTED)


@router.post(
    "/{offer_id}/reject",
    response_model=Offer,
    **access("customer", "hardship_officer", "admin"),
)
def reject_offer(offer_id: str, body: OfferDecisionRequest | None = None) -> Offer:
    return _fixture_offer(offer_id, status=OfferStatus.REJECTED)
