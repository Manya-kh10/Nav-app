from fastapi import APIRouter, HTTPException

from app.schemas.chat import ChatRequest, ChatResponse
from app.services.navigation.answers import answer
from app.services.navigation.sessions import get_session

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
async def chat(req: ChatRequest):
    s = get_session(req.session_id)
    if s is None:
        raise HTTPException(404, detail={"code": "session_not_found",
                                         "message": "Route expired. Please request a new route."})
    return answer(s, req.message, driver_mode=req.driver_mode)
