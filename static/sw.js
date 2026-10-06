const CACHE_NAME = 'ieav-louvor-v1';

self.addEventListener('install', (e) => {
    console.log('[Service Worker] Instalado com sucesso.');
    self.skipWaiting();
});

self.addEventListener('activate', (e) => {
    console.log('[Service Worker] Ativado.');
    return self.clients.claim();
});

self.addEventListener('fetch', (e) => {
    // Permite que o PWA funcione e interaja com a rede
    e.respondWith(
        fetch(e.request).catch(() => caches.match(e.request))
    );
});