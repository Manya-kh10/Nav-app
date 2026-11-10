import { searchPlaces, getGuide, sendPosition, sendReroute, sendChat } from "./api.js";
import { startGpsTracking } from "./gps.js";
import { startSimulation } from "./sim.js";
import { speak, stopAudio, playChime, startRecording, stopRecording, toWav16k, transcribe } from "./voice.js";

const $ = (id) => document.getElementById(id);

// State
let sessionId = null;
let currentGuide = null;
let gpsTracker = null;
let simTracker = null;
let isDriving = false;
let isMuted = false;
let wakeLock = null;
let lastAnnouncementText = "";
let currentLang = "en";

// Speed lockout hysteresis
let isLocked = false;
let belowThresholdSince = 0;

// Recording state for Ask button
let isAsking = false;
let askTimeout = null;

// Maneuver SVG icons
const ICONS = {
    left: `<svg viewBox="0 0 24 24"><path d="M9 10V6l-7 7 7 7v-4h6c3.87 0 7-3.13 7-7v-3h-4v3c0 1.66-1.34 3-3 3H9z"/></svg>`,
    right: `<svg viewBox="0 0 24 24"><path d="M15 10V6l7 7-7 7v-4H9c-3.87 0-7-3.13-7-7v-3h4v3c0 1.66 1.34 3 3 3h6z"/></svg>`,
    straight: `<svg viewBox="0 0 24 24"><path d="M12 2L4 10h5v12h6V10h5z"/></svg>`,
    uturn: `<svg viewBox="0 0 24 24"><path d="M18 13v-3c0-3.87-3.13-7-7-7S4 6.13 4 10v9H8v-9c0-1.66 1.34-3 3-3s3 1.34 3 3v3H11l5 6 5-6h-3z"/></svg>`,
    roundabout: `<svg viewBox="0 0 24 24"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 17.93c-3.95-.49-7-3.85-7-7.93 0-.62.08-1.21.21-1.79L9 13v-3l-6 1.5 1.5 6 1.77-1.77C8.16 17.82 10.42 19 13 19v.93zm5.79-4.14L17 14v3l6-1.5-1.5-6-1.77 1.77C18.84 9.18 16.58 8 14 8V7.07c3.95.49 7 3.85 7 7.93 0 .62-.08 1.21-.21 1.79z"/></svg>`,
    arrive: `<svg viewBox="0 0 24 24"><path d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5c-1.38 0-2.5-1.12-2.5-2.5s1.12-2.5 2.5-2.5 2.5 1.12 2.5 2.5-1.12 2.5-2.5 2.5z"/></svg>`,
};

function getManeuverSvg(step) {
    if (!step) return ICONS.straight;
    if (step.maneuver === "arrive") return ICONS.arrive;
    if (step.maneuver?.includes("roundabout") || step.maneuver?.includes("rotary")) return ICONS.roundabout;
    if (step.modifier === "uturn") return ICONS.uturn;
    if (step.modifier?.includes("left")) return ICONS.left;
    if (step.modifier?.includes("right")) return ICONS.right;
    return ICONS.straight;
}

// -------------------------------------------------------------
// WAKELOCK & SCREEN VISIBILITY
// -------------------------------------------------------------
async function requestWakeLock() {
    try {
        if ("wakeLock" in navigator) {
            wakeLock = await navigator.wakeLock.request("screen");
            $("badge-wakelock").textContent = "LOCK 🔒";
            $("badge-wakelock").className = "status-badge active";
            wakeLock.addEventListener("release", () => {
                if (isDriving) {
                    $("badge-wakelock").textContent = "LOCK LOST ⚠️";
                    $("badge-wakelock").className = "status-badge warning";
                    showWakeLockWarning();
                }
            });
        }
    } catch (err) {
        console.warn("WakeLock request error:", err);
    }
}

function showWakeLockWarning() {
    $("warning-banner").style.display = "block";
}

function hideWakeLockWarning() {
    $("warning-banner").style.display = "none";
}

