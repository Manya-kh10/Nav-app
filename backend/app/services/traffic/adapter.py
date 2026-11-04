"""TomTom Route Guidance to Standard Step Adapter.
Maps TomTom calculateRoute response to the standard Bangalore Voice Nav Route and Step schemas.
Ensures landmark matching, announcer stages, and deviation logic work identically with TomTom.
"""

from app.schemas.route import Route, Step
from app.services.traffic.provider import TrafficLevel, TrafficSummary

TOMTOM_MANEUVER_MAP = {
    "DEPART": ("depart", None),
    "ARRIVE": ("arrive", None),
    "STRAIGHT": ("continue", "straight"),
    "FOLLOW": ("continue", "straight"),
    "KEEP_LEFT": ("fork", "left"),
    "KEEP_RIGHT": ("fork", "right"),
    "BEAR_LEFT": ("turn", "slight left"),
    "BEAR_RIGHT": ("turn", "slight right"),
    "TURN_LEFT": ("turn", "left"),
    "TURN_RIGHT": ("turn", "right"),
    "SHARP_LEFT": ("turn", "sharp left"),
    "SHARP_RIGHT": ("turn", "sharp right"),
    "MAKE_UTURN": ("turn", "uturn"),
    "ROUNDABOUT_ENTER": ("roundabout", None),
    "ROUNDABOUT_EXIT": ("roundabout", None),
    "MOTORWAY_EXIT_LEFT": ("fork", "left"),
    "MOTORWAY_EXIT_RIGHT": ("fork", "right"),
}


def compute_traffic_level(delay_s: int, free_flow_s: int) -> TrafficLevel:
    """Computes traffic level based on absolute delay and relative delay percentage.
    - none: delay < 2 min (120s) or delay < 10% of free flow
    - light: delay 2-7 min or delay 10-35% of free flow
    - heavy: delay >= 7 min or delay >= 35% of free flow
    """
    if delay_s <= 0:
        return TrafficLevel.NONE
    if delay_s < 120 or (free_flow_s > 0 and (delay_s / free_flow_s) < 0.10):
        return TrafficLevel.NONE
    if delay_s < 420 and (free_flow_s > 0 and (delay_s / free_flow_s) < 0.35):
        return TrafficLevel.LIGHT
    return TrafficLevel.HEAVY


def adapt_tomtom_route(data: dict, fetched_at: float) -> tuple[Route, TrafficSummary]:
    """Adapts a TomTom calculateRoute JSON response into our Route model and TrafficSummary."""
    routes = data.get("routes", [])
    if not routes:
        raise ValueError("No routes found in TomTom response")

    r0 = routes[0]
    summary = r0["summary"]
    leg = r0["legs"][0]
    points = leg.get("points", [])
    geometry = [[p["latitude"], p["longitude"]] for p in points]

    travel_time_s = summary["travelTimeInSeconds"]
    no_traffic_s = summary.get("noTrafficTravelTimeInSeconds", travel_time_s)
    delay_s = summary.get("trafficDelayInSeconds", 0)
    level = compute_traffic_level(delay_s, no_traffic_s)

    traffic_summary = TrafficSummary(
        travel_time_s=travel_time_s,
        no_traffic_travel_time_s=no_traffic_s,
        delay_s=delay_s,
        level=level,
        fetched_at=fetched_at,
        provider="tomtom",
    )

    instructions = r0.get("guidance", {}).get("instructions", [])
    steps: list[Step] = []

    for i, inst in enumerate(instructions):
        maneuver_code = inst.get("maneuver", "STRAIGHT")
        mapped_maneuver, mapped_modifier = TOMTOM_MANEUVER_MAP.get(
            maneuver_code, ("continue", "straight")
        )

        road = inst.get("street", "").strip()
        lat = inst["point"]["latitude"]
        lon = inst["point"]["longitude"]

        # Calculate distance and duration to next maneuver
        if i + 1 < len(instructions):
            next_inst = instructions[i + 1]
            dist_m = max(0.0, float(next_inst.get("routeOffsetInMeters", 0) - inst.get("routeOffsetInMeters", 0)))
            dur_s = max(0.0, float(next_inst.get("travelTimeInSeconds", 0) - inst.get("travelTimeInSeconds", 0)))
        else:
            dist_m = 0.0
            dur_s = 0.0

        steps.append(
            Step(
                maneuver=mapped_maneuver,
                modifier=mapped_modifier,
                road=road,
                distance_m=dist_m,
                duration_s=dur_s,
                lat=lat,
                lon=lon,
            )
        )

    # If TomTom guidance was empty or lacked depart/arrive
    if not steps:
        steps = [
            Step(maneuver="depart", modifier=None, road="", distance_m=summary["lengthInMeters"], duration_s=travel_time_s, lat=geometry[0][0], lon=geometry[0][1]),
            Step(maneuver="arrive", modifier=None, road="", distance_m=0.0, duration_s=0.0, lat=geometry[-1][0], lon=geometry[-1][1]),
        ]

    route = Route(
        mode="drive",
        geometry=geometry,
        distance_m=float(summary["lengthInMeters"]),
        duration_s=float(travel_time_s),
        steps=steps,
    )

    return route, traffic_summary


def build_traffic_spoken_summary(summary: TrafficSummary, lang: str = "en") -> str:
    """Generates a strictly factual spoken traffic overview."""
    mins = summary.travel_minutes
    delay = summary.delay_minutes
    lvl = summary.level

    if lang == "kn":
        if lvl == TrafficLevel.NONE or delay == 0:
            return f"ಸುಮಾರು {mins} ನಿಮಿಷ. ಟ್ರಾಫಿಕ್ ಸುಗಮವಾಗಿದೆ."
        if lvl == TrafficLevel.LIGHT:
            return f"ಸುಮಾರು {mins} ನಿಮಿಷ. ಲಘು ಟ್ರಾಫಿಕ್, ಸಾಮಾನ್ಯಕ್ಕಿಂತ {delay} ನಿಮಿಷ ಹೆಚ್ಚು."
        return f"ಸುಮಾರು {mins} ನಿಮಿಷ. ಟ್ರಾಫಿಕ್ ದಟ್ಟವಾಗಿದೆ, ಸಾಮಾನ್ಯಕ್ಕಿಂತ {delay} ನಿಮಿಷ ಹೆಚ್ಚು."

    if lang == "hinglish":
        if lvl == TrafficLevel.NONE or delay == 0:
            return f"Lagbhag {mins} minute. Traffic bilkul smooth hai."
        if lvl == TrafficLevel.LIGHT:
            return f"Lagbhag {mins} minute. Halka traffic hai, aam taur se {delay} minute zyada."
        return f"Lagbhag {mins} minute. Traffic heavy hai, lagbhag {delay} minute zyada lagenge."

    # English default
    if lvl == TrafficLevel.NONE or delay == 0:
        return f"About {mins} minutes. Traffic is flowing smoothly."
    if lvl == TrafficLevel.LIGHT:
        return f"About {mins} minutes. Traffic is light, about {delay} minutes more than usual."
    return f"About {mins} minutes. Traffic is heavy, about {delay} minutes more than usual."

