// CarbonTrack service worker — caches the app shell (built JS/CSS + icons) so
// the app can still open when a driver has no signal, and falls back to the
// cached index.html for any navigation while offline. Deliberately does NOT
// cache /api/* responses: trip/fleet data must always be fresh when online,
// and stale cached data could be actively dangerous for something like live
// fleet positions. Offline API writes (location pings) are queued in the app
// itself, not here — see lib/offlineQueue.js.
//
// CACHE_NAME is bumped on every deploy that changes this file's caching
// behavior (see the version comment below). Bumping it is what makes the
// "activate" handler below actually delete old caches — a browser that
// visited an older build is otherwise stuck with whatever it cached forever,
// since a service worker update alone doesn't clear a same-named cache.
// version: 2 (fixed: navigation was cache-first with no invalidation path,
// so a rebuild's new JS/CSS filenames could never be reached by anyone whose
// browser had already cached the old index.html — that's the
// "Failed to load module script ... MIME type of text/html" bug.)
// version: 3 (fixed: the offline fallback below could resolve to `undefined`
// instead of a Response — on a fresh install, before /index.html or a given
// route had ever been successfully fetched once, a failed fetch had nothing
// to fall back to and respondWith(undefined) throws "Failed to convert
// value to 'Response'", which the browser reports as "The FetchEvent for
// '<url>' resulted in a network error response". Bumped so browsers stuck
// with the old, buggy worker are forced onto this fixed one.)
const CACHE_NAME = "carbontrack-shell-v3";
const APP_SHELL = ["/", "/index.html", "/manifest.json", "/icon-192.png", "/icon-512.png"];
const OFFLINE_FALLBACK = new Response(
  "<!doctype html><meta charset=utf-8><title>Offline</title>" +
  "<p style='font-family:system-ui;padding:2rem'>You're offline and this page hasn't been cached yet. Reconnect and try again.</p>",
  { status: 503, statusText: "Offline", headers: { "Content-Type": "text/html" } }
);

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(APP_SHELL)).catch(() => {})
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET") return;

  const url = new URL(request.url);
  if (url.pathname.startsWith("/api/")) return; // never cache API traffic

  // Built JS/CSS: cache-first is safe here because Vite content-hashes these
  // filenames (e.g. index-C0Jg4gyG.js) — a new build always gets a new name,
  // so there's no way to ever get stuck serving a stale one. Old, no-longer-
  // referenced entries just sit unused in the cache until the next
  // "activate" cache-name bump clears them.
  if (url.pathname.startsWith("/assets/")) {
    event.respondWith(
      caches.match(request).then((cached) => cached || fetch(request).then((res) => {
        const copy = res.clone();
        caches.open(CACHE_NAME).then((cache) => cache.put(request, copy)).catch(() => {});
        return res;
      }).catch(() => cached || new Response("", { status: 504, statusText: "Asset unavailable offline" })))
    );
    return;
  }

  // Navigation (/, /index.html, and every client-side route like
  // /driver/new-trip) and anything else (manifest, icons): ALWAYS try the
  // network first. This is the important part — index.html is what names
  // which hashed JS/CSS files to load, so it must never be served stale from
  // cache while online, or the browser ends up asking for assets from a
  // build that's no longer on the server. Only fall back to a cached copy
  // when the network request genuinely fails (offline), so the app can still
  // open with no signal.
  event.respondWith(
    fetch(request).then((res) => {
      const copy = res.clone();
      caches.open(CACHE_NAME).then((cache) => cache.put(request, copy)).catch(() => {});
      return res;
    }).catch(() =>
      caches.match(request)
        .then((cached) => cached || caches.match("/index.html"))
        .then((cached) => cached || OFFLINE_FALLBACK)
    )
  );
});
