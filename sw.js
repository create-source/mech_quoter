const CACHE_VERSION = "auto-mechanic-v1";
const STATIC_CACHE = `static-${CACHE_VERSION}`;
const DYNAMIC_CACHE = `dynamic-${CACHE_VERSION}`;

// Files that make up your app shell
const APP_SHELL = [
  "/",
  "/static/index.html",
  "/static/app.js",
  "/static/styles.css",
  "/manifest.json",
  "/static/icons/icon-192.png",
  "/static/icons/icon-512.png"
];

// ===============================
// INSTALL
// ===============================
self.addEventListener("install", (event) => {
  console.log("Service Worker installing...");

  event.waitUntil(
    caches.open(STATIC_CACHE).then((cache) => {
      return cache.addAll(APP_SHELL);
    })
  );

  self.skipWaiting();
});

// ===============================
// ACTIVATE
// ===============================
self.addEventListener("activate", (event) => {
  console.log("Service Worker activating...");

  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys.map((key) => {
          if (key !== STATIC_CACHE && key !== DYNAMIC_CACHE) {
            return caches.delete(key);
          }
        })
      )
    )
  );

  self.clients.claim();
});

// ===============================
// FETCH
// ===============================
self.addEventListener("fetch", (event) => {
  const { request } = event;

  // 🔹 API Calls → Network First
  if (request.url.includes("/estimate") || request.url.includes("/api")) {
    event.respondWith(networkFirst(request));
    return;
  }

  // 🔹 Everything else → Cache First
  event.respondWith(cacheFirst(request));
});

// ===============================
// STRATEGIES
// ===============================

// Cache First Strategy
async function cacheFirst(request) {
  const cached = await caches.match(request);
  return cached || fetch(request);
}

// Network First Strategy
async function networkFirst(request) {
  const cache = await caches.open(DYNAMIC_CACHE);

  try {
    const response = await fetch(request);
    cache.put(request, response.clone());
    return response;
  } catch (error) {
    const cached = await cache.match(request);
    return cached || new Response(
      JSON.stringify({ error: "Offline" }),
      { headers: { "Content-Type": "application/json" } }
    );
  }
}
