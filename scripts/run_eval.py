"""Destination-Resolution Accuracy & Latency Evaluation.
Evaluates spoken place clips (via Gnani Prisma STT) and query strings through the place matching pipeline.
Outputs a summary table and saves detailed JSON to eval/results/destination_eval.json.
"""
import asyncio
import json
import os
import sys
import time
from pathlib import Path

import httpx

# Reconfigure stdout for Windows terminal UTF-8 safety
if sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.services.places.search import search_places

CLIPS_DIR = ROOT / "data" / "clips"
RESULTS_DIR = ROOT / "eval" / "results"
RESULTS_FILE = RESULTS_DIR / "destination_eval.json"


def load_env() -> dict[str, str]:
    env = {}
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    return env


# Benchmark suite: the 5 planned voice clips + robustness variations
BENCHMARK_CASES = [
    {
        "id": "place1",
        "clip": "place1.m4a",
        "language_code": "kn-IN",
        "spoken": "Indiranagar Metro Station",
        "text_input": "ಇಂದಿರಾನಗರ ಮೆಟ್ರೋ ಸ್ಟೇಷನ್",
        "expected": ["Indiranagar Metro Station", "Indiranagar"],
    },
    {
        "id": "place2",
        "clip": "place2.m4a",
        "language_code": "hi-IN",
        "spoken": "Majestic bus stand",
        "text_input": "मजेस्टिक बस स्टैंड",
        "expected": ["Kempegowda Bus Station", "Majestic"],
    },
    {
        "id": "place3",
        "clip": "place3.m4a",
        "language_code": "en-IN",
        "spoken": "Koramangala Forum Mall",
        "text_input": "Koramangala Forum Mall",
        "expected": ["Nexus Koramangala", "Forum Mall"],
    },
    {
        "id": "place4",
        "clip": "place4.m4a",
        "language_code": "kn-IN",
        "spoken": "Halasuru",
        "text_input": "ಹಲಸೂರು",
        "expected": ["Halasuru"],
    },
    {
        "id": "place5",
        "clip": "place5.m4a",
        "language_code": "en-IN",
        "spoken": "MG Road metro kaise jaaun",
        "text_input": "MG Road metro kaise jaaun",
        "expected": ["Mahatma Gandhi Road", "MG Road Metro Station"],
    },
    # Robustness text cases (colloquialisms, typos, scripts)
    {
        "id": "text_kr_market_en",
        "clip": None,
        "language_code": "en-IN",
        "spoken": "kr market",
        "text_input": "kr market",
        "expected": ["Krishna Rajendra Market", "KR Market"],
    },
    {
        "id": "text_kr_market_hi",
        "clip": None,
        "language_code": "hi-IN",
        "spoken": "के आर मार्केट",
        "text_input": "के आर मार्केट",
        "expected": ["Krishna Rajendra Market", "KR Market"],
    },
    {
        "id": "text_silk_board",
        "clip": None,
        "language_code": "en-IN",
        "spoken": "silk board",
        "text_input": "silk board",
        "expected": ["Central Silk Board"],
    },
    {
        "id": "text_town_hall",
        "clip": None,
        "language_code": "en-IN",
        "spoken": "town hall",
        "text_input": "town hall",
        "expected": ["Sir Puttanna Chetty Town Hall", "Town Hall"],
    },
    {
        "id": "text_typo_indra",
        "clip": None,
        "language_code": "en-IN",
        "spoken": "indra nagar metro",
        "text_input": "indra nagar metro",
        "expected": ["Indiranagar Metro Station", "Indiranagar"],
    },
    {
        "id": "text_typo_koramangla",
        "clip": None,
        "language_code": "en-IN",
        "spoken": "koramangla",
        "text_input": "koramangla",
        "expected": ["Koramangala"],
    },
]


async def transcribe_clip(client: httpx.AsyncClient, base_url: str, api_key: str, clip_path: Path, lang: str):
    url = f"{base_url.rstrip('/')}/stt/v3"
    t0 = time.perf_counter()
    with clip_path.open("rb") as f:
        r = await client.post(
            url,
            headers={"X-API-Key-ID": api_key},
            files={"audio_file": (clip_path.name, f, "audio/mp4")},
            data={"language_code": lang, "format": "transcribe"},
            timeout=30.0,
        )
    dt_ms = (time.perf_counter() - t0) * 1000
    if r.status_code == 200:
        data = r.json()
        transcript = data.get("transcript", "").strip()
        return transcript, dt_ms, None
    return "", dt_ms, f"HTTP {r.status_code}: {r.text[:200]}"


def matches_expected(place_name: str, expected_list: list[str]) -> bool:
    pn = place_name.lower()
    for exp in expected_list:
        en = exp.lower()
        if en in pn or pn in en:
            return True
    return False


