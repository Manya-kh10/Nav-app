import time

from fastapi import APIRouter, HTTPException

from app.schemas.nav_state import NavStatus, PositionUpdate
from app.schemas.route import Guide, GuideRequest, LatLon, RerouteResult, Route, RouteRequest
from app.services.landmarks.finder import find_landmarks
from app.services.navigation.sessions import create_session, get_session
from app.services.navigation.steps import simplify_steps
from app.services.navigation.templates import build_instructions, fmt_dist, live_instruction
from app.services.routing.client import RoutingError, get_route
from app.services.routing.deviation import distance_m, next_maneuver, project

router = APIRouter(prefix="/navigation", tags=["navigation"])
MAX_CLOCK_SKEW_S = 300
ARRIVED_M = 25
MIN_REROUTE_GAP_S = 10


def _http_error(e: RoutingError) -> HTTPException:
    status = 404 if e.code == "no_route" else 502
    return HTTPException(status_code=status, detail={"code": e.code, "message": e.detail})


@router.post("/route", response_model=Route)
async def route(req: RouteRequest):
    try:
        return await get_route(req.start, req.end, req.mode)
    except RoutingError as e:
        raise _http_error(e)


@router.post("/guide", response_model=Guide)
async def guide(req: GuideRequest):
    try:
        r = await get_route(req.start, req.end, req.mode)
    except RoutingError as e:
        raise _http_error(e)
    steps = simplify_steps(r.steps)
    found = None
    status = "skipped"
    if req.landmarks:
        found = await find_landmarks(steps)
        status = "ok" if found is not None else "unavailable"
    instructions = build_instructions(steps, found or {}, req.mode)
    r = r.model_copy(update={"steps": steps})
    sid = create_session(r, instructions, found or {}, req.end, req.mode)
    return Guide(route=r, instructions=instructions, landmarks_status=status, session_id=sid)


@router.post("/position", response_model=NavStatus)
async def position(u: PositionUpdate):
    s = get_session(u.session_id)
    if s is None:
        raise HTTPException(404, detail={"code": "session_not_found",
                                         "message": "Route expired. Please request a new route."})
    if abs(time.time() - u.timestamp) > MAX_CLOCK_SKEW_S:
        raise HTTPException(422, detail={"code": "bad_timestamp",
                                         "message": "Timestamp is too far from server time."})
    if u.timestamp < s.last_ts:
        raise HTTPException(409, detail={"code": "stale_update", "message": "Older than the last update."})
    s.last_ts = u.timestamp

    dist, along = project(s.route.geometry, u.lat, u.lon)
    poor = u.accuracy_m is not None and u.accuracy_m > s.tracker.max_accuracy_m
    needs_reroute = s.tracker.update(dist, u.accuracy_m, u.timestamp)

    total = s.route.distance_m
    remaining = max(0.0, total - along)
    remaining_s = s.route.duration_s * (remaining / total) if total else 0.0

    nxt = next_maneuver(s.route.steps, along)
    idx = dist_next = text = None
    if nxt and dist <= s.tracker.threshold_m:
        idx, dist_next = nxt
        lm = s.landmarks.get(idx)
        text = live_instruction(s.route.steps[idx], dist_next, lm["name"] if lm else None)

    result = NavStatus(
        on_route=dist <= s.tracker.threshold_m,
        needs_reroute=needs_reroute,
        gps_quality="poor" if poor else "ok",
        distance_from_route_m=round(dist, 1),
        remaining_m=round(remaining, 1),
        remaining_s=round(remaining_s, 1),
        arrived=remaining < ARRIVED_M,
        next_index=idx,
        next_text=text,
        distance_to_next_m=round(dist_next, 1) if dist_next is not None else None,
    )
    s.last_status = result
    s.last_status_at = time.time()
    return result


@router.post("/reroute", response_model=RerouteResult)
async def reroute(u: PositionUpdate):
    s = get_session(u.session_id)
    if s is None:
        raise HTTPException(404, detail={"code": "session_not_found",
                                         "message": "Route expired. Please request a new route."})
    now = time.time()
    if abs(now - u.timestamp) > MAX_CLOCK_SKEW_S:
        raise HTTPException(422, detail={"code": "bad_timestamp",
                                         "message": "Timestamp is too far from server time."})
    if u.accuracy_m is not None and u.accuracy_m > s.tracker.max_accuracy_m:
        raise HTTPException(422, detail={"code": "poor_gps",
                                         "message": "GPS accuracy is too low to reroute."})
    if now - s.last_reroute < MIN_REROUTE_GAP_S:
        raise HTTPException(429, detail={"code": "reroute_too_soon",
                                         "message": "Rerouting too often; try again in a few seconds."})
    s.last_reroute = now
    s.reroute_seq += 1
    seq = s.reroute_seq

    try:
        r = await get_route(LatLon(lat=u.lat, lon=u.lon), s.destination, s.mode)
    except RoutingError as e:
        raise _http_error(e)
    if seq != s.reroute_seq:
        raise HTTPException(409, detail={"code": "superseded", "message": "A newer reroute is in progress."})

    steps = simplify_steps(r.steps)

    # connect the user's actual position to the start of the new route
    gap = distance_m(u.lat, u.lon, r.geometry[0][0], r.geometry[0][1])
    if gap > 5:
        sec_per_m = r.duration_s / r.distance_m if r.distance_m else 0.8
        r = r.model_copy(update={
            "geometry": [[u.lat, u.lon]] + r.geometry,
            "distance_m": r.distance_m + gap,
            "duration_s": r.duration_s + gap * sec_per_m,
        })
        steps[0] = steps[0].model_copy(update={
            "lat": u.lat, "lon": u.lon,
            "distance_m": steps[0].distance_m + gap,
            "duration_s": steps[0].duration_s + gap * sec_per_m,
        })

    found = await find_landmarks(steps)
    if seq != s.reroute_seq:
        raise HTTPException(409, detail={"code": "superseded", "message": "A newer reroute is in progress."})

    instructions = build_instructions(steps, found or {}, s.mode)
    r = r.model_copy(update={"steps": steps})
    s.route, s.instructions, s.landmarks = r, instructions, found or {}
    s.tracker.reset()
    s.last_status = None   # old step indexes no longer match the new route
    s.last_ts = max(s.last_ts, u.timestamp)

    minutes = max(1, round(r.duration_s / 60))
    message = (f"You moved away from the route, so I found a new one: "
               f"{fmt_dist(r.distance_m)}, about {minutes} minutes.")
    return RerouteResult(
        route=r, instructions=instructions,
        landmarks_status="ok" if found is not None else "unavailable",
        session_id=u.session_id, message=message,
    )