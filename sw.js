const CACHE_NAME = 'sba-portal-v1';

// Install event: Cache essential files
self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME).then((cache) => {
            return cache.addAll([
                '/static/css/style.css', // Update with your actual CSS filename
                '/static/images/logo.jpg' // Update with your actual logo path
            ]);
        })
    );
});

// Fetch event: Serve from network, fallback to cache
self.addEventListener('fetch', (event) => {
    event.respondWith(
        fetch(event.request).catch(() => {
            return caches.match(event.request);
        })
    );
});