document.addEventListener("visibilitychange", async () => {
    if (!isDriving) return;
    if (document.visibilityState === "visible") {
        hideWakeLockWarning();
        await requestWakeLock();
    } else {
        showWakeLockWarning();
        if (!isMuted) {
            speak("Screen lost. Keep the app open.", "en-IN").catch(() => {});
        }
    }
});

// -------------------------------------------------------------
// AUDIO PLAYBACK & QUEUE MANAGEMENT
// -------------------------------------------------------------
let currentTrackingSessionId = null;
let lastAnnouncementId = 0;
const ttsCode = (l) => ({ en: "en-IN", hi: "hi-IN", hinglish: "hi-IN", kn: "kn-IN" }[l] || "en-IN");

function playAnnouncement(ann) {
    if (!ann) return;
    if (ann.session_id && ann.session_id !== currentTrackingSessionId) {
        currentTrackingSessionId = ann.session_id;
        lastAnnouncementId = 0;
    }
    if (ann.id && ann.id <= lastAnnouncementId) return;
    if (ann.id) lastAnnouncementId = ann.id;
    if (ann.text) lastAnnouncementText = ann.text;

    if (ann.chime) {
        playChime();
    }

    if (ann.speak && ann.text && !isMuted) {
        const lang = ann.lang || ann.language || currentLang;
        speak(ann.text, ttsCode(lang)).catch((e) => {
            console.warn("Spoken guidance failed:", e);
        });
    }
}

// -------------------------------------------------------------
// SETUP SCREEN & PLACE PICKER
// -------------------------------------------------------------
const startState = {
    from: { lat: 12.9716, lon: 77.5946, name: "Current GPS Location" },
    to: null,
};

function setupSearch(type) {
    const input = $(`${type}-input`);
    const searchBtn = $(`${type}-search`);
    const results = $(`${type}-results`);
    const chosen = $(`${type}-chosen`);

    input.addEventListener("keydown", (e) => {
        if (e.key === "Enter") searchBtn.click();
    });

    searchBtn.addEventListener("click", async () => {
        const q = input.value.trim();
        if (q.length < 2) return;
        results.textContent = "Searching...";
        try {
            const places = await searchPlaces(q);
            results.textContent = "";
            if (!places.length) {
                results.textContent = "No matches found. Try another place.";
                return;
            }
            places.forEach((p) => {
                const b = document.createElement("button");
                b.textContent = p.name;
                b.addEventListener("click", () => {
                    startState[type] = { lat: p.lat, lon: p.lon, name: p.name };
                    chosen.textContent = `Selected: ${p.name}`;
                    results.textContent = "";
                    checkReadyForPreview();
                });
                results.appendChild(b);
            });
        } catch (err) {
            results.textContent = err.message || "Search failed.";
        }
    });
}

