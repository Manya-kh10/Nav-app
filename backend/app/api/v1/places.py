from fastapi import APIRouter, HTTPException, Query

from app.schemas.places import Place
from app.services.places.search import PlaceSearchError, search_places

router = APIRouter(prefix="/places", tags=["places"])


@router.get("/search", response_model=list[Place])
async def search(q: str = Query(min_length=2), limit: int = Query(5, ge=1, le=10)):
    try:
        return await search_places(q, limit)
    except PlaceSearchError as e:
        raise HTTPException(status_code=502, detail={"code": "place_search_unavailable", "message": str(e)}) 