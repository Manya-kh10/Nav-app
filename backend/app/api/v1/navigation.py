import time

from fastapi import APIRouter, HTTPException

from app.schemas.nav_state import Guidance, NavStatus, PositionUpdate
from app.schemas.route import (
    Guide,
    GuideRequest,
    LatLon,
    RerouteResult,
    Route,
    RouteRequest,
    Step,
    TrafficInfo,
)
from app.services.landmarks.finder import find_landmarks
from app.services.navigation.announcer import AnnouncerConfig, build_reroute_announcement, check_announcement, render_guidance
from app.services.navigation.answers import fmt_dist_hi, fmt_dist_kn
from app.services.navigation.sessions import create_session, get_session
from app.services.navigation.steps import simplify_steps
from app.services.navigation.templates import build_instructions, fmt_dist, live_instruction
from app.services.routing.client import RoutingError, get_route
from app.services.routing.deviation import distance_m, next_maneuver, project
from app.services.traffic.adapter import build_traffic_spoken_summary
from app.services.traffic.budget import can_call
from app.services.traffic.incidents import check_incident_announcement, get_route_bbox
from app.services.traffic.provider import TrafficSnapshot
from app.services.traffic.tomtom import TomTomTrafficProvider

router = APIRouter(prefix="/navigation", tags=["navigation"])
MAX_CLOCK_SKEW_S = 300
ARRIVED_M = 25
MIN_REROUTE_GAP_S = 2.0

traffic_provider = TomTomTrafficProvider()


def _http_error(e: RoutingError) -> HTTPException:
    status = 404 if e.code == "no_route" else 502
    return HTTPException(status_code=status, detail={"code": e.code, "message": e.detail})


@router.post("/route", response_model=Route)
async def route(req: RouteRequest):
    if req.mode == "drive":
        tomtom_res = await traffic_provider.get_route_with_traffic(req.start, req.end)
        if tomtom_res:
            r, summary = tomtom_res
            spoken = build_traffic_spoken_summary(summary, lang=req.lang or "en")
            t_info = TrafficInfo(
                travel_time_s=summary.travel_time_s,
                no_traffic_travel_time_s=summary.no_traffic_travel_time_s,
                delay_s=summary.delay_s,
                level=summary.level.value,
                delay_minutes=summary.delay_minutes,
                travel_minutes=summary.travel_minutes,
                spoken_summary=spoken,
                attribution="Traffic data © TomTom",
            )
            return r.model_copy(update={"traffic": t_info})

    try:
        return await get_route(req.start, req.end, req.mode)
    except RoutingError as e:
        raise _http_error(e)


