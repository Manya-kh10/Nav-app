import { searchPlaces, getGuide, sendPosition, sendReroute, sendChat } from "./api.js";
import { initMap, drawRoute, moveUser, clearUser } from "./map.js";
import { startSimulation } from "./sim.js";
import { startGpsTracking } from "./gps.js";
import { speak, stopAudio, playChime } from "./voice.js";

const state = { from: null, to: null, guide: null, sim: null, gps: null };
const $ = (id) => document.getElementById(id);
const status = (msg) => { $("status").textContent = msg || ""; };

let currentTrackingSessionId = null;
let lastAnnouncementId = 0;
const ttsCode = (l) => ({ en: "en-IN", hi: "hi-IN", hinglish: "hi-IN", kn: "kn-IN" }[l] || "en-IN");

function resetAnnouncements() {
    lastAnnouncementId = 0;
    stopAudio();
}

function handleAnnouncement(s) {
    if (s.session_id && s.session_id !== currentTrackingSessionId) {
        currentTrackingSessionId = s.session_id;
        lastAnnouncementId = 0;
    }
    const { navLang } = getSelectedLang();
    const stepText = formatStepCountdown(s, navLang);
    if (stepText && $("nav-next")) {
        $("nav-next").textContent = stepText;
    }
    const a = s.announcement;
    if (!a || a.id <= lastAnnouncementId) return;
    lastAnnouncementId = a.id;
    if (a.chime) {
        navLog("🔔 Turn chime");
        playChime();
    }
    if (a.speak && a.text) {
        navLog(`🔊 ${a.text}`);
        speak(a.text, ttsCode(a.lang || a.language)).catch(() => {});
    }
}

function shortName(p) {
    return p.display_name.split(",").slice(0, 3).join(",");
}

function setupPicker(key) {
    const input = $(`${key}-input`);
    const list = $(`${key}-results`);
    const chosen = $(`${key}-chosen`);

    input.addEventListener("input", () => status(""));
    input.addEventListener("focus", () => {
        if ($("status").textContent.includes("Route expired")) {
            status("");
        }
    });

    async function doSearch() {
        const q = input.value.trim();
        if (q.length < 2) return;
        status("");
        list.textContent = "Searching...";
        try {
            const places = await searchPlaces(q);
            list.textContent = "";
            if (!places.length) {
                list.textContent = "No places found. Try a different spelling.";
                return;
            }
            for (const p of places) {
                const b = document.createElement("button");
                b.textContent = p.name;
                const small = document.createElement("small");
                small.textContent = p.score
                    ? `${shortName(p)} · ${Math.round(p.score)}% match`
                    : shortName(p);
                b.appendChild(small);
                b.addEventListener("click", () => {
                    state[key] = { lat: p.lat, lon: p.lon, name: p.name, name_kn: p.name_kn };
                    chosen.textContent = `Selected: ${p.name}`;
                    list.textContent = "";
                    status(""); // Clear any stale route expired warning
                });
                list.appendChild(b);
            }
        } catch (e) {
            list.textContent = "";
            status(e.message);
        }
    }

    $(`${key}-search`).addEventListener("click", doSearch);
    input.addEventListener("keydown", (e) => { if (e.key === "Enter") doSearch(); });
}

function distText(m) {
    if (m >= 1000) {
        const km = (m / 1000).toFixed(1).replace(/\.0$/, "");
        return `${km} km`;
    }
    return `${Math.round(m)} m`;
}

function formatStepCountdown(s, navLang) {
    if (s.arrived) {
        if (navLang === "kn") return "ನೀವು ತಲುಪಿದ್ದೀರಿ.";
        if (navLang === "hi") return "आप अपनी मंज़िल पर पहुँच गए हैं।";
        if (navLang === "hinglish") return "Aap apni manzil par pahunch gaye hain.";
        return "You have arrived at your destination.";
    }
    if (!s.on_route) {
        if (navLang === "kn") return "ದಾರಿಯಿಂದ ಹೊರಗಿದ್ದೀರಿ. ಹೊಸ ದಾರಿ ಹುಡುಕುತ್ತಿದ್ದೇವೆ...";
        if (navLang === "hi") return "आप रास्ते से हट गए हैं। नया रास्ता ढूँढ रहे हैं...";
        if (navLang === "hinglish") return "Aap route se hat gaye hain. Naya rasta dhoond rahe hain...";
        return "You are off the route. Finding a new one...";
    }
    if (s.guidance && s.guidance.text) {
        return s.guidance.text;
    }
    if (s.next_text) {
        return s.next_text;
    }
    return "";
}

