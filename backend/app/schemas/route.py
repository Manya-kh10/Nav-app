from typing import Literal

from pydantic import BaseModel


class LatLon(BaseModel):
    lat: float
    lon: float


class RouteRequest(BaseModel):
    start: LatLon
    end: LatLon
    mode: Literal["walk", "drive"] = "walk"


class GuideRequest(RouteRequest):
    landmarks: bool = True


class Step(BaseModel):
    maneuver: str            # turn, depart, arrive, fork, roundabout...
    modifier: str | None     # left, right, slight left...
    road: str
    distance_m: float
    duration_s: float
    lat: float
    lon: float


class Route(BaseModel):
    mode: str
    distance_m: float
    duration_s: float
    geometry: list[list[float]]   # [[lat, lon], ...]
    steps: list[Step]
    eta_note: str = "Estimate from the routing engine; does not include traffic."


class Instruction(BaseModel):
    text: str
    maneuver: str
    modifier: str | None = None
    distance_to_m: float          # distance from the previous point to this maneuver
    lat: float
    lon: float
    landmark: str | None = None
    landmark_kind: str | None = None


class Guide(BaseModel):
    route: Route
    instructions: list[Instruction]
    landmarks_status: Literal["ok", "unavailable", "skipped"]
    session_id: str

class RerouteResult(Guide):
    message: str