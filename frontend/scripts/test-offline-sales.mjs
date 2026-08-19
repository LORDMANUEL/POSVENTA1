import assert from 'node:assert/strict';

const storage = new Map();
globalThis.localStorage = {
  getItem: (key) => storage.has(key) ? storage.get(key) : null,
  setItem: (key, value) => storage.set(key, String(value)),
  removeItem: (key) => storage.delete(key),
};
globalThis.localStorage.setItem('mz_tenant_id', 'tenant-a');
globalThis.CustomEvent = class CustomEvent { constructor(type, options = {}) { this.type = type; this.detail = options.detail; } };
globalThis.window = { dispatchEvent: () => {} };
Object.defineProperty(globalThis, 'navigator', { value: { onLine: false }, configurable: true });

const {
  getOfflineSales,
  queueOfflineSale,
  removeOfflineSale,
  retryOfflineSale,
  syncOfflineSales,
} = await import('../src/offlineSales.js');

await queueOfflineSale({
  idempotencyKey: 'offline-sale-0001',
  total: 500,
  payload: { payment_method: 'cash', lines: [{ product_id: 'p1', quantity: 1 }] },
});
assert.equal((await getOfflineSales()).length, 1);
assert.equal((await getOfflineSales())[0].status, 'pending');

let calls = 0;
const successfulApi = {
  request: async (_path, options) => {
    calls += 1;
    assert.equal(options.headers['Idempotency-Key'], 'offline-sale-0001');
    return { id: 'server-sale-1' };
  },
};
Object.defineProperty(globalThis, 'navigator', { value: { onLine: true }, configurable: true });
const synced = await syncOfflineSales(successfulApi);
assert.equal(synced.synced, 1);
assert.equal(calls, 1);
assert.equal((await getOfflineSales()).length, 0);

await queueOfflineSale({
  idempotencyKey: 'offline-sale-0002',
  total: 700,
  payload: { payment_method: 'cash', lines: [{ product_id: 'p2', quantity: 2 }] },
});
const conflictApi = {
  request: async () => {
    const error = new Error('Stock insuficiente');
    error.status = 409;
    error.network = false;
    throw error;
  },
};
const conflict = await syncOfflineSales(conflictApi);
assert.equal(conflict.needsAttention, 1);
assert.equal((await getOfflineSales())[0].status, 'needs_attention');
assert.match((await getOfflineSales())[0].lastError, /Stock insuficiente/);

await retryOfflineSale('offline-sale-0002');
assert.equal((await getOfflineSales())[0].status, 'pending');
assert.equal((await getOfflineSales())[0].lastError, null);
await removeOfflineSale('offline-sale-0002');

Object.defineProperty(globalThis, 'navigator', { value: { onLine: false }, configurable: true });
for (let i = 0; i < 250; i += 1) {
  await queueOfflineSale({
    idempotencyKey: `capacity-${String(i).padStart(4, '0')}`,
    total: 10 + i,
    payload: { payment_method: 'cash', lines: [{ product_id: `p-${i}`, quantity: 1 }] },
  });
}
const durableTenantA = await getOfflineSales();
assert.equal(durableTenantA.length, 250);
assert.equal(durableTenantA[0].idempotencyKey, 'capacity-0000');
assert.equal(durableTenantA.at(-1).idempotencyKey, 'capacity-0249');

// The same persistent browser/WebView2 profile can serve another tenant. Its
// queue must start empty and must never expose or synchronize tenant A rows.
globalThis.localStorage.setItem('mz_tenant_id', 'tenant-b');
assert.equal((await getOfflineSales()).length, 0);
await queueOfflineSale({
  idempotencyKey: 'tenant-b-sale-0001',
  total: 99,
  payload: { payment_method: 'cash', lines: [{ product_id: 'tenant-b-product', quantity: 1 }] },
});
const tenantB = await getOfflineSales();
assert.equal(tenantB.length, 1);
assert.equal(tenantB[0].idempotencyKey, 'tenant-b-sale-0001');
assert.equal(tenantB[0].tenantScope, 'tenant-b');

globalThis.localStorage.setItem('mz_tenant_id', 'tenant-a');
assert.equal((await getOfflineSales()).length, 250);

globalThis.localStorage.setItem('mz_tenant_id', 'tenant-b');
assert.equal((await getOfflineSales()).length, 1);

console.log('offline POS durable + tenant isolation logic: OK');
