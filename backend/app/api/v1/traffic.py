"""Traffic API Endpoints.
Provides usage and budget transparency for traffic provider requests.
"""

from fastapi import APIRouter
from app.services.traffic import budget

router = APIRouter(prefix="/traffic", tags=["traffic"])


@router.get("/usage")
def traffic_usage():
    """Returns the daily traffic budget consumption against the hard daily cap."""
    return budget.get_usage()

