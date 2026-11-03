"""Kannada test: Prisma STT on a recorded clip + Timbre TTS with Kannada-capable voices."""
import json
import sys
import time
from pathlib import Path

import httpx

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
CLIP = ROOT / "data" / "clips" / "kn_test1.m4a"
OUT = ROOT / "eval" / "results"

# (label, voice, model) - v3.0 voices speak all 10 languages; Saanvi/Kavin are the v2.5 Kannada voices
TTS_CASES = [
    ("v30_shivani_words", "Shivani", "timbre-v3.0", "ನೂರು ಮೀಟರ್ ನಂತರ ಎಡಕ್ಕೆ ತಿರುಗಿ."),
    ("v30_shivani_digits", "Shivani", "timbre-v3.0", "100 ಮೀಟರ್ ನಂತರ ಎಡಕ್ಕೆ ತಿರುಗಿ."),
    ("v25_saanvi_words", "Saanvi", "timbre-v2.5", "ನೂರು ಮೀಟರ್ ನಂತರ ಎಡಕ್ಕೆ ತಿರುಗಿ."),
    ("v25_kavin_words", "Kavin", "timbre-v2.5", "ನೂರು ಮೀಟರ್ ನಂತರ ಎಡಕ್ಕೆ ತಿರುಗಿ."),
]


def load_env():
    env = {}
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def test_stt(client, base, key):
    print("== STT (Prisma, kn-IN) ==")
    if not CLIP.exists():
        print(f"clip not found: {CLIP}")
        return
    t0 = time.time()
    with CLIP.open("rb") as f:
        r = client.post(
            f"{base}/stt/v3",
            headers={"X-API-Key-ID": key},
            files={"audio_file": (CLIP.name, f, "audio/mp4")},
            data={"language_code": "kn-IN", "format": "transcribe"},
        )
    dt = time.time() - t0
    print(f"HTTP {r.status_code} in {dt:.1f}s")
    try:
        body = r.json()
    except Exception:
        print(r.text[:500])
        return
    print(json.dumps(body, ensure_ascii=False, indent=2))
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "stt_kn_test1.json").write_text(json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8")


def test_tts(client, base, key, tts_model_default):
    print("\n== TTS (Timbre, kn-IN) ==")
    OUT.mkdir(parents=True, exist_ok=True)
    for label, voice, model, text in TTS_CASES:
        payload = {
            "text": text, "voice": voice, "model": model, "language": "kn-IN", "speed": 1.0,
            "audio_config": {"container": "mp3", "bitrate": "64k", "sample_rate": 24000},
        }
        t0 = time.time()
        r = client.post(f"{base}/api/v1/tts/inference",
                        headers={"X-API-Key-ID": key, "Content-Type": "application/json"},
                        json=payload)
        dt = time.time() - t0
        ctype = r.headers.get("content-type", "")
        if r.status_code == 200 and ("audio" in ctype or "octet" in ctype):
            path = OUT / f"tts_kn_{label}.mp3"
            path.write_bytes(r.content)
            print(f"[OK ] {label}: {len(r.content)} bytes, {dt:.1f}s -> {path.name}")
        else:
            print(f"[ERR] {label}: HTTP {r.status_code} ({ctype}) {r.text[:300]}")


def main():
    env = load_env()
    key = env.get("GNANI_API_KEY", "")
    base = env.get("GNANI_BASE_URL", "https://api.vachana.ai").rstrip("/")
    if not key or "paste_your_key" in key:
        print("Set GNANI_API_KEY in .env first")
        return
    with httpx.Client(timeout=60) as client:
        test_stt(client, base, key)
        test_tts(client, base, key, env.get("GNANI_TTS_MODEL", "timbre-v3.0"))
    print("\nDone. Play the .mp3 files in eval\\results and compare the transcript with what you said.")


if __name__ == "__main__":
    main()