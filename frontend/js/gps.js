/**
 * Live GPS tracking with accuracy filtering and debounced position updates.
 */

export function startGpsTracking({
    sessionId,
    api,
    onTick,
    onReroute,
    onEnd,
    onError,
    minIntervalMs = 2000,
    maxAccuracyM = 40,
}) {
    if (!navigator.geolocation) {
        onError("Geolocation is not supported by your browser.");
        return { stop: () => {} };
    }

    let watchId = null;
    let lastSent = 0;
    let busy = false;
    let rerouting = false;
    let stopped = false;

    function stop() {
        stopped = true;
        if (watchId !== null) {
            navigator.geolocation.clearWatch(watchId);
            watchId = null;
        }
    }

    async function handlePosition(pos) {
        if (stopped || busy || rerouting) return;

        const now = Date.now();
        if (now - lastSent < minIntervalMs) return;

        const lat = pos.coords.latitude;
        const lon = pos.coords.longitude;
        const accuracy = pos.coords.accuracy || 10;
        const ts = pos.timestamp ? pos.timestamp / 1000 : now / 1000;

        busy = true;
        lastSent = now;

        try {
            const status = await api.position(sessionId, lat, lon, accuracy, ts);
            if (stopped) return;

            onTick({ lat, lon, status, accuracy });

            if (status.needs_reroute) {
                rerouting = true;
                try {
                    const res = await api.reroute(sessionId, lat, lon, accuracy, ts);
                    if (stopped) return;
                    onReroute(res);
                } finally {
                    rerouting = false;
                }
                return;
            }

            if (status.arrived) {
                stop();
                onEnd();
            }
        } catch (e) {
            if (!stopped) {
                onError(e.message || "Failed to update GPS position");
            }
        } finally {
            busy = false;
        }
    }

    function handleError(err) {
        if (stopped) return;
        let msg = "GPS error";
        switch (err.code) {
            case 1:
                msg = "Location permission denied. Please allow GPS access.";
                stop();
                break;
            case 2:
                msg = "GPS position unavailable. Check your location settings.";
                break;
            case 3:
                msg = "GPS request timed out.";
                break;
            default:
                msg = err.message || "Unknown GPS error";
        }
        onError(msg);
    }

    const options = {
        enableHighAccuracy: true,
        timeout: 10000,
        maximumAge: 1000,
    };

    watchId = navigator.geolocation.watchPosition(handlePosition, handleError, options);

    return { stop };
}

