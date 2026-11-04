from fastapi import APIRouter

from app.api.v1 import chat, navigation, places, speech, traffic

api_router = APIRouter()
api_router.include_router(places.router)
api_router.include_router(navigation.router)
api_router.include_router(chat.router)
api_router.include_router(speech.router)
api_router.include_router(traffic.router)


@api_router.get("/ping")
def ping():
    return {"ok": True}