async def run_evaluation():
    env = load_env()
    api_key = env.get("GNANI_API_KEY", "")
    base_url = env.get("GNANI_BASE_URL", "https://api.vachana.ai")

    has_gnani = bool(api_key and "paste_your_key" not in api_key)
    print("=" * 80)
    print(" BANGALORE VOICE NAV: DESTINATION-RESOLUTION EVALUATION")
    print("=" * 80)
    print(f"Gnani API Key Configured: {'Yes' if has_gnani else 'No (audio clips will be skipped)'}")
    print(f"Clips Directory: {CLIPS_DIR}")
    print("-" * 80)

    results = []
    top1_count = 0
    top3_count = 0
    total_search_ms = 0.0

    async with httpx.AsyncClient() as client:
        for case in BENCHMARK_CASES:
            cid = case["id"]
            lang = case["language_code"]
            expected = case["expected"]
            clip_file = CLIPS_DIR / case["clip"] if case.get("clip") else None

            transcript = None
            stt_ms = None
            stt_error = None

            # 1. Transcribe audio if clip exists and API is configured
            if clip_file and clip_file.exists() and has_gnani:
                transcript, stt_ms, stt_error = await transcribe_clip(
                    client, base_url, api_key, clip_file, lang
                )
                search_query = transcript or case["text_input"]
                mode = "audio+stt"
            elif clip_file and not clip_file.exists():
                search_query = case["text_input"]
                mode = "text (clip pending)"
            else:
                search_query = case["text_input"]
                mode = "text benchmark"

            # 2. Run Place Search
            t0 = time.perf_counter()
            places = await search_places(search_query, limit=5)
            search_ms = (time.perf_counter() - t0) * 1000
            total_search_ms += search_ms

            # 3. Check Rank
            top_place = places[0] if places else None
            top_name = top_place.name if top_place else "None"
            top_score = top_place.score if top_place else 0.0

            rank = None
            for idx, p in enumerate(places):
                if matches_expected(p.name, expected):
                    rank = idx + 1
                    break

            is_top1 = rank == 1
            is_top3 = rank is not None and rank <= 3
            if is_top1:
                top1_count += 1
            if is_top3:
                top3_count += 1

            res = {
                "id": cid,
                "mode": mode,
                "language": lang,
                "spoken": case["spoken"],
                "query_used": search_query,
                "expected": expected[0],
                "matched_top": top_name,
                "score": top_score,
                "rank": rank if rank is not None else ">5",
                "stt_ms": round(stt_ms, 1) if stt_ms is not None else None,
                "search_ms": round(search_ms, 1),
                "is_top1": is_top1,
                "is_top3": is_top3,
                "stt_error": stt_error,
            }
            results.append(res)

    # 4. Print Formatted Table
    header = f"{'Case ID':<22} | {'Lang':<5} | {'Input Query / Transcript':<30} | {'Expected Target':<26} | {'Top Match':<26} | {'Rank':<4} | {'Latency':<8}"
    print(header)
    print("-" * len(header))
    for r in results:
        status_rank = f"#{r['rank']}" if isinstance(r['rank'], int) else "FAIL"
        lat = f"{r['search_ms']}ms"
        if r['stt_ms']:
            lat = f"{r['stt_ms']:.0f}+{r['search_ms']:.0f}ms"
        q_disp = r['query_used'][:28] + ".." if len(r['query_used']) > 30 else r['query_used']
        exp_disp = r['expected'][:24] + ".." if len(r['expected']) > 26 else r['expected']
        top_disp = r['matched_top'][:24] + ".." if len(r['matched_top']) > 26 else r['matched_top']
        print(f"{r['id']:<22} | {r['language']:<5} | {q_disp:<30} | {exp_disp:<26} | {top_disp:<26} | {status_rank:<4} | {lat:<8}")

    total = len(results)
    top1_pct = (top1_count / total) * 100
    top3_pct = (top3_count / total) * 100
    avg_search_lat = total_search_ms / total

    print("=" * 80)
    print(" SUMMARY METRICS:")
    print(f" Total Test Cases:          {total}")
    print(f" Top-1 Match Accuracy:      {top1_count}/{total} ({top1_pct:.1f}%)")
    print(f" Top-3 Match Accuracy:      {top3_count}/{total} ({top3_pct:.1f}%)")
    print(f" Mean Search Latency:       {avg_search_lat:.1f} ms")
    print("=" * 80)

    # Save to JSON
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    summary_data = {
        "timestamp": time.time(),
        "total": total,
        "top1_accuracy_pct": round(top1_pct, 1),
        "top3_accuracy_pct": round(top3_pct, 1),
        "mean_search_latency_ms": round(avg_search_lat, 1),
        "cases": results,
    }
    RESULTS_FILE.write_text(json.dumps(summary_data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved evaluation results -> {RESULTS_FILE}")


if __name__ == "__main__":
    asyncio.run(run_evaluation())
