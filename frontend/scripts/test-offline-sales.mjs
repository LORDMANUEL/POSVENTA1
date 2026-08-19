import assert from 'node:assert/strict';

const storage = new Map();
globalThis.localStorage = {
  getItem: (key) => storage.has(key) ? storage.get(key) : null,
  setItem: (key, value) => storage.set(key, String(value)),
  removeItem: (key) => storage.delete(key),
};
globalThis.CustomEvent = class CustomEvent { constructor(type) { this.type = type; } };
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
const durable = await getOfflineSales();
assert.equal(durable.length, 250);
assert.equal(durable[0].idempotencyKey, 'capacity-0000');
assert.equal(durable.at(-1).idempotencyKey, 'capacity-0249');

console.log('offline POS durable logic: OK');