async function checkReadyForPreview() {
    if (!startState.to) return;
    $("setup-status").textContent = "Calculating route...";

    // Acquire accurate GPS position for origin if using default
    if (startState.from.name === "Current GPS Location" && navigator.geolocation) {
        await new Promise((resolve) => {
            navigator.geolocation.getCurrentPosition(
                (pos) => {
                    const lat = pos.coords.latitude;
                    const lon = pos.coords.longitude;
                    // Only use GPS if within Bangalore region (~12.75 - 13.25 lat, 77.35 - 77.85 lon)
                    if (lat >= 12.75 && lat <= 13.25 && lon >= 77.35 && lon <= 77.85) {
                        startState.from.lat = lat;
                        startState.from.lon = lon;
                    } else {
                        // User is outside Bangalore! Keep default central Bangalore origin (Vidhana Soudha area)
                        startState.from = { lat: 12.9716, lon: 77.5946, name: "Bangalore Center" };
                    }
                    resolve();
                },
                () => resolve(), // fallback to default Bangalore center
                { timeout: 3000, enableHighAccuracy: true }
            );
        });
    }

    try {
        const lang = $("driver-lang")?.value || "en";
        const guide = await getGuide(startState.from, startState.to, "drive", lang);
        currentGuide = guide;
        sessionId = guide.session_id;

        const km = (guide.route.distance_m / 1000).toFixed(1);
        const mins = Math.max(1, Math.round(guide.route.duration_s / 60));

        $("prev-dist").textContent = `${km} km`;
        $("prev-time").textContent = `${mins} min`;
        $("prev-turns").textContent = guide.route.steps.length;

        if (guide.route.traffic) {
            const t = guide.route.traffic;
            const delayNote = t.delay_minutes > 0 ? ` (+${t.delay_minutes}m)` : "";
            $("prev-traffic").textContent = `${t.level.toUpperCase()}${delayNote}`;
            $("badge-traffic").textContent = `TRAFFIC: ${t.level.toUpperCase()}`;
            $("badge-traffic").className = t.level === "heavy" ? "status-badge warning" : "status-badge active";
        } else {
            $("prev-traffic").textContent = "N/A";
            $("badge-traffic").textContent = "NO TRAFFIC DATA";
            $("badge-traffic").className = "status-badge";
        }

        $("route-preview").style.display = "grid";
        $("btn-start-drive").disabled = false;
        if ($("btn-sim-drive")) $("btn-sim-drive").disabled = false;
        $("setup-status").textContent = "Route ready. Tap START DRIVING or SIMULATE DRIVE.";
    } catch (err) {
        $("setup-status").textContent = err.message || "Could not calculate route.";
    }
}

// -------------------------------------------------------------
// SPEED LOCKOUT HYSTERESIS
// -------------------------------------------------------------
function updateSpeedLockout(speedMps) {
    const kmh = Math.round(speedMps * 3.6);
    $("hud-speed").textContent = kmh;

    const lockoutBanner = $("lockout-banner");

    if (kmh >= 8) {
        belowThresholdSince = 0;
        if (!isLocked) {
            isLocked = true;
            lockoutBanner.classList.add("active");
        }
    } else if (kmh < 3) {
        const now = Date.now();
        if (belowThresholdSince === 0) {
            belowThresholdSince = now;
        } else if (now - belowThresholdSince >= 3000) {
            // Speed held < 3 km/h for 3 continuous seconds
            if (isLocked) {
                isLocked = false;
                lockoutBanner.classList.remove("active");
            }
        }
    } else {
        // Between 3 and 8 km/h: hold existing state
        belowThresholdSince = 0;
    }
}

// -------------------------------------------------------------
// NAVIGATION HUD UPDATES
// -------------------------------------------------------------
function updateHud(status) {
    // 1. Next Maneuver distance & instruction
    if (status.distance_to_next_m !== null && status.distance_to_next_m !== undefined) {
        const d = status.distance_to_next_m;
        if (d >= 1000) {
            $("hud-distance").textContent = `${(d / 1000).toFixed(1)} km`;
        } else {
            $("hud-distance").textContent = `${Math.round(d)} m`;
        }
    } else if (status.arrived) {
        $("hud-distance").textContent = "ARRIVED";
    }

    if (status.guidance) {
        $("hud-instruction").textContent = status.guidance.text;
    } else if (status.next_text) {
        $("hud-instruction").textContent = status.next_text;
    }

    // 2. Icon
    if (currentGuide && status.next_index !== null && currentGuide.route.steps[status.next_index]) {
        const step = currentGuide.route.steps[status.next_index];
        $("hud-maneuver-icon").innerHTML = getManeuverSvg(step);
    } else if (status.arrived) {
        $("hud-maneuver-icon").innerHTML = ICONS.arrive;
    }

    // 3. Landmark
    if (currentGuide && status.next_index !== null) {
        const lm = currentGuide.instructions?.[status.next_index]?.landmark;
        if (lm) {
            $("hud-landmark").textContent = `📍 near ${lm}`;
            $("hud-landmark").style.display = "inline-block";
        } else {
            $("hud-landmark").style.display = "none";
        }
    }

    // 4. Remaining time & distance with live calculated clock ETA
    const remKm = (status.remaining_m / 1000).toFixed(1);
    const remMin = Math.max(0, Math.round(status.remaining_s / 60));
    const etaDate = new Date(Date.now() + (status.remaining_s || 0) * 1000);
    const etaTimeStr = etaDate.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    $("hud-remaining-dist").textContent = `${remKm} km`;
    $("hud-eta").textContent = `${remMin} min · ${etaTimeStr}`;

    // 5. GPS badge
    $("badge-gps").textContent = status.gps_quality === "ok" ? "GPS OK" : "POOR GPS";
    $("badge-gps").className = status.gps_quality === "ok" ? "status-badge active" : "status-badge warning";

    // 6. Proactive Announcement
    if (status.announcement) {
        playAnnouncement(status.announcement);
    }
}

