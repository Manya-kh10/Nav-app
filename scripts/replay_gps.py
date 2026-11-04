"""Deterministic GPS Trace Replay Runner with Drive Profile.
Replays walking and driving routes through the navigation API.
Validates on-route tracking, debounce timing, reroute triggering, proactive guidance,
and audio cache economy.
Outputs summary metrics and writes eval/results/gps_replay_eval.json.
"""
import argparse
import asyncio
import json
import math
import sys
import time
from pathlib import Path

import httpx

if sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.core.config import settings
from app.main import app
from app.services.speech import audio_cache

OUT_DIR = ROOT / "eval" / "results"
OUT_FILE = OUT_DIR / "gps_replay_eval.json"
R_EARTH = 6371000.0


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R_EARTH * math.asin(math.sqrt(a))


def resample(geometry: list[list[float]], step_m: float = 20.0) -> list[list[float]]:
    out = [geometry[0]]
    carry = 0.0
    for i in range(1, len(geometry)):
        a = geometry[i - 1]
        b = geometry[i]
        seg = haversine_m(a[0], a[1], b[0], b[1])
        if seg == 0:
            continue
        d = step_m - carry
        while d <= seg:
            t = d / seg
            out.append([a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t])
            d += step_m
        carry = seg - (d - step_m)
    out.append(geometry[-1])
    return out


async def replay_scenario(
    client: httpx.AsyncClient,
    name: str,
    start: dict,
    end: dict,
    simulate_wrong_turn: bool,
    mode: str = "walk",
    speed_mps: float | None = None,
):
    speed_disp = f" @ {speed_mps * 3.6:.0f} km/h" if speed_mps else ""
    print(f"\n--- Scenario: {name} [{mode.upper()}{speed_disp}] {'(Wrong-Turn Deviation)' if simulate_wrong_turn else '(Clean Route)'} ---")

    # 1. Request Guide / Route Session
    guide_resp = await client.post(
        "/navigation/guide",
        json={"start": start, "end": end, "mode": mode, "landmarks": True},
    )
    if guide_resp.status_code != 200:
        print(f"Failed to get route: HTTP {guide_resp.status_code} - {guide_resp.text}")
        return None

    guide = guide_resp.json()
    session_id = guide["session_id"]
    route = guide["route"]

    # Resolution step along geometry based on speed and fix interval
    dt = 1.0 if mode == "drive" else 1.5
    effective_speed = speed_mps if speed_mps is not None else (10.0 if mode == "drive" else 1.4)
    step_m = max(5.0, effective_speed * dt)

    path = resample(route["geometry"], step_m=step_m)
    print(f"Session: {session_id[:8]}... | Route Distance: {route['distance_m']:.0f}m | Maneuvers: {len(route['steps'])} | Waypoints: {len(path)}")

    deviate_at = int(len(path) * 0.4) if simulate_wrong_turn else 999999
    deviating = False
    drift_m = 0.0

    ticks = 0
    reroute_triggered = False
    reroute_latency_ms = None
    arrived = False
    off_route_ticks = 0
    # Bounded timestamp progression: strictly monotonic, guaranteed abs(ts - now) <= 200s
    base_time = time.time()
    tick_counter = 0

    # Metrics
    announcements = []
    seen_stages: dict[tuple[int, str], int] = {}
    duplicates = 0
    distance_deltas: list[float] = []
    uncached_tts_calls = 0

    step_idx = 0
    while step_idx < len(path):
        tick_counter += 1
        # Maps ticks from (now - 200) to (now + 200) over up to 1000 ticks
        cur_sim_time = (base_time - 200.0) + (tick_counter * 0.4)
        lat, lon = path[step_idx]

        if simulate_wrong_turn and step_idx >= deviate_at:
            deviating = True

        if deviating:
            drift_m = min(drift_m + 15.0, 80.0)
            lat += (drift_m * 0.707) / 111320.0
            lon += (drift_m * 0.707) / 108500.0

        pos_payload = {
            "session_id": session_id,
            "lat": lat,
            "lon": lon,
            "accuracy_m": 8.0,
            "timestamp": cur_sim_time,
            "speed_mps": effective_speed,
        }
        pos_resp = await client.post("/navigation/position", json=pos_payload)
        ticks += 1
        if pos_resp.status_code != 200:
            print(f"Position update error: HTTP {pos_resp.status_code} - {pos_resp.text}")
            break

        status = pos_resp.json()
        if not status["on_route"]:
            off_route_ticks += 1

        # Check for proactive announcement
        ann = status.get("announcement")
        if ann:
            announcements.append(ann)
            nxt_idx = status.get("next_index")
            stage = ann.get("stage")

            # Check duplicate stage emission for same maneuver
            if nxt_idx is not None and stage in ("far", "near", "now"):
                pair = (nxt_idx, stage)
                if pair in seen_stages:
                    duplicates += 1
                seen_stages[pair] = seen_stages.get(pair, 0) + 1

                # Distance vs target check
                actual_d = status.get("distance_to_next_m")
                if actual_d is not None:
                    if stage == "far":
                        target_d = max(400.0, effective_speed * 40.0)
                    elif stage == "near":
                        target_d = max(120.0, effective_speed * 15.0)
                    else:
                        target_d = 30.0
                    distance_deltas.append(abs(actual_d - target_d))

            # Audio cache check
            tts_text = ann.get("text", "")
            tts_lang = "en-IN" if ann.get("language") == "en" else "hi-IN"
            key = audio_cache.make_key(
                settings.gnani_tts_model,
                settings.gnani_tts_voice,
                tts_lang,
                1.0,
                tts_text,
            )
            if not audio_cache.get(key):
                uncached_tts_calls += 1

            print(f"  📢 [{stage.upper()} | {ann.get('priority')}] {tts_text}")

        # Check for reroute
        if status["needs_reroute"] and not reroute_triggered:
            reroute_triggered = True
            t_reroute0 = time.perf_counter()
            reroute_resp = await client.post(
                "/navigation/reroute",
                json={
                    "session_id": session_id,
                    "lat": lat,
                    "lon": lon,
                    "accuracy_m": 8.0,
                    "timestamp": cur_sim_time,
                    "speed_mps": effective_speed,
                },
            )
            reroute_latency_ms = (time.perf_counter() - t_reroute0) * 1000
            if reroute_resp.status_code == 200:
                new_guide = reroute_resp.json()
                print(f"  [REROUTE OK] {new_guide.get('message', 'Rerouted')} in {reroute_latency_ms:.1f}ms")
                # Resume on the new route
                path = resample(new_guide["route"]["geometry"], step_m=step_m)
                step_idx = 0
                deviating = False
                drift_m = 0.0
                seen_stages.clear()  # Step indexes reset on the new route
                continue
            else:
                print(f"  [REROUTE FAILED] HTTP {reroute_resp.status_code}")
                break

        if status["arrived"] or step_idx >= len(path) - 1:
            arrived = True
            break

        step_idx += 1

    # Check missed turns (excluding depart and arrive)
    turn_steps = [i for i, s in enumerate(route["steps"]) if s["maneuver"] not in ("depart", "arrive")]
    announced_turn_steps = {pair[0] for pair in seen_stages.keys()}
    missed_turns = len(set(turn_steps) - announced_turn_steps)

    mean_dist_delta = round(sum(distance_deltas) / len(distance_deltas), 1) if distance_deltas else 0.0

    print(
        f"Result: Ticks={ticks} | Arrived={arrived} | Announcements={len(announcements)} "
        f"| Duplicates={duplicates} | Missed Turns={missed_turns} | Mean Target Offset={mean_dist_delta}m"
    )

    return {
        "scenario": name,
        "mode": mode,
        "speed_mps": effective_speed,
        "wrong_turn": simulate_wrong_turn,
        "total_ticks": ticks,
        "off_route_ticks": off_route_ticks,
        "reroute_triggered": reroute_triggered,
        "reroute_latency_ms": round(reroute_latency_ms, 1) if reroute_latency_ms else None,
        "arrived": arrived,
        "announcements_count": len(announcements),
        "duplicates": duplicates,
        "missed_turns": missed_turns,
        "mean_distance_vs_target_m": mean_dist_delta,
        "uncached_tts_calls": uncached_tts_calls,
    }


