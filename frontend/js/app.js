import { searchPlaces, getGuide, sendPosition, sendReroute, sendChat } from "./api.js";
import { initMap, drawRoute, moveUser, clearUser } from "./map.js";
import { startSimulation } from "./sim.js";

const state = { from: null, to: null, guide: null, sim: null };
const $ = (id) => document.getElementById(id);
const status = (msg) => { $("status").textContent = msg || ""; };

function shortName(p) {
    return p.display_name.split(",").slice(0, 3).join(",");
}

function setupPicker(key) {
    const input = $(`${key}-input`);
    const list = $(`${key}-results`);
    const chosen = $(`${key}-chosen`);

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
                    state[key] = { lat: p.lat, lon: p.lon, name: p.name };
                    chosen.textContent = `Selected: ${p.name}`;
                    list.textContent = "";
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

function renderGuide(guide) {
    const route = guide.route;
    const mins = Math.round(route.duration_s / 60);
    $("summary").textContent = `${distText(route.distance_m)}, about ${mins} min `;
    const note = document.createElement("span");
    note.className = "note";
    note.textContent = `(${route.eta_note})`;
    $("summary").appendChild(note);
    $("steps").textContent = "";
    for (const ins of guide.instructions) {
        const li = document.createElement("li");
        li.textContent = ins.text;
        $("steps").appendChild(li);
    }
}

function setSimButtons(running) {
    const has = !!state.guide;
    $("sim-walk").disabled = !has || running;
    $("sim-wrong").disabled = !has || running;
    $("sim-stop").disabled = !running;
}

function navLog(msg) {
    const li = document.createElement("li");
    li.textContent = `${new Date().toLocaleTimeString()}  ${msg}`;
    $("nav-log").prepend(li);
}

function stopSim() {
    if (state.sim) {
        state.sim.stop();
        state.sim = null;
    }
    setSimButtons(false);
}

function runSim(wrong) {
    if (!state.guide) return;
    stopSim();
    clearUser();
    $("nav-log").textContent = "";
    navLog(wrong ? "Started: walking with a wrong turn" : "Started: walking the route");

    state.sim = startSimulation({
        geometry: state.guide.route.geometry,
        sessionId: state.guide.session_id,
        wrongTurn: wrong,
        api: { position: sendPosition, reroute: sendReroute },
        onTick: ({ lat, lon, status: s }) => {
            moveUser(lat, lon);
            $("nav-next").textContent = s.on_route
                ? (s.next_text || "")
                : "You are off the route. Finding a new one...";
            $("nav-meta").textContent =
                `${distText(s.remaining_m)} left, about ${Math.round(s.remaining_s / 60)} min` +
                (s.on_route ? "" : `, ${Math.round(s.distance_from_route_m)} m off route`);
        },
        onReroute: (res) => {
            state.guide = res;
            renderGuide(res);
            const here = res.route.geometry[0];
            drawRoute(res.route, { lat: here[0], lon: here[1] }, state.to, false);
            navLog(res.message);
        },
        onEnd: () => {
            navLog("Arrived.");
            $("nav-next").textContent = "You have arrived.";
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

async function onGo() {
    if (!state.from || !state.to) {
        status("Pick both a start and a destination first.");
        return;
    }
    stopSim();
    clearUser();
    state.guide = null;
    setSimButtons(false);
    status("Getting route...");
    $("steps").textContent = "";
    $("summary").textContent = "";
    $("nav-log").textContent = "";
    try {
        const guide = await getGuide(
            { lat: state.from.lat, lon: state.from.lon },
            { lat: state.to.lat, lon: state.to.lon },
            $("mode").value,
        );
        state.guide = guide;
        drawRoute(guide.route, state.from, state.to);
        renderGuide(guide);
        $("nav-next").textContent = guide.instructions[0]?.text || "";
        $("nav-meta").textContent = "";
        setSimButtons(false);
        status(guide.landmarks_status === "unavailable"
            ? "Landmark data unavailable right now; showing plain directions."
            : "");
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
$("sim-stop").addEventListener("click", stopSim);

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
        const res = await sendChat(state.guide.session_id, msg);
        $("chat-answer").textContent = res.text;
        navLog(`Q: ${msg} -> ${res.text}`);
        window.dispatchEvent(new CustomEvent("nav-answer", { detail: res }));
        input.value = "";
    } catch (e) {
        $("chat-answer").textContent = e.message;
    }
}
$("chat-send").addEventListener("click", onAsk);
$("chat-input").addEventListener("keydown", (e) => { if (e.key === "Enter") onAsk(); });