function stopAllTracking() {
    if (gpsTracker) {
        gpsTracker.stop();
        gpsTracker = null;
    }
    if (simTracker) {
        simTracker.stop();
        simTracker = null;
    }
    isDriving = false;
    stopAudio();
}

// -------------------------------------------------------------
// START DRIVING
// -------------------------------------------------------------
async function startDriving(simulated = false) {
    if (!sessionId) return;
    stopAllTracking();
    isDriving = true;
    lastAnnouncementId = 0;
    currentTrackingSessionId = sessionId;
    stopAudio();
    currentLang = $("driver-lang").value;

    $("setup-screen").style.display = "none";
    $("driving-screen").style.display = "flex";

    await requestWakeLock();

    // Initial spoken confirmation with live traffic summary if available
    let startMsg = "Starting route guidance. Phone fixed on dashboard.";
    if (currentLang === "kn") {
        startMsg = "ಮಾರ್ಗದರ್ಶನ ಪ್ರಾರಂಭಿಸಲಾಗುತ್ತಿದೆ. ಮೊಬೈಲ್ ಡ್ಯಾಶ್‌ಬೋರ್ಡ್‌ನಲ್ಲಿ ಫಿಕ್ಸ್ ಮಾಡಲಾಗಿದೆ.";
    } else if (currentLang === "hi") {
        startMsg = "मार्गदर्शन शुरू हो रहा है। फ़ोन डैशबोर्ड पर लगा है।";
    } else if (currentLang === "hinglish") {
        startMsg = "Route guidance shuru ho rahi hai. Phone dashboard par laga hai.";
    }
    if (currentGuide?.route?.traffic?.spoken_summary) {
        startMsg = currentGuide.route.traffic.spoken_summary;
    }
    playAnnouncement({
        text: startMsg,
        stage: "now",
        priority: "high",
        language: currentLang,
    });

    if (simulated) {
        $("badge-gps").textContent = "SIM DRIVE 36 km/h";
        $("badge-gps").className = "status-badge active";
        const simSpeedMps = 10.0; // 36 km/h
        updateSpeedLockout(simSpeedMps);

        simTracker = startSimulation({
            geometry: currentGuide.route.geometry,
            sessionId,
            wrongTurn: false,
            stepM: 30, // 30m steps per tick
            tickMs: 1200,
            api: {
                position: (sid, lat, lon, acc, ts) =>
                    sendPosition(sid, lat, lon, acc, ts, simSpeedMps, currentLang),
                reroute: (sid, lat, lon, acc, ts) =>
                    sendReroute(sid, lat, lon, acc, ts),
            },
            onTick: ({ status }) => {
                updateSpeedLockout(simSpeedMps);
                updateHud(status);
            },
            onReroute: (newGuide) => {
                lastAnnouncementId = 0;
                currentTrackingSessionId = newGuide.session_id || sessionId;
                stopAudio();
                currentGuide = newGuide;
                if (newGuide.message) {
                    playAnnouncement({
                        text: newGuide.message,
                        stage: "reroute",
                        priority: "high",
                        language: currentLang,
                    });
                }
            },
            onEnd: () => {
                updateSpeedLockout(0);
                playAnnouncement({
                    text: currentLang === "kn" ? "ನೀವು ನಿಮ್ಮ ಗಮ್ಯಸ್ಥಾನವನ್ನು ತಲುಪಿದ್ದೀರಿ." : "You have arrived at your destination.",
                    stage: "arrival",
                    priority: "high",
                    language: currentLang,
                });
            },
            onError: (err) => {
                console.warn("Simulation error:", err);
            },
        });
        return;
    }

    // Start Live GPS tracking
    gpsTracker = startGpsTracking({
        sessionId,
        api: {
            position: (sid, lat, lon, acc, ts, spd) =>
                sendPosition(sid, lat, lon, acc, ts, spd, currentLang),
            reroute: (sid, lat, lon, acc, ts) =>
                sendReroute(sid, lat, lon, acc, ts),
        },
        onTick: ({ status, speed }) => {
            const currentSpeed = speed || status.speed_mps || 0;
            updateSpeedLockout(currentSpeed);
            updateHud(status);
        },
        onReroute: (newGuide) => {
            lastAnnouncementId = 0;
            currentTrackingSessionId = newGuide.session_id || sessionId;
            stopAudio();
            currentGuide = newGuide;
            if (newGuide.message) {
                playAnnouncement({
                    text: newGuide.message,
                    stage: "reroute",
                    priority: "high",
                    language: currentLang,
                });
            }
        },
        onEnd: () => {
            playAnnouncement({
                text: "You have arrived at your destination.",
                stage: "arrival",
                priority: "high",
                language: currentLang,
            });
        },
        onError: (err) => {
            console.warn("GPS error:", err);
            $("badge-gps").textContent = "GPS ERR";
            $("badge-gps").className = "status-badge warning";
        },
        minIntervalMs: 1500,
    });
}

