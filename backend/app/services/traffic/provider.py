"""Traffic Provider Interface and Data Models.
Defines data structures for traffic delay, flow levels, and incidents,
with strictly factual provider-derived data.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Literal

from app.schemas.route import LatLon, Route, Step


class TrafficLevel(str, Enum):
    NONE = "none"
    LIGHT = "light"
    HEAVY = "heavy"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class TrafficSummary:
    travel_time_s: int
    no_traffic_travel_time_s: int
    delay_s: int
    level: TrafficLevel
    fetched_at: float  # unix epoch timestamp
    provider: str = "tomtom"

    @property
    def delay_minutes(self) -> int:
        return max(0, round(self.delay_s / 60))

    @property
    def travel_minutes(self) -> int:
        return max(1, round(self.travel_time_s / 60))

    def age_minutes(self, now: float | None = None) -> int:
        cur = now if now is not None else datetime.now(timezone.utc).timestamp()
        return max(0, int((cur - self.fetched_at) / 60))


@dataclass(frozen=True)
class TrafficIncident:
    id: str
    category: str  # Provider category word (e.g. "Jam", "Accident", "Road Works")
    description: str
    lat: float
    lon: float
    delay_s: int
    length_m: float
    distance_along_route_m: float = 0.0  # Computed distance from route start
    distance_to_user_m: float = 0.0       # Computed distance ahead of user


@dataclass
class TrafficSnapshot:
    summary: TrafficSummary | None = None
    incidents: list[TrafficIncident] = field(default_factory=list)
    last_traffic_fetch: float = 0.0
    last_incidents_fetch: float = 0.0
    last_incident_announced_at: float = 0.0
    announced_incident_ids: set[str] = field(default_factory=set)

    def is_stale(self, max_age_s: float = 600.0, now: float | None = None) -> bool:
        """Data older than 10 minutes (600s) is considered outdated."""
        if not self.summary:
            return True
        cur = now if now is not None else datetime.now(timezone.utc).timestamp()
        return (cur - self.summary.fetched_at) > max_age_s


class TrafficProvider(ABC):
    @abstractmethod
    async def get_route_with_traffic(
        self, start: LatLon, end: LatLon
    ) -> tuple[Route, TrafficSummary] | None:
        """Calculates driving route with live traffic and guidance steps."""
        pass

    @abstractmethod
    async def get_incidents_in_bbox(
        self, min_lat: float, min_lon: float, max_lat: float, max_lon: float
    ) -> list[TrafficIncident]:
        """Fetches traffic incidents in the given bounding box."""
        pass

