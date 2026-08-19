import { useCallback, useEffect, useState } from 'react';
import { api } from './api';
import {
  getOfflineSales,
  queueOfflineSale,
  removeOfflineSale,
  retryOfflineSale,
  syncOfflineSales,
} from './offlineSales';

export async function submitSaleResilient({ payload, total, idempotencyKey }) {
  if (!navigator.onLine) {
    queueOfflineSale({ payload, total, idempotencyKey });
    return { offline: true, id: idempotencyKey, total };
  }
  try {
    const result = await api.request('/sales', {
      method: 'POST',
      headers: { 'Idempotency-Key': idempotencyKey },
      body: JSON.stringify(payload),
    });
    return { offline: false, ...result };
  } catch (error) {
    if (error?.network || error?.status === 0) {
      queueOfflineSale({ payload, total, idempotencyKey });
      return { offline: true, id: idempotencyKey, total };
    }
    throw error;
  }
}

export default function OfflineSalesStatus({ onSynced }) {
  const [items, setItems] = useState(() => getOfflineSales());
  const [syncing, setSyncing] = useState(false);
  const [message, setMessage] = useState('');

  const refresh = useCallback(() => setItems(getOfflineSales()), []);
  const sync = useCallback(async () => {
    if (syncing || !navigator.onLine) return;
    setSyncing(true); setMessage('');
    try {
      const result = await syncOfflineSales(api);
      refresh();
      if (result.synced > 0) {
        setMessage(`${result.synced} venta(s) offline sincronizada(s).`);
        if (onSynced) await onSynced();
      }
    } finally { setSyncing(false); }
  }, [onSynced, refresh, syncing]);

  useEffect(() => {
    const changed = () => refresh();
    const online = () => { refresh(); sync(); };
    window.addEventListener('mz:offline-sales-changed', changed);
    window.addEventListener('online', online);
    refresh();
    if (navigator.onLine) sync();
    return () => {
      window.removeEventListener('mz:offline-sales-changed', changed);
      window.removeEventListener('online', online);
    };
  }, []); // Intentionally initialize once; subsequent queue changes use the custom event.

  if (items.length === 0 && !message) return null;
  const pending = items.filter((item) => item.status === 'pending');
  const attention = items.filter((item) => item.status === 'needs_attention');
  return <section className="panel">
    <div className="panel-title"><div><p className="eyebrow">Resincronización</p><h2>Ventas offline</h2></div><span>{items.length} pendiente(s)</span></div>
    <p className="muted">Una venta offline no descuenta inventario hasta ser confirmada por el servidor. La misma clave idempotente evita duplicados.</p>
    <div className="inventory-action">
      <button className="primary" disabled={syncing || !navigator.onLine || pending.length === 0} onClick={sync}>{syncing ? 'Sincronizando…' : 'Sincronizar ahora'}</button>
      <span>{navigator.onLine ? 'Con conexión' : 'Sin conexión'}</span>
    </div>
    {message && <div className="notice">{message}</div>}
    <div className="product-list">{items.map((item) => <div key={item.idempotencyKey}><span><strong>{item.status === 'needs_attention' ? 'Requiere atención' : 'Pendiente'}</strong><small>{new Date(item.createdAt).toLocaleString('es-HN')} · L {Number(item.total).toFixed(2)} · {item.idempotencyKey.slice(0, 8)}</small>{item.lastError && <small>{item.lastError}</small>}</span><span>{item.status === 'needs_attention' && <button className="link" onClick={() => { retryOfflineSale(item.idempotencyKey); refresh(); }}>Reintentar</button>}<button className="link" onClick={() => { if (window.confirm('¿Eliminar esta venta offline pendiente?')) { removeOfflineSale(item.idempotencyKey); refresh(); } }}>Descartar</button></span></div>)}</div>
    {attention.length > 0 && <div className="error">{attention.length} venta(s) requieren revisión por stock, caja, permisos u otra validación del servidor.</div>}
  </section>;
}