// -------------------------------------------------------------
// THREE DASHBOARD BUTTONS
// -------------------------------------------------------------

// 1. REPEAT
$("btn-repeat").addEventListener("click", async () => {
    if (lastAnnouncementText && !isMuted) {
        let ttsLang = "en-IN";
        if (currentLang === "kn") ttsLang = "kn-IN";
        else if (currentLang === "hinglish" || currentLang === "hi") ttsLang = "hi-IN";
        stopAudio();
        speak(lastAnnouncementText, ttsLang).catch(() => {});
        return;
    }
    if (sessionId) {
        try {
            const res = await sendChat(sessionId, "repeat", true);
            playAnnouncement({
                text: res.text,
                stage: "near",
                priority: "normal",
                language: res.lang || currentLang,
            });
        } catch (err) {
            console.warn("Repeat failed:", err);
        }
    }
});

// 2. ASK (One-tap voice query)
$("btn-ask").addEventListener("click", async () => {
    const askBtn = $("btn-ask");
    const askText = $("ask-btn-text");

    if (isAsking) {
        // Tap to finish recording early
        clearTimeout(askTimeout);
        await finishAsk();
        return;
    }

    try {
        await startRecording();
        isAsking = true;
        askBtn.classList.add("listening");
        askText.textContent = "LISTENING...";

        // Auto-stop at 8 seconds
        askTimeout = setTimeout(async () => {
            if (isAsking) await finishAsk();
        }, 8000);
    } catch (err) {
        console.warn("Could not start recording:", err);
        askText.textContent = "MIC ERR";
        setTimeout(() => { askText.textContent = "ASK"; }, 2000);
    }
});

async function finishAsk() {
    isAsking = false;
    clearTimeout(askTimeout);
    const askBtn = $("btn-ask");
    const askText = $("ask-btn-text");

    askBtn.classList.remove("listening");
    askText.textContent = "PROCESSING...";

    try {
        const rawBlob = await stopRecording();
        const wav = await toWav16k(rawBlob);

        let ttsLang = "en-IN";
        if (currentLang === "kn") ttsLang = "kn-IN";
        else if (currentLang === "hinglish" || currentLang === "hi") ttsLang = "hi-IN";

        const { transcript } = await transcribe(wav, ttsLang);
        if (transcript && sessionId) {
            const res = await sendChat(sessionId, transcript, true);
            playAnnouncement({
                text: res.text,
                stage: "near",
                priority: "high",
                language: res.lang || currentLang,
            });
        }
    } catch (err) {
        console.warn("Ask transcription or chat failed:", err);
    } finally {
        askText.textContent = "ASK";
    }
}

