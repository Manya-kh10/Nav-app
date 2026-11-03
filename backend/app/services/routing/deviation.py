import math
from dataclasses import dataclass

R = 6371000.0


def _xy(lat: float, lon: float, lat0: float) -> tuple[float, float]:
    return math.radians(lon) * R * math.cos(math.radians(lat0)), math.radians(lat) * R


def project(geometry: list[list[float]], lat: float, lon: float) -> tuple[float, float]:
    """Return (distance_to_route_m, distance_along_route_m) for a point against [[lat, lon], ...]."""
    px, py = _xy(lat, lon, lat)
    best_d, best_along, cum = float("inf"), 0.0, 0.0
    for (alat, alon), (blat, blon) in zip(geometry, geometry[1:]):
        ax, ay = _xy(alat, alon, lat)
        bx, by = _xy(blat, blon, lat)
        dx, dy = bx - ax, by - ay
        seg = math.hypot(dx, dy)
        t = 0.0 if seg == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (seg * seg)))
        d = math.hypot(px - (ax + t * dx), py - (ay + t * dy))
        if d < best_d:
            best_d, best_along = d, cum + t * seg
        cum += seg
    return best_d, best_along

def distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    x1, y1 = _xy(lat1, lon1, lat1)
    x2, y2 = _xy(lat2, lon2, lat1)
    return math.hypot(x2 - x1, y2 - y1)

def next_maneuver(steps, along_m: float):
    """Return (step_index, distance_to_it_m) for the next real maneuver ahead, or None if past the end."""
    start = 0.0
    for i, st in enumerate(steps):
        if i > 0 and start > along_m:
            return i, start - along_m
        start += st.distance_m
    return None


@dataclass
class DeviationTracker:
    threshold_m: float = 40.0     # tunable
    min_seconds: float = 5.0      # must stay off-route this long before we reroute
    max_accuracy_m: float = 30.0  # ignore GPS fixes worse than this
    _since: float | None = None

    def update(self, dist_m: float, accuracy_m: float | None, ts: float) -> bool:
        """True when the user has been confidently off-route long enough to reroute."""
        if accuracy_m is not None and accuracy_m > self.max_accuracy_m:
            return False
        if dist_m <= self.threshold_m:
            self._since = None
            return False
        if self._since is None:
            self._since = ts
        return ts - self._since >= self.min_seconds

    def reset(self) -> None:
        self._since = None