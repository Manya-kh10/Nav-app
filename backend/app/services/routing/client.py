import httpx

from app.schemas.route import LatLon, Route, Step

# dev-only public servers; self-host for the demo
URLS = {
    "walk": "https://routing.openstreetmap.de/routed-foot/route/v1/driving/{c}",
    "drive": "https://router.project-osrm.org/route/v1/driving/{c}",
}
HEADERS = {"User-Agent": "bangalore-voice-nav-hackathon/0.1 (student project)"}


class RoutingError(Exception):
    def __init__(self, code: str, detail: str = ""):
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


async def get_route(start: LatLon, end: LatLon, mode: str = "walk") -> Route:
    coords = f"{start.lon},{start.lat};{end.lon},{end.lat}"
    url = URLS[mode].format(c=coords)
    params = {"overview": "full", "geometries": "geojson", "steps": "true"}
    last = ""
    for _ in range(2):
        try:
            async with httpx.AsyncClient(headers=HEADERS, timeout=20) as client:
                r = await client.get(url, params=params)
            data = r.json()
            if r.status_code == 200 and data.get("code") == "Ok":
                return _parse(data["routes"][0], mode)
            if data.get("code") == "NoRoute":
                raise RoutingError("no_route", "No route between these points")
            last = f"HTTP {r.status_code} {data.get('code', '')}"
        except RoutingError:
            raise
        except (httpx.HTTPError, ValueError) as e:
            last = str(e) or type(e).__name__
    raise RoutingError("routing_unavailable", last)


def _parse(route: dict, mode: str) -> Route:
    steps = []
    for leg in route["legs"]:
        for s in leg["steps"]:
            m = s["maneuver"]
            steps.append(Step(
                maneuver=m["type"], modifier=m.get("modifier"), road=s.get("name", ""),
                distance_m=s["distance"], duration_s=s["duration"],
                lat=m["location"][1], lon=m["location"][0],
            ))
    geometry = [[lat, lon] for lon, lat in route["geometry"]["coordinates"]]
    return Route(mode=mode, distance_m=route["distance"], duration_s=route["duration"],
                 geometry=geometry, steps=steps)