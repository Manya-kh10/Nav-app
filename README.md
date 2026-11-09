# Bangalore Voice Nav

A bilingual and trilingual conversational voice navigation web application engineered for Bangalore, built for the **Great Indian AI Internship Challenge** by **Gnani.ai**.

Powered by Gnani.ai's proprietary speech models—**Prisma STT** (Speech-to-Text) and **Timbre TTS** (Text-to-Speech)—combined with OpenStreetMap routing and TomTom real-time traffic intelligence.

---

## Key Features

1. **Voice-First Navigation & In-Trip Assistance:**
   - Spoken natural-language guidance in English, Hinglish, and Kannada.
   - Conversational query answering during trips: *"next turn?"*, *"how much delay?"*, *"am I on route?"*, *"how is the traffic ahead?"*.
   - Instant typed fallback if microphone permissions are denied or speech services are unreachable.

2. **Regulatory-Compliant Driver HUD (`/driver.html`):**
   - Built to comply with Rule 37 of the *Motor Vehicles (Driving) Regulations, 2017* (navigation aids must not distract the driver).
   - High-contrast, dark-mode display with minimal visual noise and giant 72px touch targets.
   - Speed Lockout Hysteresis: Interface automatically locks visual inputs when traveling at or above 8 km/h, and only unlocks after vehicle remains below 3 km/h for more than 3 seconds.
   - Screen WakeLock management to keep the display active during vehicular travel.

3. **Auto / Cab Driver Card:**
   - One-tap visual and spoken Kannada destination card (`ದಯವಿಟ್ಟು ಇಲ್ಲಿಗೆ ಕರೆದುಕೊಂಡು ಹೋಗಿ`) allowing non-Kannada speakers to communicate destinations clearly to local auto and taxi drivers.

4. **Local POI Matching & Transliteration:**
   - 18,700+ indexed Bangalore points of interest (stations, tech parks, hospitals, localities).
   - Offline phonetic and consonant-skeleton matcher capable of resolving typos (*"kurban park"* → Cubbon Park), colloquial aliases (*"majestic bus stand"* → Kempegowda Bus Station), spacing variations (*"white field"* → Whitefield), and native scripts (Devanagari and Kannada).

5. **Live Traffic & Spatial Incident Filtering:**
   - TomTom API integration calculating live delay, delay percentage, and traffic level (`none`, `light`, `heavy`).
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
Start the FastAPI server:
```bash
uvicorn backend.app.main:app --reload --port 8000
```
Open your browser:
- **Standard Navigation Web UI:** [http://localhost:8000](http://localhost:8000)
- **High-Contrast Driver Mode:** [http://localhost:8000/driver.html](http://localhost:8000/driver.html)

### 4. Run Automated Tests
```bash
pytest tests -q
```
Expected result: `46 passed`.

---

## Evaluation Results & Benchmarks

All metrics reported below trace directly to raw evaluation artifacts in `eval/results/`:

| Benchmark | Sample Size ($n$) | Primary Metric | Result | Source Artifact |
|---|---|---|---|---|
| **GPS Replay Simulation** | 4 scenarios (walk 1.4 m/s & drive 10 m/s, clean & wrong-turn) | Arrival Rate | **100.0%** (4/4 arrived) | `eval/results/gps_replay_eval_20261109_121513.json` |
| **GPS Replay Simulation** | 4 scenarios (walk 1.4 m/s & drive 10 m/s, clean & wrong-turn) | Missed Turns / Duplicate Announcements | **0 duplicates, 0 missed** | `eval/results/gps_replay_eval_20261109_121513.json` |
| **Destination Search** | 11 multi-script cases | Top-1 & Top-3 Accuracy | **100.0%** Top-1 & Top-3 | `eval/results/destination_eval.json` |
| **Destination Latency** | 11 multi-script cases | Mean Search Latency | **143.2 ms** | `eval/results/destination_eval.json` |
| **Conversational Chat Intents** | 25 test utterances | Intent Hit Rate | **92.0%** (23/25 hit rate) | Verified via `scratch/test_chat_25.py` |
| **Bangalore Place Matcher** | 23 real-world POI queries | Top-1 / Top-3 Accuracy | **95.7%** Top-1 / **100.0%** Top-3 | Verified via `scratch/test_places_25.py` |

---

## Known Limitations

1. **Traffic Provider Dependency:** Real-time vehicular traffic delays and road incidents are sourced solely from TomTom. If the API key is absent, network fails, or the daily quota (400 calls/day) is exhausted, the application falls back honestly to free-flow estimates without traffic delays.
2. **Public OpenStreetMap Infrastructure:** Route geometry and online fallback geocoding rely on public OpenStreetMap servers (OSRM demo server and Nominatim). Under extreme network congestion, external routing requests may experience latency or 502 responses.
3. **Kannada Spoken Phrasing:** Kannada driver audio templates and passenger card translations are research prototypes and have not yet undergone formal sign-off by a certified native Kannada linguist (`enable_kannada_driver` defaults to disabled in production configuration).
4. **Benchmark Sample Sizes:** Test benchmarks represent small holdout sets ($n=4$ replay routes, $n=25$ chat queries, $n=25$ place queries) calibrated specifically for Bangalore metropolitan landmarks.
5. **Driver HUD Calibration:** Driver mode thresholds and speed lockout logic are calibrated for automobiles and taxis operating under urban road speeds.
6. **Mobile Browser Lifecycle:** The web application relies on the browser Screen Wake Lock API. If the user locks the phone or switches browser tabs, background execution of JavaScript timers and geolocation updates may be suspended by the mobile operating system.

---

## Attribution & Licenses

- **OpenStreetMap Data:** © [OpenStreetMap contributors](https://www.openstreetmap.org/copyright), licensed under the [Open Database License (ODbL) 1.0](https://opendatacommons.org/licenses/odbl/).
- **Leaflet:** Interactive mapping engine licensed under the [BSD 2-Clause License](https://github.com/Leaflet/Leaflet/blob/main/LICENSE).
- **TomTom:** Traffic flow, incidents, and routing guidance powered by [TomTom Traffic & Routing APIs](https://docs.tomtom.com).
- **Gnani.ai:** Automatic speech recognition (Prisma STT) and speech synthesis (Timbre TTS) powered by [Gnani.ai](https://www.gnani.ai).

---

## Privacy Policy

- **Microphone Audio:** Audio recorded via the browser is transmitted over HTTPS to the backend for forwarding to Gnani.ai Prisma STT. Audio bytes are not retained on server storage or logged to permanent storage.
- **Location Telemetry:** GPS latitude, longitude, and speed updates are processed strictly in-memory during active navigation sessions to calculate distance along route and detect turns. No user tracking history or coordinate trails are saved to databases or shared with third parties.
- **Traffic Queries:** When driving mode is active, only the route bounding box or origin/destination coordinates are sent to TomTom to fetch real-time traffic delays. No personally identifiable user information is transmitted.

