import fs from 'node:fs';

const sw = fs.readFileSync(new URL('../public/sw.js', import.meta.url), 'utf8');
const registration = fs.readFileSync(new URL('../src/registerServiceWorker.js', import.meta.url), 'utf8');
const main = fs.readFileSync(new URL('../src/main.jsx', import.meta.url), 'utf8');

const required = [
  "CACHE_VERSION = 'mily-zebra-shell-v0.12.1'",
  "APP_SHELL = ['/', '/admin', '/index.html', '/manifest.webmanifest']",
  "url.pathname.startsWith('/api/')",
  "request.mode === 'navigate'",
  "caches.match('/index.html')",
];
for (const token of required) {
  if (!sw.includes(token)) throw new Error(`Service Worker sin contrato requerido: ${token}`);
}
if (!registration.includes("serviceWorker.register('/sw.js'")) throw new Error('Service Worker no se registra');
if (!main.includes('registerServiceWorker();')) throw new Error('main.jsx no activa el Service Worker');
console.log('PWA_OFFLINE_SHELL=PASS');
