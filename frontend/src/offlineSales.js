const STORAGE_KEY = 'mz_offline_sales_v1';
const MAX_QUEUE = 200;

function readQueue() {
  try {
    const parsed = JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]');
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function writeQueue(items) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(items.slice(-MAX_QUEUE)));
  window.dispatchEvent(new CustomEvent('mz:offline-sales-changed'));
}

export function getOfflineSales() {
  return readQueue();
}

export function queueOfflineSale({ payload, total, idempotencyKey }) {
  const items = readQueue();
  if (items.some((item) => item.idempotencyKey === idempotencyKey)) return idempotencyKey;
  items.push({
    idempotencyKey,
    payload,
    total,
    status: 'pending',
    createdAt: new Date().toISOString(),
    attempts: 0,
    lastError: null,
  });
  writeQueue(items);
  return idempotencyKey;
}

export function removeOfflineSale(idempotencyKey) {
  writeQueue(readQueue().filter((item) => item.idempotencyKey !== idempotencyKey));
}

export async function syncOfflineSales(api) {
  const items = readQueue();
  if (!navigator.onLine) {
    return {
      synced: 0,
      pending: items.filter((item) => item.status === 'pending').length,
      needsAttention: items.filter((item) => item.status === 'needs_attention').length,
    };
  }

  let synced = 0;
  const next = [];
  for (let index = 0; index < items.length; index += 1) {
    const item = items[index];
    if (item.status === 'needs_attention') {
      next.push(item);
      continue;
    }
    try {
      await api.request('/sales', {
        method: 'POST',
        headers: { 'Idempotency-Key': item.idempotencyKey },
        body: JSON.stringify(item.payload),
      });
      synced += 1;
    } catch (error) {
      const attempts = Number(item.attempts || 0) + 1;
      if (error?.network || error?.status === 0) {
        next.push({ ...item, attempts, status: 'pending', lastError: error.message });
        next.push(...items.slice(index + 1));
        break;
      }
      next.push({
        ...item,
        attempts,
        status: 'needs_attention',
        lastError: error?.message || 'Error de sincronización',
      });
    }
  }

  writeQueue(next);
  return {
    synced,
    pending: next.filter((item) => item.status === 'pending').length,
    needsAttention: next.filter((item) => item.status === 'needs_attention').length,
  };
}

export function retryOfflineSale(idempotencyKey) {
  const items = readQueue().map((item) => item.idempotencyKey === idempotencyKey
    ? { ...item, status: 'pending', lastError: null }
    : item);
  writeQueue(items);
}
