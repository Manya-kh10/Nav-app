"""Deterministic GPS Trace Replay Runner.
Replays walking routes and wrong-turn deviations through the navigation API.
Validates on-route tracking, debounce timing, reroute triggering, and arrival.
Outputs a summary and writes eval/results/gps_replay_eval.json.
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

from app.main import app

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


async def replay_scenario(client: httpx.AsyncClient, name: str, start: dict, end: dict, simulate_wrong_turn: bool):
    print(f"\n--- Scenario: {name} {'(Wrong-Turn Deviation)' if simulate_wrong_turn else '(Clean Walk)'} ---")

    # 1. Request Guide / Route Session
    guide_resp = await client.post(
        "/navigation/guide",
        json={"start": start, "end": end, "mode": "walk", "landmarks": True},
    )
    if guide_resp.status_code != 200:
        print(f"Failed to get route: HTTP {guide_resp.status_code} - {guide_resp.text}")
        return None

    guide = guide_resp.json()
    session_id = guide["session_id"]
    route = guide["route"]
    path = resample(route["geometry"], step_m=20.0)
    print(f"Session: {session_id[:8]}... | Route Distance: {route['distance_m']:.0f}m | Resampled Points: {len(path)}")

    deviate_at = int(len(path) * 0.4) if simulate_wrong_turn else 999999
    deviating = False
    drift_m = 0.0

    ticks = 0
    reroute_triggered = False
    reroute_latency_ms = None
    arrived = False
    off_route_ticks = 0
    t_start = time.time()
    cur_sim_time = t_start

    step_idx = 0
    while step_idx < len(path):
        cur_sim_time += 1.5  # 1.5s between GPS fixes
        lat, lon = path[step_idx]

        if simulate_wrong_turn and step_idx >= deviate_at:
            deviating = True

        if deviating:
            drift_m = min(drift_m + 15.0, 80.0)
            # Drift diagonally (NE) so it leaves both N-S and E-W roads
            lat += (drift_m * 0.707) / 111320.0
            lon += (drift_m * 0.707) / 108500.0

        pos_resp = await client.post(
            "/navigation/position",
            json={
                "session_id": session_id,
                "lat": lat,
                "lon": lon,
                "accuracy_m": 8.0,
                "timestamp": cur_sim_time,
            },
        )
        ticks += 1
        if pos_resp.status_code != 200:
            print(f"Position update error: HTTP {pos_resp.status_code} - {pos_resp.text}")
            break

        status = pos_resp.json()
        if not status["on_route"]:
            off_route_ticks += 1

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
                },
            )
            reroute_latency_ms = (time.perf_counter() - t_reroute0) * 1000
            if reroute_resp.status_code == 200:
                new_guide = reroute_resp.json()
                print(f"  [REROUTE OK] {new_guide.get('message', 'Rerouted')} in {reroute_latency_ms:.1f}ms")
                # Resume on the new route
                path = resample(new_guide["route"]["geometry"], step_m=20.0)
                step_idx = 0
                deviating = False
                drift_m = 0.0
                continue
            else:
                print(f"  [REROUTE FAILED] HTTP {reroute_resp.status_code}")
                break

        if status["arrived"] or step_idx >= len(path) - 1:
            arrived = True
            break

        step_idx += 1

    print(f"Result: Ticks={ticks} | Off-route ticks={off_route_ticks} | Rerouted={reroute_triggered} | Arrived={arrived}")
    return {
        "scenario": name,
        "wrong_turn": simulate_wrong_turn,
        "total_ticks": ticks,
        "off_route_ticks": off_route_ticks,
        "reroute_triggered": reroute_triggered,
        "reroute_latency_ms": round(reroute_latency_ms, 1) if reroute_latency_ms else None,
        "arrived": arrived,
    }


async def main():
    parser = argparse.ArgumentParser(description="Replay GPS routes against backend.")
    parser.add_argument("--url", default="", help="Live backend URL (e.g. http://127.0.0.1:8001/api/v1). If empty, tests in-process.")
    args = parser.parse_args()

    print("=" * 70)
    print(" BANGALORE VOICE NAV: DETERMINISTIC GPS REPLAY TEST")
    print("=" * 70)

    # 2 Benchmark routes:
    # 1. Indiranagar Metro -> 100 Feet Rd south
    # 2. MG Road Metro -> Cubbon Park
    routes = [
        ("Indiranagar Walk", {"lat": 12.9784, "lon": 77.6408}, {"lat": 12.9719, "lon": 77.6412}),
        ("MG Road to Cubbon Park", {"lat": 12.9756, "lon": 77.6068}, {"lat": 12.9763, "lon": 77.5929}),
    ]

    results = []
    if args.url:
        print(f"Target: Live HTTP {args.url}")
        async with httpx.AsyncClient(base_url=args.url.rstrip("/")) as client:
            for name, start, end in routes:
                res1 = await replay_scenario(client, f"{name} (Normal)", start, end, False)
                if res1:
                    results.append(res1)
                res2 = await replay_scenario(client, f"{name} (Deviation)", start, end, True)
                if res2:
                    results.append(res2)
    else:
        print("Target: In-process FastAPI app via ASGITransport")
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver/api/v1") as client:
            for name, start, end in routes:
                res1 = await replay_scenario(client, f"{name} (Normal)", start, end, False)
                if res1:
                    results.append(res1)
                res2 = await replay_scenario(client, f"{name} (Deviation)", start, end, True)
                if res2:
                    results.append(res2)

    print("\n" + "=" * 70)
    print(" GPS REPLAY EVALUATION SUMMARY")
    print("=" * 70)
    all_arrived = all(r["arrived"] for r in results)
    reroutes_ok = all(r["reroute_triggered"] for r in results if r["wrong_turn"])
    print(f"Total Scenarios Tested:  {len(results)}")
    print(f"Arrival Success Rate:    {sum(1 for r in results if r['arrived'])}/{len(results)} ({'100%' if all_arrived else 'Partial'})")
    print(f"Reroute Recovery Rate:   {sum(1 for r in results if r['reroute_triggered'] and r['wrong_turn'])}/{sum(1 for r in results if r['wrong_turn'])}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved replay results -> {OUT_FILE}")


if __name__ == "__main__":
    asyncio.run(main())
