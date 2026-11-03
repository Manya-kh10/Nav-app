from fastapi import APIRouter, File, Form, HTTPException, Response, UploadFile
from pydantic import BaseModel, Field

from app.services.speech.prisma_stt import STTError, transcribe
from app.services.speech.timbre_tts import TTSError, synthesize
from app.services.usage import counter

router = APIRouter(prefix="/speech", tags=["speech"])

LANGS = {"en-IN", "hi-IN", "kn-IN"}
MAX_AUDIO_BYTES = 3 * 1024 * 1024


class TranscribeResponse(BaseModel):
    transcript: str
    language_code: str
    model: str | None = None


class SynthesizeRequest(BaseModel):
    text: str = Field(min_length=1, max_length=300)
    language_code: str = "en-IN"
    speed: float = Field(default=1.0, ge=0.5, le=2.0)


def _status(code: str) -> int:
    return 400 if code in ("stt_rejected", "tts_rejected") else 502


@router.post("/transcribe", response_model=TranscribeResponse)
async def transcribe_endpoint(audio_file: UploadFile = File(...), language_code: str = Form("en-IN")):
    if language_code not in LANGS:
        raise HTTPException(400, detail={"code": "bad_language", "message": f"Use one of {sorted(LANGS)}"})
    data = await audio_file.read(MAX_AUDIO_BYTES + 1)
    if not data:
        raise HTTPException(400, detail={"code": "empty_audio", "message": "No audio received."})
    if len(data) > MAX_AUDIO_BYTES:
        raise HTTPException(413, detail={"code": "audio_too_large", "message": "Audio clip is too large."})
    try:
        r = await transcribe(data, audio_file.filename or "clip.wav",
                             audio_file.content_type or "audio/wav", language_code)
    except STTError as e:
        raise HTTPException(_status(e.code), detail={"code": e.code, "message": e.detail or "Speech recognition failed."})
    return TranscribeResponse(transcript=r["transcript"], language_code=language_code, model=r["model"])


@router.post("/synthesize")
async def synthesize_endpoint(req: SynthesizeRequest):
    if req.language_code not in LANGS:
        raise HTTPException(400, detail={"code": "bad_language", "message": f"Use one of {sorted(LANGS)}"})
    try:
        audio = await synthesize(req.text, req.language_code, req.speed)
    except TTSError as e:
        raise HTTPException(_status(e.code), detail={"code": e.code, "message": e.detail or "Speech synthesis failed."})
    return Response(content=audio, media_type="audio/mpeg")


@router.get("/usage")
def usage():
    return counter.summary()