import { clearSnapshots, isSnapshotPath, loadSnapshot, saveSnapshot, snapshotKey } from '../src/offlineSnapshot.js';

class MemoryStorage {
  constructor() { this.map = new Map(); }
  getItem(k) { return this.map.has(k) ? this.map.get(k) : null; }
  setItem(k, v) { this.map.set(k, String(v)); }
  removeItem(k) { this.map.delete(k); }
}

const storage = new MemoryStorage();
storage.setItem('mz_tenant_id', 'tenant-a');
for (const path of ['/me', '/products', '/inventory', '/cash/current']) {
  if (!isSnapshotPath(path)) throw new Error(`ruta snapshot faltante: ${path}`);
}
if (isSnapshotPath('/sales') || snapshotKey('/sales', storage) !== null) throw new Error('una escritura no debe poder cachearse como snapshot');

saveSnapshot('/me', { id: 'u1', role: 'cashier', full_name: 'Caja A' }, storage);
saveSnapshot('/products', [{ id: 'p1', sale_price: '100.00' }], storage);
saveSnapshot('/cash/current', { id: 'cash-a', opening_amount: '50.00', expected_amount: '50.00' }, storage);
if (loadSnapshot('/me', storage).value.full_name !== 'Caja A') throw new Error('snapshot /me tenant A inválido');

storage.setItem('mz_tenant_id', 'tenant-b');
if (loadSnapshot('/me', storage) !== null) throw new Error('tenant B no debe leer snapshot de tenant A');
saveSnapshot('/me', { id: 'u2', role: 'cashier', full_name: 'Caja B' }, storage);
saveSnapshot('/cash/current', { id: 'cash-b', opening_amount: '75.00', expected_amount: '75.00' }, storage);
if (loadSnapshot('/me', storage).value.full_name !== 'Caja B') throw new Error('snapshot /me tenant B inválido');

storage.setItem('mz_tenant_id', 'tenant-a');
if (loadSnapshot('/me', storage).value.full_name !== 'Caja A') throw new Error('snapshot tenant A fue sobrescrito por tenant B');
if (loadSnapshot('/cash/current', storage).value.id !== 'cash-a') throw new Error('snapshot caja tenant A inválido');
clearSnapshots(storage);
if (loadSnapshot('/me', storage) !== null) throw new Error('clear snapshots tenant A falló');

storage.setItem('mz_tenant_id', 'tenant-b');
if (loadSnapshot('/me', storage).value.full_name !== 'Caja B') throw new Error('clear tenant A no debe borrar tenant B');
if (loadSnapshot('/cash/current', storage).value.id !== 'cash-b') throw new Error('snapshot caja tenant B inválido');

console.log('OFFLINE_SNAPSHOT_TENANT_ISOLATION=PASS');
