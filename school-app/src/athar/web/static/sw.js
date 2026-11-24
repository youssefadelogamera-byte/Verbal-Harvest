/* The installed app's service worker.
   It keeps only the app's icons and word lists, and shows a
   clear message when the school server cannot be reached. It never stores learner data: every /api/ and
   /learners/ request goes straight to the server, and nothing about a child is ever written to the phone. */
const SHELL = "lis-shell-v1";
const FILES = ["/static/ar.json", "/static/ar-server.json", "/static/brand/mark.svg",
               "/static/brand/icon-192.png", "/manifest.webmanifest"];
const OFFLINE = `<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Not connected</title><body style="font:16px/1.6 system-ui,sans-serif;margin:0;display:grid;place-items:center;min-height:100vh;background:#F5F7FB;color:#121C4A">
<main style="max-width:420px;padding:24px;text-align:center"><h1 style="font-size:20px">Cannot reach the school server</h1>
<p>Check that you are on the school network and that the server is running, then try again.</p>
<p dir="rtl" lang="ar">لا يمكن الوصول إلى خادم المدرسة. تأكّد أنك متصل بشبكة المدرسة ثم حاول مرة أخرى.</p>
<button onclick="location.reload()" style="font:inherit;padding:8px 18px;border-radius:10px;border:0;background:#1F3F8F;color:#fff">Try again</button></main></body></html>`;

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(SHELL).then((cache) => cache.addAll(FILES)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(caches.keys()
    .then((keys) => Promise.all(keys.filter((k) => k !== SHELL).map((k) => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (event.request.method !== "GET" || url.origin !== location.origin) return;
  if (url.pathname.startsWith("/api/") || url.pathname.startsWith("/learners/") || url.pathname === "/brand/logo") return;
  if (event.request.mode === "navigate") {
    // Always the newest page when the server answers; a plain message in both languages when it does not.
    event.respondWith(fetch(event.request).catch(() =>
      new Response(OFFLINE, { headers: { "Content-Type": "text/html; charset=utf-8" } })));
    return;
  }
  if (FILES.includes(url.pathname)) {
    event.respondWith(fetch(event.request).then((res) => {
      const copy = res.clone();
      caches.open(SHELL).then((cache) => cache.put(event.request, copy));
      return res;
    }).catch(() => caches.match(event.request)));
  }
});