function formatDestinationMeta(s, navLang, accuracy = null) {
    const remM = s.remaining_m;
    const remMin = Math.max(1, Math.round(s.remaining_s / 60));
    const dist = distText(remM);
    let offRoute = "";
    if (!s.on_route) {
        offRoute = `, ${Math.round(s.distance_from_route_m)} m off route`;
    }
    let gpsAcc = "";
    if (accuracy !== null && accuracy !== undefined) {
        gpsAcc = ` (GPS ±${Math.round(accuracy)}m)`;
    }

    if (navLang === "hi") {
        return `🏁 मंज़िल: ${dist} बाकी · लगभग ${remMin} मिनट${offRoute}${gpsAcc}`;
    }
    if (navLang === "hinglish") {
        return `🏁 Manzil: ${dist} bacha hai · lagbhag ${remMin} min${offRoute}${gpsAcc}`;
    }
    if (navLang === "kn") {
        return `🏁 ಗಮ್ಯಸ್ಥಾನ: ${dist} ಬಾಕಿ · ಸುಮಾರು ${remMin} ನಿಮಿಷ${offRoute}${gpsAcc}`;
    }
    return `🏁 Destination: ${dist} remaining · ~${remMin} min${offRoute}${gpsAcc}`;
}

function renderGuide(guide) {
    const scrollY = window.scrollY;
    const route = guide.route;
    const mins = Math.max(1, Math.round(route.duration_s / 60));
    $("summary").textContent = `${distText(route.distance_m)}, about ${mins} min `;
    const note = document.createElement("span");
    note.className = "note";
    note.textContent = `(${route.eta_note})`;
    $("summary").appendChild(note);
    const trafficAttr = $("traffic-attr");
    if (trafficAttr) {
        trafficAttr.style.display = (guide.traffic_status === "available" || route.traffic) ? "block" : "none";
    }

    // Immediately show upcoming turn and destination meta in the card!
    const { navLang } = getSelectedLang();
    const firstStepText = guide.instructions[0]?.text || (route.steps[0] ? `Continue for ${distText(route.steps[0].distance_m)}` : "Route ready");
    $("nav-next").textContent = firstStepText;
    if (navLang === "hi") {
        $("nav-meta").textContent = `🏁 मंज़िल: ${distText(route.distance_m)} बाकी · लगभग ${mins} मिनट`;
    } else if (navLang === "hinglish") {
        $("nav-meta").textContent = `🏁 Manzil: ${distText(route.distance_m)} bacha hai · lagbhag ${mins} min`;
    } else if (navLang === "kn") {
        $("nav-meta").textContent = `🏁 ಗಮ್ಯಸ್ಥಾನ: ${distText(route.distance_m)} ಬಾಕಿ · ಸುಮಾರು ${mins} ನಿಮಿಷ`;
    } else {
        $("nav-meta").textContent = `🏁 Destination: ${distText(route.distance_m)} remaining · ~${mins} min`;
    }

    $("steps").textContent = "";
    guide.instructions.forEach((ins, idx) => {
        const li = document.createElement("li");
        li.id = `step-item-${idx}`;
        li.textContent = ins.text;
        $("steps").appendChild(li);
    });
    window.scrollTo(0, scrollY);
}

function setSimButtons(running) {
    const has = !!state.guide;
    $("sim-walk").disabled = !has || running;
    $("sim-wrong").disabled = !has || running;
    $("gps-live").disabled = !has || running;
    $("sim-stop").disabled = !running;
}

function navLog(msg) {
    const li = document.createElement("li");
    li.textContent = `${new Date().toLocaleTimeString()}  ${msg}`;
    $("nav-log").prepend(li);
}

