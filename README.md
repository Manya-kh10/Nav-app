# Navora

A voice-first navigation assistant prototype for Bangalore, built for the **Great Indian AI Internship Challenge** by **Gnani.ai**. (The repository folder is still named `bangalore-voice-nav`.)

Uses Gnani.ai's **Prisma STT** (speech-to-text) and **Timbre TTS** (text-to-speech) with OpenStreetMap routing (public OSRM servers). Driver Mode can optionally use TomTom traffic data. No LLM is used: every turn, distance and landmark comes from map data and fixed templates.

> **Status:** hackathon prototype. Tested on a desktop browser at `localhost` only; not tested on a phone or in a vehicle. See [Known Limitations](#known-limitations).

---

## Key Features

1. **Voice-First Navigation & In-Trip Assistance:**
   - Spoken guidance and answers in English, Hindi and Hinglish. Kannada is built in but **unverified** (no native-speaker review).
   - Conversational query answering during trips: *"next turn?"*, *"how much delay?"*, *"am I on route?"*, *"how is the traffic ahead?"*.
   - Instant typed fallback if microphone permissions are denied or speech services are unreachable.

2. **Regulatory-Compliant Driver HUD (`/driver.html`):**
   - Designed with Rule 37 of the *Motor Vehicles (Driving) Regulations, 2017* in mind (navigation aids must not distract the driver). This has not been legally reviewed or tested in a vehicle.
   - High-contrast, dark-mode display with minimal visual noise and giant 72px touch targets.
   - Speed Lockout Hysteresis: Interface automatically locks visual inputs when traveling at or above 8 km/h, and only unlocks after vehicle remains below 3 km/h for more than 3 seconds.
   - Screen WakeLock management to keep the display active during vehicular travel.

3. **Auto / Cab Driver Card:**
   - One-tap visual and spoken Kannada destination card (`ದಯವಿಟ್ಟು ಇಲ್ಲಿಗೆ ಕರೆದುಕೊಂಡು ಹೋಗಿ: <destination>`) to help non-Kannada speakers show a destination to auto and taxi drivers. Kannada wording is unverified.

4. **Local POI Matching & Transliteration:**
   - 17,442 indexed Bangalore points of interest from OpenStreetMap (`data/bangalore_pois.json`).
   - Offline phonetic and consonant-skeleton matcher capable of resolving typos (*"kurban park"* → Cubbon Park), colloquial aliases (*"majestic bus stand"* → Kempegowda Bus Station), spacing variations (*"white field"* → Whitefield), and native scripts (Devanagari and Kannada).

5. **Live Traffic & Spatial Incident Filtering:**
   - Optional TomTom integration (Driver Mode only) reporting delay, delay percentage and traffic level (`none`, `light`, `heavy`). Only one live traffic reading has been taken during development; no claims are made about typical or peak-hour accuracy.
   - Incident alerts filtered strictly to obstacles within 60 meters of the road centerline and located ahead of the vehicle, rate-limited to at most 1 audio alert per 2 minutes.
   - Hard daily budget enforcement (default 400 calls/day) to prevent quota exhaustion, degrading gracefully to standard routing if limits are reached.

---

## Quick Start (Fresh Clone)

### Prerequisites
- Python 3.11+ (Python 3.12 or 3.14 compatible)
- Modern web browser (Chrome, Safari, Firefox, Edge)

### 1. Installation
Clone the repository, create a virtual environment, and install dependencies:
```bash
git clone https://github.com/your-repo/bangalore-voice-nav.git
cd bangalore-voice-nav
python -m venv .venv

# On Windows:
.venv\Scripts\activate

# On Linux/macOS:
source .venv/bin/activate

pip install -r requirements.txt
```

### 2. Environment Configuration (Optional)
The application starts and functions honestly without any `.env` file! If no API keys are present:
- Voice endpoints report clear, honest error messages (`stt_unavailable` / `tts_unavailable`).
- Typed search, walking routing, driving routing, GPS simulation, and turn guidance work completely out-of-the-box.

To enable live speech and live traffic services, copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
Fill in your credentials in `.env`:
```ini
GNANI_API_KEY=your_gnani_key
GNANI_BASE_URL=https://api.vachana.ai
GNANI_TTS_MODEL=timbre-v3.0
GNANI_TTS_VOICE=Shivani

TOMTOM_API_KEY=your_tomtom_key
TRAFFIC_DAILY_CAP=400
```

### 3. Run the Application
Start the FastAPI server from the `backend/` folder:
```bash
cd backend
uvicorn app.main:app --port 8001
```
Open your browser (add `?nosw=1` if an old cached UI appears):
- **Main (walking) UI:** [http://localhost:8001](http://localhost:8001)
- **Driver Mode:** [http://localhost:8001/driver.html](http://localhost:8001/driver.html)
- **Faster simulation:** append `?simspeed=12` (default multiplier is 6× walking speed).

The server has no authentication. Run it on `localhost` only; do not expose it publicly.

### 4. Run Automated Tests
From the project root:
```bash
python -m pytest tests -q
```
Last run (2026-11-10): `104 passed`. The tests mostly use mocked or in-process services, not live Gnani/TomTom calls.

---

## Evaluation Results & Benchmarks

All metrics reported below trace directly to raw evaluation artifacts in `eval/results/`:

| Benchmark | Sample Size ($n$) | Primary Metric | Result | Source Artifact |
|---|---|---|---|---|
| **GPS Replay Simulation** | 4 scenarios (walk 1.4 m/s & drive 10 m/s, clean & wrong-turn) | Arrival Rate | **100.0%** (4/4 arrived) | `eval/results/gps_replay_eval_20261109_121513.json` |
| **GPS Replay Simulation** | 4 scenarios (walk 1.4 m/s & drive 10 m/s, clean & wrong-turn) | Missed Turns / Duplicate Announcements | **0 duplicates, 0 missed** | `eval/results/gps_replay_eval_20261109_121513.json` |
| **Destination Search** | 11 multi-script cases | Top-1 & Top-3 Accuracy | **100.0%** Top-1 & Top-3 | `eval/results/destination_eval.json` |
| **Destination Latency** | 11 multi-script cases | Mean Search Latency | **143.2 ms** | `eval/results/destination_eval.json` |
| **GPS Replay Simulation** | 1 route (MG Road Metro → Indiranagar Metro, walk) | Arrived / Duplicates / Missed turns | **arrived, 0 duplicates, 0 missed** | `eval/results/gps_replay_eval_20261110_164812.json` |

These are small, self-written test sets. They do not measure speech recognition on real or noisy voice recordings. Earlier chat-intent and place-matcher figures came from scratch scripts that are not in this repository, so they are not reported here.

---

## Known Limitations

1. **Traffic Provider Dependency:** Real-time vehicular traffic delays and road incidents are sourced solely from TomTom. If the API key is absent, network fails, or the daily quota (400 calls/day) is exhausted, the application falls back honestly to free-flow estimates without traffic delays.
2. **Public OpenStreetMap Infrastructure:** Route geometry and online fallback geocoding rely on public OpenStreetMap servers (OSRM demo server and Nominatim). Under extreme network congestion, external routing requests may experience latency or 502 responses.
3. **Kannada is unverified:** Kannada guidance, answers and the driver-card phrase have not been reviewed by a native speaker. The language is labelled "unverified" in the UI.
4. **Small test sets:** Replay evaluation covers 5 scenarios on 2 corridors, and destination search covers 11 cases. No evaluation of speech recognition on real place names or noisy audio. Credits used per Gnani call are not measured.
5. **Not field-tested:** Tested only in a desktop browser on `localhost`. Not tested on a phone, outdoors with real GPS, or in a vehicle. Driver Mode thresholds (speed lockout) are not calibrated in a real car.
6. **Traffic data:** Only one TomTom reading has been taken. No claims about typical or peak-hour traffic. TomTom terms and attribution requirements have not been fully reviewed.
7. **Place names from OSM:** Some results show OSM names, e.g. the MG Road metro station appears as "Mahatma Gandhi Road (station)".
8. **No GPS-loss watchdog:** There is no "GPS signal lost" warning yet. Off-route detection (more than 40 m for 5 s) triggers a reroute.
9. **Language switch during navigation:** Changing the language while a simulation or live GPS session is running changes chat answers but does not re-translate the step list until navigation is stopped.
10. **No auth, localhost only:** There is no access control or demo token. Do not expose the server publicly.
11. **Mobile Browser Lifecycle:** The app relies on the Screen Wake Lock API. If the phone locks or the tab is switched, the OS may suspend timers and geolocation updates.

---

## Attribution & Licenses

- **OpenStreetMap Data:** © [OpenStreetMap contributors](https://www.openstreetmap.org/copyright), licensed under the [Open Database License (ODbL) 1.0](https://opendatacommons.org/licenses/odbl/).
- **Leaflet:** Interactive mapping engine licensed under the [BSD 2-Clause License](https://github.com/Leaflet/Leaflet/blob/main/LICENSE).
- **TomTom:** Traffic flow, incidents, and routing guidance powered by [TomTom Traffic & Routing APIs](https://docs.tomtom.com).
- **Gnani.ai:** Automatic speech recognition (Prisma STT) and speech synthesis (Timbre TTS) powered by [Gnani.ai](https://www.gnani.ai).

---

## Privacy Policy

- **Microphone Audio:** Audio recorded in the browser is sent to the local backend, which forwards it over HTTPS to Gnani.ai Prisma STT. The Gnani API key stays on the backend (`.env`) and is never sent to the browser. Audio bytes are not retained on server storage or logged to permanent storage.
- **Location Telemetry:** GPS latitude, longitude, and speed updates are processed strictly in-memory during active navigation sessions to calculate distance along route and detect turns. No user tracking history or coordinate trails are saved to databases or shared with third parties.
- **Traffic Queries:** When driving mode is active, only the route bounding box or origin/destination coordinates are sent to TomTom to fetch real-time traffic delays. No personally identifiable user information is transmitted.

