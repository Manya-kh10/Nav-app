"""TomTom Traffic and Routing Provider.
Fetches real-time traffic-aware routes and incident details with retry logic,
strict rate-limit compliance, and daily budget enforcement.
Attribution requirement: "Traffic data © TomTom"
"""

import asyncio
import time
from datetime import datetime, timezone
import httpx

from app.core.config import settings
from app.schemas.route import LatLon, Route
from app.services.traffic import budget
from app.services.traffic.adapter import adapt_tomtom_route
from app.services.traffic.provider import TrafficIncident, TrafficProvider, TrafficSummary

TOMTOM_BASE_URL = "https://api.tomtom.com"
RETRY_STATUSES = {429, 500, 502, 503, 504}

TOMTOM_INCIDENT_CATEGORIES = {
    0: "Obstruction",
    1: "Accident",
    2: "Fog",
    3: "Hazard",
    4: "Rain",
    5: "Ice",
    6: "Traffic Jam",
    7: "Lane Closed",
    8: "Road Closed",
    9: "Road Works",
    10: "Wind",
    11: "Flooding",
    14: "Broken Down Vehicle",
}


class TomTomTrafficProvider(TrafficProvider):
    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or settings.tomtom_api_key

    async def get_route_with_traffic(
        self, start: LatLon, end: LatLon
    ) -> tuple[Route, TrafficSummary] | None:
        """Calculates driving route with traffic via TomTom Routing API v1.
        Returns None if key missing, budget cap reached, or provider fails.
        """
        if not self.api_key or not budget.can_call():
            return None

        url = f"{TOMTOM_BASE_URL}/routing/1/calculateRoute/{start.lat},{start.lon}:{end.lat},{end.lon}/json"
        params = {
            "key": self.api_key,
            "traffic": "true",
            "computeTravelTimeFor": "all",
            "instructionsType": "text",
            "travelMode": "car",
        }

        for attempt in range(2):
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.get(url, params=params)

                budget.record_call("calculateRoute", resp.status_code)

                if resp.status_code == 200:
                    data = resp.json()
                    now = datetime.now(timezone.utc).timestamp()
                    return adapt_tomtom_route(data, fetched_at=now)

                if resp.status_code not in RETRY_STATUSES:
                    break

            except (httpx.TimeoutException, httpx.NetworkError):
                if attempt == 0:
                    await asyncio.sleep(1.0)
                    continue

        return None

    async def get_incidents_in_bbox(
        self, min_lat: float, min_lon: float, max_lat: float, max_lon: float
    ) -> list[TrafficIncident]:
        """Fetches traffic incidents in the given bounding box via TomTom Incidents API v5."""
        if not self.api_key or not budget.can_call():
            return []

        # TomTom expects bbox formatted as: minLon,minLat,maxLon,maxLat
        bbox_str = f"{min_lon:.5f},{min_lat:.5f},{max_lon:.5f},{max_lat:.5f}"
        url = f"{TOMTOM_BASE_URL}/traffic/services/5/incidentDetails"
        params = {
            "key": self.api_key,
            "bbox": bbox_str,
            "fields": "{incidents{id,geometry{type,coordinates},properties{iconCategory,magnitudeOfDelay,events{description,code},length,delay}}}",
        }

        for attempt in range(2):
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.get(url, params=params)

                budget.record_call("incidentDetails", resp.status_code)

                if resp.status_code == 200:
                    data = resp.json()
                    raw_incidents = data.get("incidents", [])
                    out: list[TrafficIncident] = []

                    for inc in raw_incidents:
                        props = inc.get("properties", {})
                        geom = inc.get("geometry", {})
                        coords = geom.get("coordinates", [])

                        # Extract representative point [lon, lat]
                        if geom.get("type") == "Point" and len(coords) >= 2:
                            pt_lon, pt_lat = coords[0], coords[1]
                        elif geom.get("type") == "LineString" and coords and len(coords[0]) >= 2:
                            pt_lon, pt_lat = coords[0][0], coords[0][1]
                        else:
                            continue

                        cat_code = props.get("iconCategory", 0)
                        category = TOMTOM_INCIDENT_CATEGORIES.get(cat_code, "Traffic Obstruction")
                        events = props.get("events", [])
                        desc = events[0].get("description", category) if events else category

                        out.append(
                            TrafficIncident(
                                id=str(inc.get("id", "")),
                                category=category,
                                description=desc,
                                lat=pt_lat,
                                lon=pt_lon,
                                delay_s=int(props.get("delay", 0)),
                                length_m=float(props.get("length", 0.0)),
                            )
                        )
                    return out

                if resp.status_code not in RETRY_STATUSES:
                    break

            except (httpx.TimeoutException, httpx.NetworkError):
                if attempt == 0:
                    await asyncio.sleep(1.0)
                    continue

        return []

