const CACHE_NAME = "gigamas-v5";

const urlsToCache = [
    "/",
    "/dashboard",
    "/login",
    "/laporan",
    "/barang",
    "/barang_masuk",
    "/barang_keluar",
    "/supplier",
    "/cabang",
    "/users",
    "/whatsapp/log",
    "/offline",
    "/static/manifest.json",
    "/static/img/logo_gigamas.png",
    "/static/img/icon-192.png",
    "/static/img/icon-512.png"
];

self.addEventListener("install", event => {
    event.waitUntil(
        caches.open(CACHE_NAME)
            .then(cache => cache.addAll(urlsToCache))
    );

    self.skipWaiting();
});

self.addEventListener("activate", event => {
    event.waitUntil(
        caches.keys().then(cacheNames => {
            return Promise.all(
                cacheNames.map(cache => {
                    if (cache !== CACHE_NAME) {
                        return caches.delete(cache);
                    }
                })
            );
        })
    );

    self.clients.claim();
});

self.addEventListener("fetch", event => {
    if (event.request.method !== "GET") {
        return;
    }

    if (event.request.mode === "navigate") {
        event.respondWith(
            fetch(event.request)
                .then(response => {
                    const responseClone = response.clone();

                    caches.open(CACHE_NAME).then(cache => {
                        cache.put(event.request, responseClone);
                    });

                    return response;
                })
                .catch(() => {
                    return caches.match(event.request)
                        .then(response => {
                            return response || caches.match("/offline");
                        });
                })
        );

        return;
    }

    event.respondWith(
        caches.match(event.request)
            .then(cachedResponse => {
                return cachedResponse || fetch(event.request)
                    .then(response => {
                        const responseClone = response.clone();

                        caches.open(CACHE_NAME).then(cache => {
                            cache.put(event.request, responseClone);
                        });

                        return response;
                    })
                    .catch(() => {
                        return caches.match("/offline");
                    });
            })
    );
});