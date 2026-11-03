const R = 6371000;
const rad = Math.PI / 180;

function dist(a, b) {
    const x = (b[1] - a[1]) * rad * R * Math.cos(a[0] * rad);
    const y = (b[0] - a[0]) * rad * R;
    return Math.hypot(x, y);
}

export function resample(geometry, stepM) {
    const out = [geometry[0]];
    let carry = 0;
    for (let i = 1; i < geometry.length; i++) {
        const a = geometry[i - 1];
        const b = geometry[i];
        const seg = dist(a, b);
        if (seg === 0) continue;
        let d = stepM - carry;
        while (d <= seg) {
            const t = d / seg;
            out.push([a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t]);
            d += stepM;
        }
        carry = seg - (d - stepM);
    }
    out.push(geometry[geometry.length - 1]);
    return out;
}

export function startSimulation({
    geometry, sessionId, wrongTurn, api,
    onTick, onReroute, onEnd, onError,
    stepM = 30, tickMs = 1000,
}) {
    let path = resample(geometry, stepM);
    let i = 0;
    let wrong = wrongTurn;
    let deviating = false;
    let drift = 0;
    let busy = false;
    let stopped = false;
    const deviateAt = Math.floor(path.length * 0.4);

    const timer = setInterval(tick, tickMs);
    function stop() {
        stopped = true;
        clearInterval(timer);
    }

    async function tick() {
        if (stopped || busy) return;
        busy = true;
        try {
            let [lat, lon] = path[Math.min(i, path.length - 1)];
            if (wrong && i >= deviateAt) deviating = true;
            if (deviating) {
                drift = Math.min(drift + 15, 90); // drifts north, up to 90 m off the road
                lat += drift / 111320;
            }
            const status = await api.position(sessionId, lat, lon, 8, Date.now() / 1000);
            if (stopped) return;
            onTick({ lat, lon, status });

            if (status.needs_reroute) {
                const res = await api.reroute(sessionId, lat, lon, 8, Date.now() / 1000);
                if (stopped) return;
                path = resample(res.route.geometry, stepM);
                i = 0;
                wrong = false;
                deviating = false;
                drift = 0;
                onReroute(res);
                return;
            }
            if (status.arrived || i >= path.length - 1) {
                stop();
                onEnd();
                return;
            }
            i++;
        } catch (e) {
            stop();
            onError(e.message || "Simulation failed");
        } finally {
            busy = false;
        }
    }

    return { stop };
}