function stopTracking() {
    resetAnnouncements();
    if (state.sim) {
        state.sim.stop();
        state.sim = null;
    }
    if (state.gps) {
        state.gps.stop();
        state.gps = null;
    }
    setSimButtons(false);
}

function getSelectedLang() {
    const sel = $("voice-lang")?.value || "kn-IN";
    if (sel === "kn-IN") return { navLang: "kn", ttsLang: "kn-IN" };
    if (sel === "hi-IN") return { navLang: "hi", ttsLang: "hi-IN" };
    if (sel === "hinglish") return { navLang: "hinglish", ttsLang: "hi-IN" };
    return { navLang: "en", ttsLang: "en-IN" };
}

window.addEventListener("lang-changed", async () => {
    const { navLang } = getSelectedLang();
    // Re-fetching creates a new route session; while sim/GPS is posting to the current
    // session, swapping it would make chat answer from stale full-route totals.
    if (state.sim || state.gps) return;
    if (state.guide && state.from && state.to) {
        try {
            const guide = await getGuide(
                { lat: state.from.lat, lon: state.from.lon },
                { lat: state.to.lat, lon: state.to.lon },
                $("mode").value,
                navLang,
            );
            state.guide = guide;
            renderGuide(guide);
            $("nav-next").textContent = guide.instructions[0]?.text || "";
        } catch { /* keep existing guide */ }
    }
});

function runSim(wrong) {
    if (!state.guide) return;
    stopTracking();
    resetAnnouncements();
    currentTrackingSessionId = state.guide.session_id;
    clearUser();
    $("nav-log").textContent = "";
    navLog(wrong ? "Started: walking with a wrong turn" : "Started: walking the route");

    const mode = $("mode")?.value || "walk";
    const simStepM = mode === "walk" ? 8 : 20;

    state.sim = startSimulation({
        geometry: state.guide.route.geometry,
        sessionId: state.guide.session_id,
        wrongTurn: wrong,
        mode: mode,
        stepM: simStepM,
        tickMs: 1000,
        api: {
            position: (sid, lat, lon, acc, ts) => {
                const { navLang } = getSelectedLang();
                return sendPosition(sid, lat, lon, acc, ts, 1.4, navLang);
            },
            reroute: sendReroute,
        },
        onTick: ({ lat, lon, status: s }) => {
            moveUser(lat, lon);
            const { navLang } = getSelectedLang();
            const stepText = formatStepCountdown(s, navLang);
            if (stepText) $("nav-next").textContent = stepText;
            $("nav-meta").textContent = formatDestinationMeta(s, navLang);

            if (s.next_index !== null && s.next_index !== undefined) {
                const prev = $("steps").querySelector(".active-step");
                if (prev) prev.classList.remove("active-step");
                const cur = $(`step-item-${s.next_index}`);
                if (cur) {
                    cur.classList.add("active-step");
                }
            }

            handleAnnouncement(s);
        },
        onReroute: (res) => {
            resetAnnouncements();
            currentTrackingSessionId = res.session_id;
            state.guide = res;
            renderGuide(res);
            const here = res.route.geometry[0];
            drawRoute(res.route, { lat: here[0], lon: here[1] }, state.to, false);
            navLog(res.message);
            const { ttsLang } = getSelectedLang();
            $("nav-next").textContent = res.instructions[0]?.text || res.message;
            window.dispatchEvent(new CustomEvent("speak-text", {
                detail: { text: res.message, lang: ttsLang }
            }));
        },
        onEnd: () => {
            navLog("Arrived.");
            const { navLang } = getSelectedLang();
            $("nav-next").textContent = navLang === "kn"
                ? "ನೀವು ತಲುಪಿದ್ದೀರಿ."
                : (navLang === "hi"
                    ? "आप अपनी मंज़िल पर पहुँच गए हैं।"
                    : (navLang === "hinglish" ? "Aap apni manzil par pahunch gaye hain." : "You have arrived at your destination."));
            $("nav-meta").textContent = navLang === "hi"
                ? "🏁 मंज़िल पर पहुँच गए हैं"
                : (navLang === "kn"
                    ? "🏁 ಗಮ್ಯಸ್ಥಾನ ತಲುಪಿದ್ದೀರಿ"
                    : (navLang === "hinglish" ? "🏁 Manzil par pahunch gaye" : "🏁 Arrived at destination"));
            state.sim = null;
            setSimButtons(false);
        },
        onError: (msg) => {
            navLog(`Error: ${msg}`);
            status(msg);
            state.sim = null;
            setSimButtons(false);
        },
    });
    setSimButtons(true);
}

