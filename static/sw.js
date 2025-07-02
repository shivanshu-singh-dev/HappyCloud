const CACHE_NAME = 'happycloud-v1';
const ASSETS = [
    '/',
    '/static/css/styles.css',
    '/static/js/app.js',
    '/static/icons/icon-192.png',
    '/static/icons/icon-512.png'
];

self.addEventListener('install', (e) => {
    e.waitUntil(
        caches.open(CACHE_NAME)
            .then(cache => cache.addAll(ASSETS))
            .then(() => self.skipWaiting())
    );
});

// self.addEventListener('fetch', (e) => {
//     e.respondWith(
//         caches.match(e.request)
//             .then(res => res || fetch(e.request))
//     );
// });

self.addEventListener('fetch', (e) => {
    e.respondWith(
        caches.match(e.request)
            .then(res => {
                return res || fetch(e.request)
                    .catch(() => caches.match('/offline'));
            })
    );
});