// 3. MUTE
$("btn-mute").addEventListener("click", () => {
    isMuted = !isMuted;
    if (isMuted) {
        stopAudio();
        $("btn-mute").classList.add("muted");
        $("mute-icon").textContent = "🔇";
        $("mute-text").textContent = "MUTED";
    } else {
        $("btn-mute").classList.remove("muted");
        $("mute-icon").textContent = "🔊";
        $("mute-text").textContent = "VOICE";
    }
});

// Setup listeners
setupSearch("from");
setupSearch("to");

// One-tap destination voice input for drivers
let isMicSearching = false;
let toMicTimeout = null;

$("to-mic")?.addEventListener("click", async () => {
    const micBtn = $("to-mic");
    const toInput = $("to-input");
    const chosen = $("to-chosen");

    if (isMicSearching) {
        clearTimeout(toMicTimeout);
        isMicSearching = false;
        micBtn.classList.remove("listening");
        chosen.textContent = "Processing speech...";
        try {
            const rawBlob = await stopRecording();
            const wav = await toWav16k(rawBlob);
            const lang = $("driver-lang")?.value || "en";
            const ttsLang = ttsCode(lang);
            const { transcript } = await transcribe(wav, ttsLang);
            if (transcript) {
                toInput.value = transcript;
                chosen.textContent = `Heard: "${transcript}"`;
                $("to-search").click();
            } else {
                chosen.textContent = "Could not hear destination. Try again.";
            }
        } catch (e) {
            chosen.textContent = "Voice input error.";
        }
        return;
    }

    try {
        await startRecording();
        isMicSearching = true;
        micBtn.classList.add("listening");
        chosen.textContent = "Listening for destination...";
        toMicTimeout = setTimeout(() => {
            if (isMicSearching) $("to-mic").click();
        }, 6000);
    } catch (e) {
        chosen.textContent = "Could not access microphone.";
    }
});
$("driver-lang")?.addEventListener("change", () => {
    if (startState.to) checkReadyForPreview();
});
$("btn-start-drive")?.addEventListener("click", () => startDriving(false));
$("btn-sim-drive")?.addEventListener("click", () => startDriving(true));

$("btn-hud-exit")?.addEventListener("click", () => {
    stopAllTracking();
    updateSpeedLockout(0);
    $("driving-screen").style.display = "none";
    $("setup-screen").style.display = "flex";
});

// Bangalore preset corridors
const PRESET_COORDS = {
    "Central Silk Board": { lat: 12.9176, lon: 77.6238, name: "Central Silk Board" },
    "Indiranagar Metro Station": { lat: 12.9784, lon: 77.6408, name: "Indiranagar Metro Station" },
    "Mahatma Gandhi Road": { lat: 12.9756, lon: 77.6068, name: "Mahatma Gandhi Road" },
    "Cubbon Park": { lat: 12.9763, lon: 77.5929, name: "Cubbon Park" },
    "Malleshwaram": { lat: 13.0031, lon: 77.5643, name: "Malleshwaram" },
    "Sankey Tank": { lat: 13.0076, lon: 77.5744, name: "Sankey Tank" },
};

document.querySelectorAll(".preset-chip").forEach((btn) => {
    btn.addEventListener("click", () => {
        const fromName = btn.dataset.from;
        const toName = btn.dataset.to;
        if (PRESET_COORDS[fromName]) {
            startState.from = { ...PRESET_COORDS[fromName] };
            $("from-input").value = fromName;
            $("from-chosen").textContent = `Selected: ${fromName}`;
        }
        if (PRESET_COORDS[toName]) {
            startState.to = { ...PRESET_COORDS[toName] };
            $("to-input").value = toName;
            $("to-chosen").textContent = `Selected: ${toName}`;
        }
        checkReadyForPreview();
    });
});