function runLiveGps() {
    if (!state.guide) return;
    stopTracking();
    resetAnnouncements();
    currentTrackingSessionId = state.guide.session_id;
    clearUser();
    $("nav-log").textContent = "";
    navLog("Started: Live GPS tracking");

    state.gps = startGpsTracking({
        sessionId: state.guide.session_id,
        api: {
            position: (sid, lat, lon, acc, ts) => {
                const { navLang } = getSelectedLang();
                return sendPosition(sid, lat, lon, acc, ts, 1.4, navLang);
            },
            reroute: sendReroute,
        },
        onTick: ({ lat, lon, status: s, accuracy }) => {
            moveUser(lat, lon);
            const { navLang } = getSelectedLang();
            const stepText = formatStepCountdown(s, navLang);
            if (stepText) $("nav-next").textContent = stepText;
            $("nav-meta").textContent = formatDestinationMeta(s, navLang, accuracy);

            if (s.next_index !== null && s.next_index !== undefined) {
                const prev = $("steps").querySelector(".active-step");
                if (prev) prev.classList.remove("active-step");
                const cur = $(`step-item-${s.next_index}`);
                if (cur) {
                    cur.classList.add("active-step");
                }
            }

            handleAnnouncement(s);
        },
        onReroute: (res) => {
            resetAnnouncements();
            currentTrackingSessionId = res.session_id;
            state.guide = res;
            renderGuide(res);
            const here = res.route.geometry[0];
            drawRoute(res.route, { lat: here[0], lon: here[1] }, state.to, false);
            navLog(`Rerouted: ${res.message}`);
            const { ttsLang } = getSelectedLang();
            $("nav-next").textContent = res.instructions[0]?.text || res.message;
            window.dispatchEvent(new CustomEvent("speak-text", {
                detail: { text: res.message, lang: ttsLang }
            }));
        },
        onEnd: () => {
            navLog("Arrived.");
            const { navLang } = getSelectedLang();
            $("nav-next").textContent = navLang === "kn"
                ? "ನೀವು ತಲುಪಿದ್ದೀರಿ."
                : (navLang === "hi"
                    ? "आप अपनी मंज़िल पर पहुँच गए हैं।"
                    : (navLang === "hinglish" ? "Aap apni manzil par pahunch gaye hain." : "You have arrived at your destination."));
            $("nav-meta").textContent = navLang === "hi"
                ? "🏁 मंज़िल पर पहुँच गए हैं"
                : (navLang === "kn"
                    ? "🏁 ಗಮ್ಯಸ್ಥಾನ ತಲುಪಿದ್ದೀರಿ"
                    : (navLang === "hinglish" ? "🏁 Manzil par pahunch gaye" : "🏁 Arrived at destination"));
            state.gps = null;
            setSimButtons(false);
        },
        onError: (msg) => {
            navLog(`GPS Error: ${msg}`);
            status(msg);
            state.gps = null;
            setSimButtons(false);
        },
    });
    setSimButtons(true);
}

function openPassengerCard() {
    if (!state.to) return;
    const knName = state.to.name_kn || state.to.name;
    $("card-kn").textContent = knName;
    $("card-en").textContent = state.to.name;

    let lmText = "";
    if (state.guide && state.guide.instructions) {
        for (const ins of state.guide.instructions) {
            if (ins.landmark) {
                lmText = `${ins.landmark} ಹತ್ತಿರ (Near ${ins.landmark})`;
            }
        }
    }
    const lmEl = $("card-landmark");
    if (lmText) {
        lmEl.textContent = lmText;
        lmEl.style.display = "inline-block";
    } else {
        lmEl.style.display = "none";
    }

    $("passenger-modal").classList.remove("hidden");
}

function closePassengerCard() {
    $("passenger-modal").classList.add("hidden");
}

