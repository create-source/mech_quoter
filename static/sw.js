const CACHE = "mech-quoter-v1";
const ASSETS = [
  "/",
  "/static/style.css",
  "/static/app.js",
  "/static/manifest.webmanifest",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) => cache.addAll(ASSETS)).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener("fetch", (event) => {
  const req = event.request;

  // Network-first for API calls
  if (req.url.includes("/vehicle/") || req.url.includes("/catalog") || req.url.includes("/estimate/pdf")) {
    event.respondWith(
      fetch(req).catch(() => caches.match(req))
    );
    return;
  }

  // Cache-first for static
  event.respondWith(
    caches.match(req).then((cached) => cached || fetch(req))
  );
});
