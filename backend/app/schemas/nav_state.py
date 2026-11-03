from typing import Literal

from pydantic import BaseModel, Field


class PositionUpdate(BaseModel):
    session_id: str
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    accuracy_m: float | None = Field(default=None, ge=0)
    timestamp: float  # unix seconds


class NavStatus(BaseModel):
    on_route: bool
    needs_reroute: bool
    gps_quality: Literal["ok", "poor"]
    distance_from_route_m: float
    remaining_m: float
    remaining_s: float
    arrived: bool
    next_index: int | None
    next_text: str | None
    distance_to_next_m: float | None