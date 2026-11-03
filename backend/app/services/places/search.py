import asyncio
import time

import httpx

from app.schemas.places import Place
from app.services.places.matcher import get_index, make_key, score_text, tokens_of

NOMINATIM = "https://nominatim.openstreetmap.org/search"
HEADERS = {"User-Agent": "bangalore-voice-nav-hackathon/0.1 (student project)"}
VIEWBOX = "77.40,13.20,77.80,12.80"  # left,top,right,bottom around Bangalore
ONLINE_BELOW = 80.0  # only ask Nominatim when the best local match is weaker than this

_lock = asyncio.Lock()
_last_call = 0.0
_cache: dict[tuple[str, int], list[Place]] = {}


class PlaceSearchError(Exception):
    pass


async def _nominatim(q: str, limit: int) -> list[Place]:
    global _last_call
    key = (q.lower(), limit)
    if key in _cache:
        return _cache[key]
    params = {
        "q": q, "format": "jsonv2", "limit": limit, "countrycodes": "in",
        "viewbox": VIEWBOX, "bounded": 1, "accept-language": "en",
    }
    async with _lock:
        last_err = "unknown"
        for _ in range(2):
            wait = 1.1 - (time.monotonic() - _last_call)
            if wait > 0:
                await asyncio.sleep(wait)
            try:
                async with httpx.AsyncClient(headers=HEADERS, timeout=15) as client:
                    r = await client.get(NOMINATIM, params=params)
                _last_call = time.monotonic()
                if r.status_code == 200:
                    places = [_to_place(x) for x in r.json()]
                    _cache[key] = places
                    return places
                last_err = f"HTTP {r.status_code}"
            except httpx.HTTPError as e:
                _last_call = time.monotonic()
                last_err = str(e) or type(e).__name__
        raise PlaceSearchError(last_err)


def _to_place(x: dict) -> Place:
    display = x.get("display_name", "")
    return Place(
        name=x.get("name") or display.split(",")[0],
        display_name=display,
        lat=float(x["lat"]),
        lon=float(x["lon"]),
        category=x.get("category"),
        type=x.get("type"),
        importance=x.get("importance"),
    )


async def _online(q: str, limit: int) -> list[Place]:
    toks = tokens_of(q) or [q]
    variants = [" ".join(toks)]
    if len(toks) >= 2:  # "indira nagar metro" -> "indiranagar metro"
        joined = " ".join([toks[0] + toks[1]] + toks[2:])
        if joined not in variants:
            variants.append(joined)
    found: list[Place] = []
    err: PlaceSearchError | None = None
    for v in variants:
        try:
            found.extend(await _nominatim(v, limit))
        except PlaceSearchError as e:
            err = e
    if not found and err:
        raise err
    return found


def _merge(q: str, local: list[Place], online: list[Place], limit: int) -> list[Place]:
    for p in online:
        p.score = round(max(score_text(q, p.name), 50.0), 1)
        p.source = "online"
    pool = sorted(local + online, key=lambda p: -(p.score or 0.0))
    out: list[Place] = []
    seen: list[tuple[str, float, float]] = []
    for p in pool:
        k = make_key(tokens_of(p.name))
        if any(k == sk and abs(p.lat - la) < 0.0015 and abs(p.lon - lo) < 0.0015 for sk, la, lo in seen):
            continue
        seen.append((k, p.lat, p.lon))
        out.append(p)
        if len(out) >= limit:
            break
    return out


async def search_places(query: str, limit: int = 5) -> list[Place]:
    q = query.strip()
    if not q:
        return []
    local = get_index().search(q, limit)
    best = local[0].score if local else 0.0
    if best >= ONLINE_BELOW:
        return local
    try:
        online = await _online(q, limit)
    except PlaceSearchError:
        if local:
            return local   # weak local matches are still better than failing
        raise
    return _merge(q, local, online, limit)