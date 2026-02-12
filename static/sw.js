/* static/sw.js */

const VERSION = "mech-quoter-v1";
const STATIC_CACHE = `static-${VERSION}`;
const RUNTIME_CACHE = `runtime-${VERSION}`;

const APP_SHELL = [
  "/",                     // home (index.html served by FastAPI)
  "/static/style.css?v=1",
  "/static/app.js?v=1",
  "/manifest.webmanifest",
  "/static/icon-192.png",
  "/static/icon-512.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(STATIC_CACHE).then((cache) => cache.addAll(APP_SHELL))
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys.map((key) => {
          if (key !== STATIC_CACHE && key !== RUNTIME_CACHE) {
            return caches.delete(key);
          }
        })
      )
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  const url = new URL(req.url);

  // Only handle same-origin
  if (url.origin !== self.location.origin) return;

  // Navigation requests (typing URL / refresh) -> fallback to cached "/" offline
  if (req.mode === "navigate") {
    event.respondWith(
      fetch(req)
        .then((res) => {
          const copy = res.clone();
          caches.open(RUNTIME_CACHE).then((c) => c.put("/", copy));
          return res;
        })
        .catch(async () => {
          const cached = await caches.match("/");
          return cached || new Response("Offline", { status: 503 });
        })
    );
    return;
  }

  // API + PDF -> network-first (fresh), fallback cache
  if (url.pathname.startsWith("/api/") || url.pathname.startsWith("/estimate")) {
    event.respondWith(networkFirst(req));
    return;
  }

  // Static assets -> cache-first
  if (url.pathname.startsWith("/static/") || url.pathname.endsWith(".webmanifest")) {
    event.respondWith(cacheFirst(req));
    return;
  }

  // Default -> try cache then network
  event.respondWith(cacheFirst(req));
});

async function cacheFirst(request) {
  const cached = await caches.match(request);
  if (cached) return cached;

  const res = await fetch(request);
  const cache = await caches.open(RUNTIME_CACHE);
  cache.put(request, res.clone());
  return res;
}

async function networkFirst(request) {
  const cache = await caches.open(RUNTIME_CACHE);
  try {
    const res = await fetch(request);
    cache.put(request, res.clone());
    return res;
  } catch (err) {
    const cached = await cache.match(request);
    return cached || new Response(
      JSON.stringify({ error: "Offline" }),
      { status: 503, headers: { "Content-Type": "application/json" } }
    );
  }
}
