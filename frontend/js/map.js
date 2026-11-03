let map;
let routeLine;
let markers = [];
let userDot;

export function initMap() {
    map = L.map("map").setView([12.9716, 77.5946], 12);
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
        maxZoom: 19,
        attribution: "© OpenStreetMap contributors",
    }).addTo(map);
}

export function drawRoute(route, from, to, fit = true) {
    if (routeLine) routeLine.remove();
    markers.forEach((m) => m.remove());
    routeLine = L.polyline(route.geometry, { weight: 5 }).addTo(map);
    markers = [
        L.marker([from.lat, from.lon]).addTo(map),
        L.marker([to.lat, to.lon]).addTo(map),
    ];
    if (fit) map.fitBounds(routeLine.getBounds(), { padding: [30, 30] });
}

export function moveUser(lat, lon) {
    if (!userDot) {
        userDot = L.circleMarker([lat, lon], {
            radius: 8, color: "#d32f2f", fillColor: "#d32f2f", fillOpacity: 1,
        }).addTo(map);
    } else {
        userDot.setLatLng([lat, lon]);
    }
}

export function clearUser() {
    if (userDot) {
        userDot.remove();
        userDot = null;
    }
}