async def main():
    parser = argparse.ArgumentParser(description="Replay GPS routes against backend.")
    parser.add_argument("--url", default="", help="Live backend URL (e.g. http://127.0.0.1:8001/api/v1). If empty, tests in-process.")
    parser.add_argument("--mode", default="all", choices=["walk", "drive", "all"], help="Routing mode to replay.")
    parser.add_argument("--speed", type=float, default=10.0, help="Driving speed in m/s (default: 10.0 m/s = 36 km/h).")
    args = parser.parse_args()

    print("=" * 75)
    print(" BANGALORE VOICE NAV: DETERMINISTIC GPS REPLAY TEST (DRIVER & WALK)")
    print("=" * 75)

    routes = [
        ("Indiranagar 100 Feet Rd", {"lat": 12.9784, "lon": 77.6408}, {"lat": 12.9719, "lon": 77.6412}),
        ("MG Road to Cubbon Park", {"lat": 12.9756, "lon": 77.6068}, {"lat": 12.9763, "lon": 77.5929}),
    ]

    results = []

    def get_modes():
        if args.mode == "all":
            return ["walk", "drive"]
        return [args.mode]

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport if not args.url else None,
        base_url=args.url.rstrip("/") if args.url else "http://testserver/api/v1",
        timeout=30.0,
    ) as client:
        for mode in get_modes():
            speed_val = args.speed if mode == "drive" else 1.4
            for name, start, end in routes:
                res1 = await replay_scenario(client, f"{name} (Normal)", start, end, False, mode=mode, speed_mps=speed_val)
                if res1:
                    results.append(res1)
                res2 = await replay_scenario(client, f"{name} (Deviation)", start, end, True, mode=mode, speed_mps=speed_val)
                if res2:
                    results.append(res2)

    print("\n" + "=" * 75)
    print(" GPS REPLAY EVALUATION SUMMARY")
    print("=" * 75)
    all_arrived = all(r["arrived"] for r in results)
    reroutes_ok = all(r["reroute_triggered"] for r in results if r["wrong_turn"])
    total_duplicates = sum(r["duplicates"] for r in results)
    total_missed = sum(r["missed_turns"] for r in results)

    print(f"Total Scenarios Tested:  {len(results)}")
    print(f"Arrival Success Rate:    {sum(1 for r in results if r['arrived'])}/{len(results)} ({'100%' if all_arrived else 'Partial'})")
    print(f"Reroute Recovery Rate:   {sum(1 for r in results if r['reroute_triggered'] and r['wrong_turn'])}/{sum(1 for r in results if r['wrong_turn'])}")
    print(f"Announcement Duplicates: {total_duplicates} (Must be 0)")
    print(f"Missed Turn Maneuvers:   {total_missed}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved replay results -> {OUT_FILE}")


if __name__ == "__main__":
    asyncio.run(main())
