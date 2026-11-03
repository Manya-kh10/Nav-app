import asyncio
import time

import httpx

from app.core.config import settings
from app.services.usage import counter

RETRY_STATUS = {429, 500, 503}


class STTError(Exception):
    def __init__(self, code: str, detail: str = ""):
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


async def transcribe(audio: bytes, filename: str, content_type: str, language_code: str) -> dict:
    if not settings.gnani_api_key:
        raise STTError("not_configured", "GNANI_API_KEY is missing in .env")
    url = f"{settings.gnani_base_url.rstrip('/')}/stt/v3"
    headers = {"X-API-Key-ID": settings.gnani_api_key}
    last = ""
    for attempt in range(2):
        t0 = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                r = await client.post(
                    url, headers=headers,
                    files={"audio_file": (filename, audio, content_type)},
                    data={"language_code": language_code, "format": "transcribe"},
                )
            counter.record("stt_call", lang=language_code, status=r.status_code,
                           ms=round((time.monotonic() - t0) * 1000))
            if r.status_code == 200:
                body = r.json()
                if body.get("success") is False:
                    raise STTError("stt_failed", str(body)[:200])
                return {
                    "transcript": (body.get("transcript") or "").strip(),
                    "model": body.get("model"),
                    "request_id": body.get("request_id"),
                }
            last = f"HTTP {r.status_code} {r.text[:200]}"
            if r.status_code not in RETRY_STATUS:
                raise STTError("stt_rejected", last)
        except (httpx.HTTPError, ValueError) as e:
            last = str(e) or type(e).__name__
        await asyncio.sleep(1.5)
    raise STTError("stt_unavailable", last)