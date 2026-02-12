const CACHE_NAME = "mech-quoter-v1";
const ASSETS = [
  "/",
  "/static/style.css?v=3",
  "/static/app.js?v=3",
  "/manifest.webmanifest",
  "/static/icon-192.png"
];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.addAll(ASSETS)));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.map((k) => (k !== CACHE_NAME ? caches.delete(k) : null)))
    )
  );
  self.clients.claim();
});

// Network-first for API; cache-first for static
self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);

  // API calls (always try network first)
  if (url.pathname.startsWith("/vehicle/") || url.pathname.startsWith("/catalog") || url.pathname.startsWith("/categories")) {
    event.respondWith(
      fetch(event.request).catch(() => caches.match(event.request))
    );
    return;
  }

  // Static assets (cache-first)
  event.respondWith(
    caches.match(event.request).then((cached) => cached || fetch(event.request))
  );
});
