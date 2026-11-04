"""Spatial Incident Filtering and Ahead-of-User Verification.
Filters incidents to those strictly within 60m of the traversed road geometry
and ahead of the vehicle along the route.
Enforces 2-minute rate-limiting on incident audio announcements.
"""

from app.schemas.nav_state import Announcement
from app.services.navigation.announcer import format_spoken_dist, round_spoken_distance
from app.services.routing.deviation import project
from app.services.traffic.provider import TrafficIncident, TrafficSnapshot


def get_route_bbox(geometry: list[list[float]], buffer_deg: float = 0.005) -> tuple[float, float, float, float]:
    """Returns (min_lat, min_lon, max_lat, max_lon) with a geographic buffer (~500m)."""
    min_lat = min(p[0] for p in geometry) - buffer_deg
    max_lat = max(p[0] for p in geometry) + buffer_deg
    min_lon = min(p[1] for p in geometry) - buffer_deg
    max_lon = max(p[1] for p in geometry) + buffer_deg
    return min_lat, min_lon, max_lat, max_lon


def filter_incidents_on_route(
    incidents: list[TrafficIncident],
    geometry: list[list[float]],
    user_along_m: float,
    max_dist_from_route_m: float = 60.0,
) -> list[TrafficIncident]:
    """Keeps only incidents within 60m of the route and strictly ahead of the user."""
    filtered: list[TrafficIncident] = []

    for inc in incidents:
        dist_from_route, along_route = project(geometry, inc.lat, inc.lon)
        if dist_from_route <= max_dist_from_route_m and along_route > user_along_m:
            ahead_m = along_route - user_along_m
            filtered.append(
                TrafficIncident(
                    id=inc.id,
                    category=inc.category,
                    description=inc.description,
                    lat=inc.lat,
                    lon=inc.lon,
                    delay_s=inc.delay_s,
                    length_m=inc.length_m,
                    distance_along_route_m=along_route,
                    distance_to_user_m=ahead_m,
                )
            )

    # Sort closest ahead first
    filtered.sort(key=lambda x: x.distance_to_user_m)
    return filtered


def check_incident_announcement(
    snapshot: TrafficSnapshot,
    user_along_m: float,
    geometry: list[list[float]],
    now: float,
    lang: str = "en",
    min_gap_s: float = 120.0,  # Max 1 incident announcement per 2 minutes
    trigger_dist_m: float = 1500.0,  # Announce when ~1.5 km ahead
) -> Announcement | None:
    """Checks if an upcoming on-route incident should be announced aloud."""
    if not snapshot.incidents:
        return None

    # Enforce 2-minute gap between incident announcements
    if now - snapshot.last_incident_announced_at < min_gap_s:
        return None

    relevant = filter_incidents_on_route(snapshot.incidents, geometry, user_along_m)
    if not relevant:
        return None

    candidate = relevant[0]
    # Check if within announcement trigger window (~1.5 km ahead and not right on top of user)
    if candidate.distance_to_user_m > trigger_dist_m or candidate.distance_to_user_m < 50.0:
        return None

    if candidate.id in snapshot.announced_incident_ids:
        return None

    val, unit = round_spoken_distance(candidate.distance_to_user_m)
    dist_str = format_spoken_dist(val, unit, lang)

    # Provider category word used directly
    category = candidate.category

    if lang == "kn":
        text = f"ಟ್ರಾಫಿಕ್ ಎಚ್ಚರಿಕೆ: {dist_str} ಮುಂದೆ {category} ಇದೆ."
    elif lang == "hinglish":
        text = f"Traffic alert: {dist_str} aage {category} hai."
    else:
        text = f"Traffic alert: {category} {dist_str} ahead."

    # Mark announced
    snapshot.announced_incident_ids.add(candidate.id)
    snapshot.last_incident_announced_at = now

    return Announcement(
        text=text,
        stage="near",
        priority="high",
        language=lang,
    )

