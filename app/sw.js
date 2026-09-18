/* 粵.fun Service Worker
   策略：
     - 首頁與索引：安裝時預快取；導航請求走「網路優先、離線回退」
     - 音檔：不可變，走「快取優先、按需寫入」，不預快取（3311 段、約 52 MB）
     - 其餘同源資源：快取優先 + 背景更新
   只處理同源 GET；跨域請求一律放行不攔截。 */

const VERSION = 'yf-v1';
const CORE = VERSION + '-core';
const MEDIA = VERSION + '-media';

const CORE_ASSETS = [
  './index.html',
  './manifest.json',
  './content/curriculum.json',
  './content/char_audio.json',
  './icons/icon-180.png',
  './icons/icon-192.png',
  './icons/icon-512.png'
];

self.addEventListener('install', event => {
  event.waitUntil((async () => {
    const cache = await caches.open(CORE);
    await Promise.allSettled(
      CORE_ASSETS.map(url => cache.add(new Request(url, { cache: 'reload' })))
    );
    await self.skipWaiting();
  })());
});

self.addEventListener('activate', event => {
  event.waitUntil((async () => {
    const keys = await caches.keys();
    await Promise.all(
      keys.filter(k => k.indexOf(VERSION) !== 0).map(k => caches.delete(k))
    );
    await self.clients.claim();
  })());
});

self.addEventListener('fetch', event => {
  const req = event.request;
  if (req.method !== 'GET') return;

  let url;
  try {
    url = new URL(req.url);
  } catch (e) {
    return;
  }
  if (url.origin !== self.location.origin) return;

  // 音檔：快取優先，首次播放後永久留在本機
  if (url.pathname.indexOf('/audio/') !== -1) {
    event.respondWith((async () => {
      const cache = await caches.open(MEDIA);
      const hit = await cache.match(req);
      if (hit) return hit;
      try {
        const res = await fetch(req);
        if (res && res.ok && res.status === 200) cache.put(req, res.clone());
        return res;
      } catch (e) {
        return Response.error();
      }
    })());
    return;
  }

  // 頁面導航：網路優先，離線時回退到快取的首頁
  if (req.mode === 'navigate') {
    event.respondWith((async () => {
      try {
        const res = await fetch(req);
        if (res && res.ok) {
          const cache = await caches.open(CORE);
          cache.put('./index.html', res.clone());
        }
        return res;
      } catch (e) {
        const cache = await caches.open(CORE);
        return (await cache.match('./index.html')) || Response.error();
      }
    })());
    return;
  }

  // 其餘同源資源：快取優先，同時背景更新
  event.respondWith((async () => {
    const cache = await caches.open(CORE);
    const hit = await cache.match(req);
    const network = fetch(req).then(res => {
      if (res && res.ok && res.status === 200) cache.put(req, res.clone());
      return res;
    }).catch(() => null);
    if (hit) {
      network.catch(() => {});
      return hit;
    }
    const res = await network;
    return res || Response.error();
  })());
});