function speakToDriver() {
    if (!state.to) return;
    const knName = state.to.name_kn || state.to.name;
    // Suffix-free on purpose: appending case markers (e.g. "ಗೆ") to arbitrary names is often ungrammatical.
    const phrase = `ನಮಸ್ಕಾರ, ದಯವಿಟ್ಟು ಇಲ್ಲಿಗೆ ಕರೆದುಕೊಂಡು ಹೋಗಿ: ${knName}.`;
    window.dispatchEvent(new CustomEvent("speak-text", {
        detail: { text: phrase, lang: "kn-IN" }
    }));
}

async function onGo() {
    if (!state.from || !state.to) {
        status("Pick both a start and a destination first.");
        return;
    }
    stopTracking();
    clearUser();
    state.guide = null;
    setSimButtons(false);
    $("passenger-card-btn").style.display = "none";
    status("Getting route...");
    $("steps").textContent = "";
    $("summary").textContent = "";
    $("nav-log").textContent = "";
    try {
        const { navLang } = getSelectedLang();
        const guide = await getGuide(
            { lat: state.from.lat, lon: state.from.lon },
            { lat: state.to.lat, lon: state.to.lon },
            $("mode").value,
            navLang,
        );
        resetAnnouncements();
        currentTrackingSessionId = guide.session_id;
        state.guide = guide;
        drawRoute(guide.route, state.from, state.to);
        renderGuide(guide);
        $("passenger-card-btn").style.display = "inline-block";
        setSimButtons(false);
        status(guide.landmarks_status === "unavailable"
            ? "Landmark data unavailable right now; showing plain directions."
            : "");
        // On mobile only, collapse search drawer so the map and route are visible
        if (window.innerWidth < 768) {
            $("app-sidebar")?.classList.add("collapsed");
        }
    } catch (e) {
        status(e.message);
    }
}

initMap();
setupPicker("from");
setupPicker("to");
$("go").addEventListener("click", onGo);
$("sim-walk").addEventListener("click", () => runSim(false));
$("sim-wrong").addEventListener("click", () => runSim(true));
$("gps-live").addEventListener("click", runLiveGps);
$("sim-stop").addEventListener("click", stopTracking);
$("passenger-card-btn").addEventListener("click", openPassengerCard);
$("modal-close").addEventListener("click", closePassengerCard);
$("passenger-modal").addEventListener("click", (e) => {
    if (e.target.id === "passenger-modal") closePassengerCard();
});
$("card-speak-btn").addEventListener("click", speakToDriver);

// Mobile drawer & bottom-sheet toggles
$("toggle-search-btn")?.addEventListener("click", () => {
    $("app-sidebar")?.classList.toggle("collapsed");
});
$("sheet-handle")?.addEventListener("click", () => {
    $("mobile-bottom-sheet")?.classList.toggle("expanded");
});

window.addEventListener("resize", () => {
    if (window.innerWidth >= 768) {
        $("app-sidebar")?.classList.remove("collapsed");
    }
});

// PWA Service Worker Registration
if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/sw.js").catch(() => {});
}

async function onAsk() {
    const input = $("chat-input");
    const msg = input.value.trim();
    if (!msg) return;
    if (!state.guide) {
        $("chat-answer").textContent = "Get a route first.";
        return;
    }
    $("chat-answer").textContent = "...";
    try {
        const { navLang } = getSelectedLang();
        const res = await sendChat(state.guide.session_id, msg, false, navLang);
        $("chat-answer").textContent = res.text;
        navLog(`Q: ${msg} -> ${res.text}`);
        window.dispatchEvent(new CustomEvent("nav-answer", { detail: res }));
        if (res.intent === "start_navigation" && !state.sim) {
            setTimeout(() => { runSim(false); }, 800);
        }
        input.value = "";
    } catch (e) {
        if (e.message && e.message.includes("Route expired")) {
            $("chat-answer").textContent = "Route session has expired. Please click 'Get Route' to refresh the route.";
            status("Route expired. Please click 'Get Route' to refresh the route.");
        } else {
            $("chat-answer").textContent = e.message;
        }
    }
}
$("chat-send").addEventListener("click", onAsk);
$("chat-input").addEventListener("keydown", (e) => { if (e.key === "Enter") onAsk(); });
