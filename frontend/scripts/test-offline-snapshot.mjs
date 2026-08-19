import { clearSnapshots, isSnapshotPath, loadSnapshot, saveSnapshot, snapshotKey } from '../src/offlineSnapshot.js';

class MemoryStorage {
  constructor() { this.map = new Map(); }
  getItem(k) { return this.map.has(k) ? this.map.get(k) : null; }
  setItem(k, v) { this.map.set(k, String(v)); }
  removeItem(k) { this.map.delete(k); }
}

const storage = new MemoryStorage();
if (!isSnapshotPath('/me') || !isSnapshotPath('/products') || !isSnapshotPath('/inventory')) throw new Error('rutas snapshot incompletas');
if (isSnapshotPath('/sales') || snapshotKey('/sales') !== null) throw new Error('una escritura no debe poder cachearse como snapshot');
saveSnapshot('/me', { id: 'u1', role: 'cashier', full_name: 'Caja' }, storage);
saveSnapshot('/products', [{ id: 'p1', sale_price: '100.00' }], storage);
if (loadSnapshot('/me', storage).value.role !== 'cashier') throw new Error('snapshot /me inválido');
if (loadSnapshot('/products', storage).value.length !== 1) throw new Error('snapshot products inválido');
clearSnapshots(storage);
if (loadSnapshot('/me', storage) !== null || loadSnapshot('/products', storage) !== null) throw new Error('clear snapshots falló');
console.log('OFFLINE_SNAPSHOT=PASS');
