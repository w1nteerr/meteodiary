/* Service Worker (ТЗ 4.7.3): кэширование оболочки приложения, чтобы форма
   внесения наблюдения открывалась при отсутствии сети (черновики — IndexedDB,
   см. drafts.js). Стратегия: сеть с падением в кэш (network-first).
   Важно: перехватываются ТОЛЬКО пути из SHELL — раньше воркер вставал на пути
   у каждого GET-запроса (включая фавикон и статику) и добавлял задержку
   своего запуска к любой загрузке. */
const CACHE = "sinoptik-shell-v2";   // v2: сбросить старые кэши со старым HTML
const SHELL = ["/", "/observations/new/", "/static/js/drafts.js"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).catch(() => null));
  self.skipWaiting();
});

self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then((keys) =>
    Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))));
  self.clients.claim();
});

self.addEventListener("fetch", (e) => {
  if (e.request.method !== "GET") return;            // POST уходит в сеть/IndexedDB
  const path = new URL(e.request.url).pathname;
  if (!SHELL.includes(path)) return;                 // не наше — браузер грузит сам
  e.respondWith(
    fetch(e.request)
      .then((resp) => {
        if (resp.ok) {
          const copy = resp.clone();
          caches.open(CACHE).then((c) => c.put(e.request, copy));
        }
        return resp;
      })
      .catch(() => caches.match(e.request))
  );
});
