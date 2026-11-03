import asyncio
import time

import httpx

from app.core.config import settings
from app.services.speech import audio_cache
from app.services.usage import counter

RETRY_STATUS = {429, 500, 503}


class TTSError(Exception):
    def __init__(self, code: str, detail: str = ""):
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


async def synthesize(text: str, language_code: str, speed: float = 1.0) -> bytes:
    if not settings.gnani_api_key:
        raise TTSError("not_configured", "GNANI_API_KEY is missing in .env")
    model, voice = settings.gnani_tts_model, settings.gnani_tts_voice
    key = audio_cache.make_key(model, voice, language_code, speed, text)
    cached = audio_cache.get(key)
    if cached:
        counter.record("tts_cache_hit", lang=language_code, chars=len(text))
        return cached

    url = f"{settings.gnani_base_url.rstrip('/')}/api/v1/tts/inference"
    headers = {"X-API-Key-ID": settings.gnani_api_key, "Content-Type": "application/json"}
    payload = {
        "text": text, "voice": voice, "model": model, "language": language_code, "speed": speed,
        "audio_config": {"container": "mp3", "bitrate": "64k", "sample_rate": 24000},
    }
    last = ""
    for attempt in range(2):
        t0 = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                r = await client.post(url, headers=headers, json=payload)
            counter.record("tts_call", lang=language_code, chars=len(text), status=r.status_code,
                           ms=round((time.monotonic() - t0) * 1000))
            ctype = r.headers.get("content-type", "")
            if r.status_code == 200 and ("audio" in ctype or "octet" in ctype) and r.content:
                audio_cache.put(key, r.content)
                return r.content
            last = f"HTTP {r.status_code} ({ctype}) {r.text[:200] if 'audio' not in ctype else ''}"
            if r.status_code not in RETRY_STATUS:
                raise TTSError("tts_rejected", last)
        except httpx.HTTPError as e:
            last = str(e) or type(e).__name__
        await asyncio.sleep(1.5)
    raise TTSError("tts_unavailable", last)