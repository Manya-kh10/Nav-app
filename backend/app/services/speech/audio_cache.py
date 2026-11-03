import hashlib

from app.core.config import ROOT

CACHE_DIR = ROOT / "data" / "audio_cache"


def make_key(*parts) -> str:
    return hashlib.sha256("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()


def get(key: str) -> bytes | None:
    f = CACHE_DIR / f"{key}.mp3"
    return f.read_bytes() if f.exists() else None


def put(key: str, data: bytes) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    (CACHE_DIR / f"{key}.mp3").write_bytes(data)