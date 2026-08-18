/* Service Worker (ТЗ 4.7.3): офлайн-доступ к скрипту черновиков, чтобы форма
   внесения наблюдения продолжала работать без сети (сами черновики хранятся
   в IndexedDB, см. drafts.js).

   ВАЖНО о том, чего здесь намеренно НЕТ:
   раньше воркер кэшировал HTML-страницы ("/" и форму наблюдения). Это давало
   цикл при установке: воркер запрашивал "/", браузер при загрузке "/" снова
   обращался к sw.js, тот опять просил "/" — и так по кругу. Safari (особенно
   на iPad) не успевал завершить установку, и страница просто зависала.
   Поэтому кэшируем ТОЛЬКО статические файлы и не трогаем навигационные
   запросы: за HTML всегда отвечает сеть. */
const CACHE = "sinoptik-static-v4";

// только статика, никаких HTML-страниц
const ASSETS = ["/static/js/drafts.js"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(ASSETS)).catch(() => null));
  self.skipWaiting();
});

self.addEventListener("activate", (e) => {
  // удаляем кэши прошлых версий, в том числе те, где лежал HTML
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (e) => {
  const req = e.request;
  // Навигационные запросы (переходы по страницам) не перехватываем вообще —
  // именно они вызывали зацикливание.
  if (req.mode === "navigate" || req.destination === "document") return;
  if (req.method !== "GET") return;

  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;   // чужие домены не трогаем
  if (!ASSETS.includes(url.pathname)) return;

  // сеть с падением в кэш: свежая версия важнее, офлайн — запасной вариант
  e.respondWith(
    fetch(req)
      .then((resp) => {
        if (resp.ok) {
          const copy = resp.clone();
          caches.open(CACHE).then((c) => c.put(req, copy));
        }
        return resp;
      })
      .catch(() => caches.match(req))
  );
});
