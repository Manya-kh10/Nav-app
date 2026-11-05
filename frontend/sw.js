// Bangalore Voice Nav Service Worker
const CACHE_NAME = "bvn-cache-v1";
const STATIC_ASSETS = [
  "/",
  "/index.html",
  "/driver.html",
  "/css/app.css",
  "/css/driver.css",
  "/js/app.js",
  "/js/driver.js",
  "/js/voice.js",
  "/js/api.js",
  "/js/gps.js",
  "/js/map.js",
  "/js/sim.js",
  "/icons/icon.svg",
  "/manifest.webmanifest",
];

self.addEventListener("install", (e) => {
  self.skipWaiting();
  e.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(STATIC_ASSETS)).catch(() => {})
  );
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    )
  );
});

self.addEventListener("fetch", (e) => {
  // Always go network-first for API requests
  if (e.request.url.includes("/api/")) {
    return;
  }
  e.respondWith(
    fetch(e.request).catch(() => caches.match(e.request))
  );
});

