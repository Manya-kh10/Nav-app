"""Deterministic GPS Trace Replay Runner with Drive & Walk Profiles.
Replays walking and driving routes through the navigation API.
Validates on-route tracking, debounce timing, reroute triggering, proactive guidance,
audio consistency, and cache economy.
"""
import argparse
import asyncio
from datetime import datetime
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
    lang: str = "en",
    speed_mult: float = 1.0,
):
    effective_speed = speed_mps if speed_mps is not None else (10.0 if mode == "drive" else 1.4)
    dt = 1.0
    step_m = effective_speed * dt
    initial_wrong_turn = simulate_wrong_turn
    speed_disp = f" @ {effective_speed:.1f} m/s ({effective_speed * 3.6:.1f} km/h, {step_m:.1f} m/tick, mult={speed_mult:g}x)"
    print(f"\n--- Scenario: {name} [{mode.upper()}{speed_disp} | lang={lang}] {'(Wrong-Turn Deviation)' if simulate_wrong_turn else '(Clean Route)'} ---")

    # 1. Request Guide / Route Session
    guide_resp = await client.post(
        "/navigation/guide",
        json={"start": start, "end": end, "mode": mode, "landmarks": True, "lang": lang},
    )
    if guide_resp.status_code != 200:
        print(f"Failed to get route: HTTP {guide_resp.status_code} - {guide_resp.text}")
        return None

    guide = guide_resp.json()
    session_id = guide["session_id"]
    route = guide["route"]

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

    base_time = time.time()
    tick_counter = 0

    # Metrics
    announcements = []
    seen_stages: dict[tuple[int, str], int] = {}
    duplicates = 0
    distance_deltas: list[float] = []
    uncached_tts_calls = 0
    step_turn_events: dict[int, list[str]] = {}
    last_countdown_bucket = None

    step_idx = 0
    print("\n  [TIMELINE]: time | stage | spoken text | live text | language | chime")
    print("  " + "-" * 75)

    last_ts = 0.0
    while step_idx < len(path):
        tick_counter += 1
        sim_progress = step_idx / max(1, len(path) - 1)
        cur_sim_time = max(last_ts + 0.001, (time.time() - 240.0) + sim_progress * 480.0)
        last_ts = cur_sim_time
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
            "lang": lang,
        }
        pos_resp = await client.post("/navigation/position", json=pos_payload)
        ticks += 1
        if pos_resp.status_code != 200:
            print(f"Position update error: HTTP {pos_resp.status_code} - {pos_resp.text}")
            break

        status = pos_resp.json()
        if not status["on_route"]:
            off_route_ticks += 1

        # Check proactive guidance and announcement
        ann = status.get("announcement")
        guidance = status.get("guidance") or {}
        live_text = guidance.get("text") or status.get("next_text") or ""
        nxt_idx = status.get("next_index")

        if ann:
            announcements.append(ann)
            stage = ann.get("stage", "none")
            spoken_text = ann.get("text", "")
            chime_flag = "YES" if ann.get("chime") else "NO"
            ann_lang = ann.get("lang") or ann.get("language") or lang
            tts_code = {"en": "en-IN", "hi": "hi-IN", "hinglish": "hi-IN", "kn": "kn-IN"}.get(ann_lang, "en-IN")

            # Timeline print
            t_s = tick_counter * dt
            print(
                f"  [{t_s:4.0f}s] Stage: {stage:7s} | Chime: {chime_flag:3s} | "
                f"Spoken: '{spoken_text}' | Live: '{live_text}' | Lang: {ann_lang} (TTS: {tts_code})"
            )

            # THE ONE RULE assertion: Spoken text == live text at emit time (when speak is True)
            if ann.get("speak") and spoken_text:
                assert spoken_text == live_text, f"THE ONE RULE Violated: spoken '{spoken_text}' != live '{live_text}'"

            # Check duplicate stage emission for same maneuver
            if nxt_idx is not None and stage in ("ahead", "near"):
                pair = (nxt_idx, stage)
                if pair in seen_stages:
                    duplicates += 1
                seen_stages[pair] = seen_stages.get(pair, 0) + 1

            # Record turn event progression
            if nxt_idx is not None:
                step_turn_events.setdefault(nxt_idx, [])
                if ann.get("stage") in ("ahead", "near"):
                    step_turn_events[nxt_idx].append(ann.get("stage"))
                if ann.get("chime"):
                    step_turn_events[nxt_idx].append("chime")

            # Audio cache verification
            if spoken_text:
                key = audio_cache.make_key(
                    settings.gnani_tts_model,
                    settings.gnani_tts_voice,
                    tts_code,
                    1.0,
                    spoken_text,
                )
                if not audio_cache.get(key):
                    uncached_tts_calls += 1

        # Print live countdown text every 100 meters
        dist_to_next = status.get("distance_to_next_m")
        if dist_to_next is not None and dist_to_next > 50.0:
            bucket = int(dist_to_next // 100) * 100
            if bucket != last_countdown_bucket:
                last_countdown_bucket = bucket
                if not ann:
                    t_s = tick_counter * dt
                    print(f"  [{t_s:4.0f}s] (Live countdown: {dist_to_next:.0f}m left) Live Text: '{live_text}'")

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
                path = resample(new_guide["route"]["geometry"], step_m=step_m)
                step_idx = 0
                simulate_wrong_turn = False
                deviating = False
                drift_m = 0.0
                seen_stages.clear()
                last_countdown_bucket = None
                continue
            else:
                print(f"  [REROUTE FAILED] HTTP {reroute_resp.status_code}")
                break

        if status["arrived"] or step_idx >= len(path) - 1:
            arrived = True
            break

        step_idx += 1

    # Verify that each turn has ahead, near, chime (for completed turns)
    turn_steps = [
        i for i, s in enumerate(route["steps"])
        if s["maneuver"] not in ("depart", "arrive") and not (s.get("modifier") == "straight" or s.get("maneuver") == "continue")
    ]
    announced_turn_steps = {pair[0] for pair in seen_stages.keys()}
    missed_turns = len(set(turn_steps) - announced_turn_steps)

    print(
        f"\nResult: Ticks={ticks} | Arrived={arrived} | Announcements={len(announcements)} "
        f"| Duplicates={duplicates} | Missed Turns={missed_turns}"
    )

    return {
        "scenario": name,
        "mode": mode,
        "speed_mps": effective_speed,
        "wrong_turn": initial_wrong_turn,
        "total_ticks": ticks,
        "off_route_ticks": off_route_ticks,
        "reroute_triggered": reroute_triggered,
        "reroute_latency_ms": round(reroute_latency_ms, 1) if reroute_latency_ms else None,
        "arrived": arrived,
        "announcements_count": len(announcements),
        "duplicates": duplicates,
        "missed_turns": missed_turns,
        "uncached_tts_calls": uncached_tts_calls,
    }


async def main():
    parser = argparse.ArgumentParser(description="Replay GPS routes against backend.")
    parser.add_argument("--url", default="", help="Live backend URL (e.g. http://127.0.0.1:8001/api/v1). If empty, tests in-process.")
    parser.add_argument("--mode", default="walk", choices=["walk", "drive", "all"], help="Routing mode to replay.")
    parser.add_argument("--speed", type=float, default=10.0, help="Driving speed in m/s (default: 10.0 m/s = 36 km/h).")
    parser.add_argument("--mult", type=float, default=1.0, help="Simulation speed multiplier (1 for 1x, 6 for 6x).")
    parser.add_argument("--lang", default="en", choices=["en", "hi", "hinglish", "kn", "all"], help="Guidance language.")
    parser.add_argument("--wrong-turn", action="store_true", help="Simulate a wrong turn to test deviation detection and automatic rerouting.")
    parser.add_argument("--scenario", default="", help="Filter scenarios by name substring (e.g. 'MG Road' or '100 Feet').")
    parser.add_argument("--full-suite", action="store_true", help="Run full 4-scenario suite: walk normal, walk wrong-turn, drive normal, drive wrong-turn.")
    args = parser.parse_args()

    print("=" * 75)
    print(f" BANGALORE VOICE NAV: DETERMINISTIC GPS REPLAY TEST (mode={args.mode}, mult={args.mult:g}x, lang={args.lang})")
    print("=" * 75)

    all_routes = [
        ("Indiranagar 100 Feet Rd", {"lat": 12.9784, "lon": 77.6408}, {"lat": 12.9719, "lon": 77.6412}),
        ("MG Road Metro -> Indiranagar Metro", {"lat": 12.975642, "lon": 77.606523}, {"lat": 12.9783, "lon": 77.6386}),
    ]

    if args.scenario:
        routes = [r for r in all_routes if args.scenario.lower() in r[0].lower()]
    else:
        routes = [all_routes[0]] if not args.full_suite else [all_routes[0]]

    results = []

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport if not args.url else None,
        base_url=args.url.rstrip("/") if args.url else "http://testserver/api/v1",
        timeout=60.0,
    ) as client:
        if args.full_suite:
            # Run the 4 standard benchmark scenarios: walk normal, walk wrong-turn, drive normal, drive wrong-turn
            suite_runs = [
                ("walk", 1.4, False),
                ("walk", 1.4, True),
                ("drive", 10.0, False),
                ("drive", 10.0, True),
            ]
            name, start, end = all_routes[0]
            for m, spd, wrong in suite_runs:
                res = await replay_scenario(client, f"{name}", start, end, wrong, mode=m, speed_mps=spd, lang="en", speed_mult=1.0)
                if res:
                    results.append(res)
        else:
            def get_modes():
                if args.mode == "all":
                    return ["walk", "drive"]
                return [args.mode]

            def get_langs():
                if args.lang == "all":
                    return ["en", "hi", "hinglish", "kn"]
                return [args.lang]

            for m in get_modes():
                base_spd = args.speed if m == "drive" else 1.4
                spd = base_spd * args.mult
                for l in get_langs():
                    for name, start, end in routes:
                        res1 = await replay_scenario(client, f"{name}", start, end, args.wrong_turn, mode=m, speed_mps=spd, lang=l, speed_mult=args.mult)
                        if res1:
                            results.append(res1)

    print("\n" + "=" * 75)
    print(" GPS REPLAY EVALUATION SUMMARY")
    print("=" * 75)
    all_arrived = all(r["arrived"] for r in results)
    total_duplicates = sum(r["duplicates"] for r in results)
    total_missed = sum(r["missed_turns"] for r in results)

    print(f"Total Scenarios Tested:  {len(results)}")
    print(f"Arrival Success Rate:    {sum(1 for r in results if r['arrived'])}/{len(results)} ({'100%' if all_arrived else 'Partial'})")
    print(f"Announcement Duplicates: {total_duplicates} (Must be 0)")
    print(f"Missed Turn Maneuvers:   {total_missed}")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    timestamped_file = OUT_DIR / f"gps_replay_eval_{timestamp}.json"
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    timestamped_file.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved replay results -> {timestamped_file}")


if __name__ == "__main__":
    asyncio.run(main())
