/* static/sw.js */

const VERSION = "mech-quoter-v1"; // bump this on each deploy
const STATIC_CACHE = `static-${VERSION}`;
const RUNTIME_CACHE = `runtime-${VERSION}`;

// Precache "clean" URLs (no ?v=). Let VERSION control updates.
const APP_SHELL = [
  "/",                     // index.html (served by FastAPI)
  "/static/style.css",
  "/static/app.js",
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
  event.waitUntil((async () => {
    const keys = await caches.keys();
    await Promise.all(
      keys.map((key) => {
        if (key !== STATIC_CACHE && key !== RUNTIME_CACHE) {
          return caches.delete(key);
        }
      })
    );
    await self.clients.claim();
  })());
});

// Optional: allow the page to tell the SW to activate immediately
self.addEventListener("message", (event) => {
  if (event.data && event.data.type === "SKIP_WAITING") {
    self.skipWaiting();
  }
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  const url = new URL(req.url);

  // Same-origin only
  if (url.origin !== self.location.origin) return;

  // Navigations: network, then fallback to cached "/"
  if (req.mode === "navigate") {
    event.respondWith((async () => {
      try {
        const res = await fetch(req);
        // keep "/" fresh in runtime cache
        const cache = await caches.open(RUNTIME_CACHE);
        cache.put("/", res.clone());
        return res;
      } catch {
        return (await caches.match("/")) || new Response("Offline", { status: 503 });
      }
    })());
    return;
  }

  // API + PDF: network-first
  if (url.pathname.startsWith("/api/") || url.pathname.startsWith("/estimate")) {
    event.respondWith(networkFirst(req));
    return;
  }

  // Static assets: stale-while-revalidate (fast + updates)
  if (
    url.pathname.startsWith("/static/") ||
    url.pathname.endsWith(".webmanifest")
  ) {
    event.respondWith(staleWhileRevalidate(req));
    return;
  }

  // Default: cache-first
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
  } catch {
    const cached = await cache.match(request);
    return cached || new Response(
      JSON.stringify({ error: "Offline" }),
      { status: 503, headers: { "Content-Type": "application/json" } }
    );
  }
}

async function staleWhileRevalidate(request) {
  const cache = await caches.open(RUNTIME_CACHE);
  const cached = await cache.match(request);

  const fetchPromise = fetch(request)
    .then((res) => {
      cache.put(request, res.clone());
      return res;
    })
    .catch(() => null);

  // Return cached immediately if available, otherwise wait for network
  return cached || (await fetchPromise) || new Response("Offline", { status: 503 });
}
