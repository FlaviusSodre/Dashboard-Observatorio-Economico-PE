/* Service Worker — Observatório Econômico de Pernambuco */

const CACHE = 'observatorio-v4';

const SHELL = [
  '/',
  '/assets/style.css',
  '/assets/app_icon.png',
];

self.addEventListener('install', function(e) {
  e.waitUntil(
    caches.open(CACHE).then(function(cache) {
      return cache.addAll(SHELL);
    })
  );
  self.skipWaiting();
});

self.addEventListener('activate', function(e) {
  e.waitUntil(
    caches.keys().then(function(keys) {
      return Promise.all(
        keys.filter(function(k) { return k !== CACHE; })
            .map(function(k) { return caches.delete(k); })
      );
    })
  );
  self.clients.claim();
});

self.addEventListener('fetch', function(e) {
  var url = new URL(e.request.url);

  /* Nunca interceptar chamadas de dados do Dash (POST) */
  if (url.pathname.startsWith('/_dash-update-component')) return;
  if (url.pathname.startsWith('/_dash-layout')) return;
  if (url.pathname.startsWith('/_dash-dependencies')) return;

  /* Cache-first para assets estáticos (CSS, JS, imagens do bundle) */
  if (url.pathname.startsWith('/assets/') ||
      url.pathname.startsWith('/_dash-component-suites/')) {
    e.respondWith(
      caches.match(e.request).then(function(cached) {
        if (cached) return cached;
        return fetch(e.request).then(function(res) {
          var clone = res.clone();
          caches.open(CACHE).then(function(c) { c.put(e.request, clone); });
          return res;
        });
      })
    );
    return;
  }

  /* Network-first para o shell e todo o resto — fallback para cache offline */
  e.respondWith(
    fetch(e.request).catch(function() {
      return caches.match(e.request);
    })
  );
});