@router.post("/guide", response_model=Guide)
async def guide(req: GuideRequest):
    r = None
    traffic_snapshot = None
    traffic_status = "not_applicable"

    if req.mode == "drive":
        traffic_status = "unavailable"
        if not can_call():
            traffic_status = "budget_exceeded"

        tomtom_res = await traffic_provider.get_route_with_traffic(req.start, req.end)
        if tomtom_res:
            r, traffic_summary = tomtom_res
            traffic_status = "available"

            spoken = build_traffic_spoken_summary(traffic_summary, lang=req.lang or "en")
            t_info = TrafficInfo(
                travel_time_s=traffic_summary.travel_time_s,
                no_traffic_travel_time_s=traffic_summary.no_traffic_travel_time_s,
                delay_s=traffic_summary.delay_s,
                level=traffic_summary.level.value,
                delay_minutes=traffic_summary.delay_minutes,
                travel_minutes=traffic_summary.travel_minutes,
                spoken_summary=spoken,
                attribution="Traffic data © TomTom",
            )
            r = r.model_copy(update={"traffic": t_info})

            # Fetch initial incidents for route bounding box
            min_lat, min_lon, max_lat, max_lon = get_route_bbox(r.geometry)
            incidents = await traffic_provider.get_incidents_in_bbox(min_lat, min_lon, max_lat, max_lon)
            now = time.time()
            traffic_snapshot = TrafficSnapshot(
                summary=traffic_summary,
                incidents=incidents,
                last_traffic_fetch=now,
                last_incidents_fetch=now,
            )

    if r is None:
        try:
            r = await get_route(req.start, req.end, req.mode)
            if req.mode == "drive":
                r = r.model_copy(update={"eta_note": "Traffic information is not available; estimate does not include traffic."})
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
    sid = create_session(r, instructions, found or {}, req.end, req.mode, traffic_snapshot=traffic_snapshot, lang=req.lang or "en")
    return Guide(
        route=r,
        instructions=instructions,
        landmarks_status=status,
        session_id=sid,
        traffic_status=traffic_status,
    )


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

    if u.lang:
        s.driver_lang = u.lang

    # Compute or extract speed (m/s)
    if u.speed_mps is not None and u.speed_mps >= 0:
        speed = u.speed_mps
    elif s.last_fix is not None:
        last_lat, last_lon, last_ts = s.last_fix
        dt = u.timestamp - last_ts
        if dt > 0:
            d = distance_m(last_lat, last_lon, u.lat, u.lon)
            computed = d / dt
            # Treat unknown as moving only once displacement shows > 8 km/h (~2.22 m/s)
            if computed >= (8.0 / 3.6):
                speed = computed
            else:
                speed = 0.0
        else:
            speed = s.speed_mps
    else:
        speed = 0.0

    s.speed_mps = speed
    s.last_fix = (u.lat, u.lon, u.timestamp)

    dist, along = project(s.route.geometry, u.lat, u.lon)
    poor = u.accuracy_m is not None and u.accuracy_m > s.tracker.max_accuracy_m
    needs_reroute = s.tracker.update(dist, u.accuracy_m, u.timestamp)

    total = s.route.distance_m
    remaining = max(0.0, total - along)
    remaining_s = s.route.duration_s * (remaining / total) if total else 0.0

    nxt = next_maneuver(s.route.steps, along)
    idx = dist_next = text = None
    on_route = dist <= s.tracker.threshold_m
    arrived = remaining < ARRIVED_M

    if nxt and on_route:
        idx, dist_next = nxt
        lm = s.landmarks.get(idx)
        text = live_instruction(s.route.steps[idx], dist_next, lm["name"] if lm else None, lang=s.driver_lang)

    next_step = s.route.steps[idx] if idx is not None and idx < len(s.route.steps) else None
    lm_data = s.landmarks.get(idx) if idx is not None else None
    lm_name = lm_data["name"] if lm_data else None

    # Step announcement
    announcement = check_announcement(
        distance_to_next_m=dist_next,
        speed_mps=speed,
        step_index=idx,
        step=next_step,
        on_route=on_route,
        arrived=arrived,
        state=s.announcer_state,
        landmark_name=lm_name,
        lang=s.driver_lang,
        mode=s.mode,
    )

    # Periodic incident & traffic refresh while driving
    if s.mode == "drive" and s.traffic_snapshot.summary:
        now = u.timestamp
        # Incidents every 3 minutes (180s)
        if now - s.traffic_snapshot.last_incidents_fetch >= 180.0:
            s.traffic_snapshot.last_incidents_fetch = now
            min_lat, min_lon, max_lat, max_lon = get_route_bbox(s.route.geometry)
            new_incs = await traffic_provider.get_incidents_in_bbox(min_lat, min_lon, max_lat, max_lon)
            if new_incs:
                s.traffic_snapshot.incidents = new_incs

        # Incidents alert check (if no higher priority step announcement)
        if announcement is None and on_route:
            inc_ann = check_incident_announcement(
                s.traffic_snapshot, along, s.route.geometry, now, lang=s.driver_lang
            )
            if inc_ann:
                announcement = inc_ann

    # Guidance computation
    guidance = None
    stage_for_guidance = s.announcer_state.last_announced_stage
    guidance_text = None

    if arrived:
        guidance_text = render_guidance(
            next_step or Step(maneuver="arrive", modifier=None, road="", distance_m=0, duration_s=0, lat=u.lat, lon=u.lon),
            0.0,
            "arrival",
            s.driver_lang,
        )
    elif next_step is not None and dist_next is not None and on_route:
        lm_for_guidance = lm_name if stage_for_guidance == "ahead" else None
        guidance_text = render_guidance(
            next_step,
            dist_next,
            stage_for_guidance,
            s.driver_lang,
            lm_for_guidance,
        )
    elif not on_route:
        guidance_text = build_reroute_announcement(s.driver_lang).text

    if guidance_text:
        guidance = Guidance(
            step_index=idx,
            stage=stage_for_guidance,
            text=guidance_text,
            lang=s.driver_lang,
        )

    result = NavStatus(
        on_route=on_route,
        needs_reroute=needs_reroute,
        gps_quality="poor" if poor else "ok",
        distance_from_route_m=round(dist, 1),
        remaining_m=round(remaining, 1),
        remaining_s=round(remaining_s, 1),
        arrived=arrived,
        next_index=idx,
        next_text=guidance_text or text,
        distance_to_next_m=round(dist_next, 1) if dist_next is not None else None,
        speed_mps=round(speed, 2),
        announcement=announcement,
        guidance=guidance,
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

    r = None
    if s.mode == "drive":
        tomtom_res = await traffic_provider.get_route_with_traffic(LatLon(lat=u.lat, lon=u.lon), s.destination)
        if tomtom_res:
            r, summary = tomtom_res
            s.traffic_snapshot.summary = summary
            s.traffic_snapshot.last_traffic_fetch = now

    if r is None:
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
    s.announcer_state.reset()
    s.last_status = None   # old step indexes no longer match the new route
    s.last_ts = max(s.last_ts, u.timestamp)
    s.last_fix = (u.lat, u.lon, u.timestamp)

    minutes = max(1, round(r.duration_s / 60))
    if s.driver_lang == "kn":
        message = f"ನೀವು ದಾರಿಯಿಂದ ಹೊರಬಂದಿದ್ದೀರಿ, ಹೊಸ ದಾರಿ ಹುಡುಕಲಾಗಿದೆ: {fmt_dist_kn(r.distance_m)}, ಸುಮಾರು {minutes} ನಿಮಿಷ."
    elif s.driver_lang in ("hinglish", "hi"):
        message = f"Route se hat gaye the, naya rasta dhoondha hai: {fmt_dist_hi(r.distance_m)}, lagbhag {minutes} minute."
    else:
        message = f"You moved away from the route, so I found a new one: {fmt_dist(r.distance_m)}, about {minutes} minutes."
    return RerouteResult(
        route=r, instructions=instructions,
        landmarks_status="ok" if found is not None else "unavailable",
        session_id=u.session_id, message=message,
        traffic_status="available" if s.traffic_snapshot.summary else "unavailable",
    )
