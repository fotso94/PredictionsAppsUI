// Service Worker for PredictionsApp PWA
const CACHE_NAME = 'predictions-app-v1';
const STATIC_CACHE_NAME = 'predictions-app-static-v1';
const DYNAMIC_CACHE_NAME = 'predictions-app-dynamic-v1';

// Static assets to cache immediately
const STATIC_ASSETS = [
  '/',
  '/static/js/bundle.js',
  '/static/css/main.css',
  '/manifest.json',
  '/favicon.ico',
  '/offline.html'
];

// API endpoints to cache
const API_CACHE_PATTERNS = [
  /\/api\/predictions/,
  /\/api\/leagues/,
  /\/api\/matches/,
  /\/api\/articles/
];

// Install event - cache static assets
self.addEventListener('install', (event) => {
  console.log('Service Worker: Installing...');

  event.waitUntil(
    caches.open(STATIC_CACHE_NAME)
      .then((cache) => {
        console.log('Service Worker: Caching static assets...');
        return cache.addAll(STATIC_ASSETS);
      })
      .then(() => {
        console.log('Service Worker: Static assets cached');
        return self.skipWaiting();
      })
      .catch((error) => {
        console.error('Service Worker: Error caching static assets:', error);
      })
  );
});

// Activate event - clean up old caches
self.addEventListener('activate', (event) => {
  console.log('Service Worker: Activating...');

  event.waitUntil(
    caches.keys()
      .then((cacheNames) => {
        return Promise.all(
          cacheNames.map((cacheName) => {
            if (
              cacheName !== STATIC_CACHE_NAME &&
              cacheName !== DYNAMIC_CACHE_NAME &&
              cacheName.startsWith('predictions-app-')
            ) {
              console.log('Service Worker: Deleting old cache:', cacheName);
              return caches.delete(cacheName);
            }
          })
        );
      })
      .then(() => {
        console.log('Service Worker: Claiming clients...');
        return self.clients.claim();
      })
  );
});

// Fetch event - network first for API, cache first for static assets
self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // Skip non-GET requests
  if (request.method !== 'GET') {
    return;
  }

  // Skip chrome-extension requests
  if (url.protocol === 'chrome-extension:') {
    return;
  }

  // Handle API requests with network-first strategy
  if (isApiRequest(url)) {
    event.respondWith(networkFirstStrategy(request));
    return;
  }

  // Handle static assets with cache-first strategy
  if (isStaticAsset(url)) {
    event.respondWith(cacheFirstStrategy(request));
    return;
  }

  // Handle navigation requests
  if (request.mode === 'navigate') {
    event.respondWith(networkFirstWithFallback(request));
    return;
  }

  // Default: try network first, fallback to cache
  event.respondWith(networkFirstStrategy(request));
});

// Network-first strategy for API requests
async function networkFirstStrategy(request) {
  try {
    const networkResponse = await fetch(request);

    if (networkResponse.ok) {
      // Cache successful API responses
      if (isApiRequest(new URL(request.url))) {
        const cache = await caches.open(DYNAMIC_CACHE_NAME);
        cache.put(request, networkResponse.clone());
      }
    }

    return networkResponse;
  } catch (error) {
    console.log('Service Worker: Network failed, trying cache...', error);

    const cachedResponse = await caches.match(request);
    if (cachedResponse) {
      return cachedResponse;
    }

    // Return offline page for navigation requests
    if (request.mode === 'navigate') {
      return caches.match('/offline.html');
    }

    throw error;
  }
}

// Cache-first strategy for static assets
async function cacheFirstStrategy(request) {
  const cachedResponse = await caches.match(request);

  if (cachedResponse) {
    return cachedResponse;
  }

  try {
    const networkResponse = await fetch(request);

    if (networkResponse.ok) {
      const cache = await caches.open(STATIC_CACHE_NAME);
      cache.put(request, networkResponse.clone());
    }

    return networkResponse;
  } catch (error) {
    console.error('Service Worker: Failed to fetch asset:', error);
    throw error;
  }
}

// Network-first with offline fallback for navigation
async function networkFirstWithFallback(request) {
  try {
    return await fetch(request);
  } catch (error) {
    console.log('Service Worker: Network failed for navigation, showing offline page');
    return caches.match('/offline.html');
  }
}

// Helper functions
function isApiRequest(url) {
  return (
    url.hostname === 'api.predictionsapp.com' ||
    url.pathname.startsWith('/api/') ||
    API_CACHE_PATTERNS.some(pattern => pattern.test(url.pathname))
  );
}

function isStaticAsset(url) {
  return (
    url.pathname.startsWith('/static/') ||
    url.pathname.includes('.js') ||
    url.pathname.includes('.css') ||
    url.pathname.includes('.png') ||
    url.pathname.includes('.jpg') ||
    url.pathname.includes('.jpeg') ||
    url.pathname.includes('.svg') ||
    url.pathname.includes('.ico') ||
    url.pathname.includes('.woff') ||
    url.pathname.includes('.woff2')
  );
}

// Background sync for offline actions
self.addEventListener('sync', (event) => {
  console.log('Service Worker: Background sync triggered:', event.tag);

  if (event.tag === 'background-predictions-sync') {
    event.waitUntil(syncPredictions());
  }
});

async function syncPredictions() {
  try {
    console.log('Service Worker: Syncing predictions...');
    // Implement background sync logic here
    const response = await fetch('/api/predictions/today');
    if (response.ok) {
      const cache = await caches.open(DYNAMIC_CACHE_NAME);
      cache.put('/api/predictions/today', response);
      console.log('Service Worker: Predictions synced successfully');
    }
  } catch (error) {
    console.error('Service Worker: Failed to sync predictions:', error);
  }
}

// Push notification handling
self.addEventListener('push', (event) => {
  console.log('Service Worker: Push notification received');

  const options = {
    body: event.data ? event.data.text() : 'New predictions available!',
    icon: '/logo192.png',
    badge: '/badge-96x96.png',
    vibrate: [100, 50, 100],
    data: {
      dateOfArrival: Date.now(),
      primaryKey: 1
    },
    actions: [
      {
        action: 'view-predictions',
        title: 'View Predictions',
        icon: '/icons/view-96x96.png'
      },
      {
        action: 'close',
        title: 'Close',
        icon: '/icons/close-96x96.png'
      }
    ]
  };

  event.waitUntil(
    self.registration.showNotification('PredictionsApp', options)
  );
});

// Notification click handling
self.addEventListener('notificationclick', (event) => {
  console.log('Service Worker: Notification clicked:', event.action);

  event.notification.close();

  if (event.action === 'view-predictions') {
    event.waitUntil(
      clients.openWindow('/predictions/today')
    );
  } else if (event.action === 'close') {
    // Just close the notification
    return;
  } else {
    // Default action - open the app
    event.waitUntil(
      clients.openWindow('/')
    );
  }
});

console.log('Service Worker: Loaded successfully');