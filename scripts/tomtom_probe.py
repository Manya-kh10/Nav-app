"""TomTom Routing & Traffic API probe for Bangalore corridors.
Reads TOMTOM_API_KEY from .env and queries 2 Bangalore routes + traffic incidents.
"""
import json
import sys
import time
from pathlib import Path

import httpx

if sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent

# 2 Distinct Bangalore corridors:
# 1. Congested: Central Silk Board -> Marathahalli (Outer Ring Road)
# 2. Quiet: Malleshwaram 18th Cross -> Sankey Tank / Sadashivanagar
CORRIDORS = [
    {
        "name": "Congested Corridor (Silk Board -> Marathahalli)",
        "start": (12.9172, 77.6227),
        "end": (12.9569, 77.7011),
    },
    {
        "name": "Quiet Corridor (Malleshwaram -> Sankey Tank)",
        "start": (12.9998, 77.5700),
        "end": (13.0075, 77.5735),
    },
]


def load_env() -> dict[str, str]:
    env = {}
    p = ROOT / ".env"
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def map_tomtom_to_step(item: dict, prev_offset: float = 0.0) -> dict:
    """Demonstrate mapping a TomTom guidance instruction into our Step model."""
    tt_maneuver = item.get("maneuver", "STRAIGHT")
    mod = None
    man = "turn"

    if tt_maneuver in ("DEPART", "LOCATION_DEPARTURE"):
        man = "depart"
    elif tt_maneuver in ("ARRIVE", "LOCATION_ARRIVAL"):
        man = "arrive"
    elif "LEFT" in tt_maneuver:
        man = "turn"
        mod = "slight left" if "BEAR" in tt_maneuver or "KEEP" in tt_maneuver else "left"
        if "SHARP" in tt_maneuver:
            mod = "sharp left"
    elif "RIGHT" in tt_maneuver:
        man = "turn"
        mod = "slight right" if "BEAR" in tt_maneuver or "KEEP" in tt_maneuver else "right"
        if "SHARP" in tt_maneuver:
            mod = "sharp right"
    elif "ROUNDABOUT" in tt_maneuver:
        man = "roundabout"
        mod = "left" if "LEFT" in tt_maneuver else "right"
    elif "UTURN" in tt_maneuver:
        man = "turn"
        mod = "uturn"
    else:
        man = "continue"
        mod = "straight"

    offset = float(item.get("routeOffsetInMeters", 0))
    dist = max(0.0, offset - prev_offset)

    street_list = item.get("street", [])
    road = street_list[0] if street_list else ""

    pt = item.get("point", {})
    return {
        "maneuver": man,
        "modifier": mod,
        "road": road,
        "distance_m": round(dist, 1),
        "lat": pt.get("latitude", 0.0),
        "lon": pt.get("longitude", 0.0),
        "raw_message": item.get("message", ""),
    }


def main():
    env = load_env()
    key = env.get("TOMTOM_API_KEY", "")

    print("=" * 75)
    print(" TOMTOM ROUTING & TRAFFIC SPIKE (BANGALORE CORRIDORS)")
    print("=" * 75)

    if not key or "paste_your_key" in key:
        print("[ERROR] TOMTOM_API_KEY is not set in ROOT/.env")
        print("Please add your key to .env:")
        print("TOMTOM_API_KEY=your_tomtom_api_key_here")
        return

    client = httpx.Client(timeout=15.0)

    for c in CORRIDORS:
        name = c["name"]
        start_lat, start_lon = c["start"]
        end_lat, end_lon = c["end"]
        loc_str = f"{start_lat},{start_lon}:{end_lat},{end_lon}"

        url = f"https://api.tomtom.com/routing/1/calculateRoute/{loc_str}/json"
        params = {
            "key": key,
            "traffic": "true",
            "computeTravelTimeFor": "all",
            "instructionsType": "text",
            "travelMode": "car",
            "routeType": "fastest",
        }

        print(f"\n--- Corridor: {name} ---")
        t0 = time.perf_counter()
        r = client.get(url, params=params)
        dt = (time.perf_counter() - t0) * 1000

        if r.status_code != 200:
            print(f"[HTTP {r.status_code}] Failed: {r.text[:300]}")
            continue

        data = r.json()
        routes = data.get("routes", [])
        if not routes:
            print("No routes returned.")
            continue

        route = routes[0]
        summary = route.get("summary", {})
        guidance = route.get("guidance", {})
        instructions = guidance.get("instructions", [])

        length_m = summary.get("lengthInMeters", 0)
        travel_time_s = summary.get("travelTimeInSeconds", 0)
        no_traffic_s = summary.get("noTrafficTravelTimeInSeconds", 0)
        traffic_delay_s = summary.get("trafficDelayInSeconds", 0)

        print(f"Response Time:            {dt:.1f} ms")
        print(f"Length:                   {length_m / 1000:.2f} km")
        print(f"travelTimeInSeconds:      {travel_time_s}s ({travel_time_s / 60:.1f} min)")
        print(f"noTrafficTravelTimeInSec: {no_traffic_s}s ({no_traffic_s / 60:.1f} min)")
        print(f"trafficDelayInSeconds:    {traffic_delay_s}s ({traffic_delay_s / 60:.1f} min)")
        print(f"Guidance Instructions:    {len(instructions)} steps")

        # Demonstrate mapping of first 3 guidance steps to our Step schema
        print("Sample Mapped Steps (TomTom -> Our Step Model):")
        prev_off = 0.0
        for i, raw_step in enumerate(instructions[:3]):
            mapped = map_tomtom_to_step(raw_step, prev_off)
            prev_off = float(raw_step.get("routeOffsetInMeters", 0))
            print(f"  Step {i}: man={mapped['maneuver']}, mod={mapped['modifier']}, "
                  f"road='{mapped['road']}', dist={mapped['distance_m']}m -> \"{mapped['raw_message']}\"")

    # Probe Traffic Incidents non-tile API
    print("\n--- Traffic Incidents Probe (Outer Ring Road Bounding Box) ---")
    inc_url = "https://api.tomtom.com/traffic/services/5/incidentDetails"
    inc_params = {
        "key": key,
        "bbox": "77.60,12.90,77.72,12.98",
        "fields": "{incidents{type,geometry{type,coordinates},properties{iconCategory,magnitudeOfDelay,events{description}}}}",
        "language": "en-GB",
        "timeValidityFilter": "present",
    }
    t0 = time.perf_counter()
    inc_res = client.get(inc_url, params=inc_params)
    dt_inc = (time.perf_counter() - t0) * 1000
    if inc_res.status_code == 200:
        inc_data = inc_res.json()
        incidents = inc_data.get("incidents", [])
        print(f"Incidents Query Time:     {dt_inc:.1f} ms")
        print(f"Incidents in ORR BBox:    {len(incidents)}")
        for idx, inc in enumerate(incidents[:3]):
            props = inc.get("properties", {})
            events = props.get("events", [{}])
            desc = events[0].get("description", "Incident") if events else "Incident"
            print(f"  Incident {idx+1}: Category={props.get('iconCategory')}, DelayMag={props.get('magnitudeOfDelay')}, Desc=\"{desc}\"")
    else:
        print(f"[HTTP {inc_res.status_code}] Incidents query failed: {inc_res.text[:300]}")

    print("\n" + "=" * 75)
    print(" SPIKE COMPLETE (Total API calls: 3/6 maximum)")
    print("=" * 75)


if __name__ == "__main__":
    main()

