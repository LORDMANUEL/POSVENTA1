import { clearSnapshots, isSnapshotPath, loadSnapshot, saveSnapshot, snapshotKey } from '../src/offlineSnapshot.js';

class MemoryStorage {
  constructor() { this.map = new Map(); }
  getItem(k) { return this.map.has(k) ? this.map.get(k) : null; }
  setItem(k, v) { this.map.set(k, String(v)); }
  removeItem(k) { this.map.delete(k); }
}

const storage = new MemoryStorage();
for (const path of ['/me', '/products', '/inventory', '/cash/current']) {
  if (!isSnapshotPath(path)) throw new Error(`ruta snapshot faltante: ${path}`);
}
if (isSnapshotPath('/sales') || snapshotKey('/sales') !== null) throw new Error('una escritura no debe poder cachearse como snapshot');
saveSnapshot('/me', { id: 'u1', role: 'cashier', full_name: 'Caja' }, storage);
saveSnapshot('/products', [{ id: 'p1', sale_price: '100.00' }], storage);
saveSnapshot('/cash/current', { id: 'cash-1', opening_amount: '50.00', expected_amount: '50.00' }, storage);
if (loadSnapshot('/me', storage).value.role !== 'cashier') throw new Error('snapshot /me inválido');
if (loadSnapshot('/products', storage).value.length !== 1) throw new Error('snapshot products inválido');
if (loadSnapshot('/cash/current', storage).value.id !== 'cash-1') throw new Error('snapshot caja inválido');
clearSnapshots(storage);
for (const path of ['/me', '/products', '/inventory', '/cash/current']) {
  if (loadSnapshot(path, storage) !== null) throw new Error(`clear snapshots falló: ${path}`);
}
console.log('OFFLINE_SNAPSHOT=PASS');
