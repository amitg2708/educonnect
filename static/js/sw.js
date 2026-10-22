/**
 * EduConnect Progressive Web App (PWA) Service Worker
 *
 * Implements:
 * 1. Pre-caching of versioned static assets and offline fallback page.
 * 2. Strict Network-Only isolation for all authenticated, student, payment, and private records.
 * 3. Safe cache-invalidation and version upgrade strategy (no stale/broken assets).
 * 4. Transparent offline error reporting (never fakes successful writes/mutations).
 */

const CACHE_VERSION = 'educonnect-pwa-v2026.10.22';
const STATIC_CACHE = `${CACHE_VERSION}-static`;
const PUBLIC_CACHE = `${CACHE_VERSION}-public`;

// Versioned static assets & fallback pre-cached upon service worker installation
const PRECACHE_ASSETS = [
    '/offline/',
    '/manifest.json',
    '/static/css/main.css',
    '/static/js/main.js',
    '/static/img/icons/icon-72x72.png',
    '/static/img/icons/icon-96x96.png',
    '/static/img/icons/icon-128x128.png',
    '/static/img/icons/icon-144x144.png',
    '/static/img/icons/icon-152x152.png',
    '/static/img/icons/icon-192x192.png',
    '/static/img/icons/icon-384x384.png',
    '/static/img/icons/icon-512x512.png',
];

// Sensitive, authenticated or private URL paths that MUST NEVER be stored in service worker cache
const SENSITIVE_URL_PATTERNS = [
    '/accounts/',
    '/fees/',
    '/attendance/',
    '/timetable/',
    '/academics/',
    '/complaints/',
    '/notifications/',
    '/admissions/admin/',
    '/admissions/application/',
    '/administration/',
    '/admin/',
    '/api/'
];

// Install Event: Pre-cache static assets and skip waiting immediately
self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(STATIC_CACHE).then((cache) => {
            return cache.addAll(PRECACHE_ASSETS);
        }).then(() => {
            return self.skipWaiting();
        }).catch((err) => {
            console.warn('[SW] Pre-cache warning:', err);
        })
    );
});

// Activate Event: Atomic cache purge of older application versions
self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys().then((cacheNames) => {
            return Promise.all(
                cacheNames.map((cacheName) => {
                    if (cacheName !== STATIC_CACHE && cacheName !== PUBLIC_CACHE) {
                        console.log('[SW] Purging outdated cache:', cacheName);
                        return caches.delete(cacheName);
                    }
                })
            );
        }).then(() => {
            return self.clients.claim();
        })
    );
});

// Helper: Check if URL represents private, authenticated, or sensitive operational records
function isSensitiveUrl(url) {
    return SENSITIVE_URL_PATTERNS.some((prefix) => url.pathname.startsWith(prefix));
}

// Helper: Check if request is a static asset or external asset library
function isStaticAsset(url) {
    return url.pathname.startsWith('/static/') ||
           url.hostname.includes('cdn.jsdelivr.net') ||
           url.hostname.includes('fonts.googleapis.com') ||
           url.hostname.includes('fonts.gstatic.com');
}

// Fetch Event: Dispatch custom caching strategies per request classification
self.addEventListener('fetch', (event) => {
    const request = event.request;
    const url = new URL(request.url);

    // 1. Non-GET requests (POST, PUT, DELETE, PATCH):
    // Never fake success offline. Attempt network; if offline, return structured 503 error.
    if (request.method !== 'GET') {
        event.respondWith(
            fetch(request).catch(() => {
                return new Response(
                    JSON.stringify({
                        error: 'offline',
                        message: 'This operation requires an active internet connection. Offline mutations cannot be processed.',
                        offline: true
                    }),
                    {
                        status: 503,
                        statusText: 'Service Unavailable (Offline)',
                        headers: { 'Content-Type': 'application/json' }
                    }
                );
            })
        );
        return;
    }

    // 2. Strict Network-Only for Sensitive & Authenticated Portals:
    // Guarantees student records, fee details, grades, and private notes are NEVER shared/cached.
    if (isSensitiveUrl(url)) {
        event.respondWith(
            fetch(request).catch((err) => {
                if (request.mode === 'navigate') {
                    return caches.match('/offline/');
                }
                throw err;
            })
        );
        return;
    }

    // 3. Static Assets: Cache-First with Network Fallback
    if (isStaticAsset(url)) {
        event.respondWith(
            caches.match(request).then((cachedResponse) => {
                if (cachedResponse) {
                    return cachedResponse;
                }
                return fetch(request).then((networkResponse) => {
                    if (networkResponse && networkResponse.status === 200) {
                        const responseToCache = networkResponse.clone();
                        caches.open(STATIC_CACHE).then((cache) => {
                            cache.put(request, responseToCache);
                        });
                    }
                    return networkResponse;
                });
            })
        );
        return;
    }

    // 4. Public Web Pages: Network-First with Stale Cache Fallback & Offline Fallback
    event.respondWith(
        fetch(request)
            .then((networkResponse) => {
                if (networkResponse && networkResponse.status === 200 && networkResponse.type === 'basic') {
                    const responseToCache = networkResponse.clone();
                    caches.open(PUBLIC_CACHE).then((cache) => {
                        cache.put(request, responseToCache);
                    });
                }
                return networkResponse;
            })
            .catch(() => {
                return caches.match(request).then((cachedResponse) => {
                    if (cachedResponse) {
                        return cachedResponse;
                    }
                    if (request.mode === 'navigate') {
                        return caches.match('/offline/');
                    }
                    return new Response('Network error occurred.', { status: 408, headers: { 'Content-Type': 'text/plain' } });
                });
            })
    );
});
