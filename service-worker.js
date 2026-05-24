const CACHE_NAME = "gigamas-cache-v1";

const urlsToCache = [
  "/",
  "/dashboard",
  "/static/manifest.json",
  "/static/img/logo_gigamas.png"
];

self.addEventListener("install", function(event) {
  event.waitUntil(
    caches.open(CACHE_NAME).then(function(cache) {
      return cache.addAll(urlsToCache);
    })
  );
});

self.addEventListener("fetch", function(event) {
  event.respondWith(
    fetch(event.request).catch(function() {
      return caches.match(event.request);
    })
  );
});