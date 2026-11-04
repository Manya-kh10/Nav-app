async function request(url, options) {
    let res;
    try {
        res = await fetch(url, options);
    } catch {
        throw new Error("Cannot reach the server");
    }
    if (!res.ok) {
        let msg = `Request failed (${res.status})`;
        try {
            const body = await res.json();
            msg = body.detail?.message || body.detail?.code || msg;
        } catch { /* keep default message */ }
        throw new Error(msg);
    }
    return res.json();
}

export const searchPlaces = (q) =>
    request(`/api/v1/places/search?q=${encodeURIComponent(q)}&limit=5`);

export const getRoute = (start, end, mode) =>
    request("/api/v1/navigation/route", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ start, end, mode }),
    });

export const getGuide = (start, end, mode) =>
    request("/api/v1/navigation/guide", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ start, end, mode, landmarks: true }),
    });

const postJson = (url, body) =>
    request(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
    });

export const sendPosition = (session_id, lat, lon, accuracy_m, timestamp, speed_mps = null, lang = null) => {
    const payload = { session_id, lat, lon, accuracy_m, timestamp };
    if (speed_mps !== null && speed_mps !== undefined) payload.speed_mps = speed_mps;
    if (lang) payload.lang = lang;
    return postJson("/api/v1/navigation/position", payload);
};

export const sendReroute = (session_id, lat, lon, accuracy_m, timestamp) =>
    postJson("/api/v1/navigation/reroute", { session_id, lat, lon, accuracy_m, timestamp });

export const sendChat = (session_id, message, driver_mode = false) =>
    postJson("/api/v1/chat", { session_id, message, driver_mode });
