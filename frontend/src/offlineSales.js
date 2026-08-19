const DB_NAME = 'mily-zebra-pos-offline';
const DB_VERSION = 1;
const SALES_STORE = 'sales';
const KEYS_STORE = 'keys';
const LEGACY_STORAGE_KEY = 'mz_offline_sales_v1';
const FALLBACK_STORAGE_KEY = 'mz_offline_sales_fallback_v2';
const CRYPTO_KEY_ID = 'payload-key';

let dbPromise = null;
let migrationPromise = null;
let syncInFlight = null;

function notifyChange() {
  if (globalThis.window?.dispatchEvent && globalThis.CustomEvent) {
    window.dispatchEvent(new CustomEvent('mz:offline-sales-changed'));
  }
}

function hasIndexedDb() {
  return typeof globalThis.indexedDB !== 'undefined';
}

function requestResult(request) {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error || new Error('IndexedDB request failed'));
  });
}

function transactionDone(tx) {
  return new Promise((resolve, reject) => {
    tx.oncomplete = () => resolve();
    tx.onabort = () => reject(tx.error || new Error('IndexedDB transaction aborted'));
    tx.onerror = () => reject(tx.error || new Error('IndexedDB transaction failed'));
  });
}

function openDb() {
  if (!hasIndexedDb()) return Promise.resolve(null);
  if (dbPromise) return dbPromise;
  dbPromise = new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains(SALES_STORE)) {
        const store = db.createObjectStore(SALES_STORE, { keyPath: 'idempotencyKey' });
        store.createIndex('status', 'status', { unique: false });
        store.createIndex('createdAt', 'createdAt', { unique: false });
      }
      if (!db.objectStoreNames.contains(KEYS_STORE)) {
        db.createObjectStore(KEYS_STORE, { keyPath: 'id' });
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error || new Error('No se pudo abrir IndexedDB'));
  });
  return dbPromise;
}

function readFallback() {
  try {
    const parsed = JSON.parse(globalThis.localStorage?.getItem(FALLBACK_STORAGE_KEY) || '[]');
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function writeFallback(items) {
  if (!globalThis.localStorage) return;
  globalThis.localStorage.setItem(FALLBACK_STORAGE_KEY, JSON.stringify(items));
}

async function getCryptoKey(db) {
  if (!db || !globalThis.crypto?.subtle) return null;
  const readTx = db.transaction(KEYS_STORE, 'readonly');
  const readDone = transactionDone(readTx);
  const existing = await requestResult(readTx.objectStore(KEYS_STORE).get(CRYPTO_KEY_ID));
  await readDone;
  if (existing?.key) return existing.key;

  const key = await crypto.subtle.generateKey(
    { name: 'AES-GCM', length: 256 },
    false,
    ['encrypt', 'decrypt'],
  );
  const writeTx = db.transaction(KEYS_STORE, 'readwrite');
  writeTx.objectStore(KEYS_STORE).put({ id: CRYPTO_KEY_ID, key });
  await transactionDone(writeTx);
  return key;
}

async function encodePayload(db, payload) {
  const raw = JSON.stringify(payload);
  const key = await getCryptoKey(db);
  if (!key) return { payloadJson: raw, iv: null, ciphertext: null };
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const ciphertext = await crypto.subtle.encrypt(
    { name: 'AES-GCM', iv },
    key,
    new TextEncoder().encode(raw),
  );
  return {
    payloadJson: null,
    iv: Array.from(iv),
    ciphertext: Array.from(new Uint8Array(ciphertext)),
  };
}

async function decodePayload(db, row) {
  if (row.payloadJson != null) return JSON.parse(row.payloadJson);
  const key = await getCryptoKey(db);
  if (!key || !row.iv || !row.ciphertext) {
    throw new Error('No se puede descifrar la venta offline');
  }
  const plaintext = await crypto.subtle.decrypt(
    { name: 'AES-GCM', iv: new Uint8Array(row.iv) },
    key,
    new Uint8Array(row.ciphertext),
  );
  return JSON.parse(new TextDecoder().decode(plaintext));
}

async function putIndexed(db, item) {
  const encoded = await encodePayload(db, item.payload);
  const row = { ...item, ...encoded };
  delete row.payload;
  const tx = db.transaction(SALES_STORE, 'readwrite');
  tx.objectStore(SALES_STORE).put(row);
  await transactionDone(tx);
}

async function migrateLegacyQueue() {
  if (migrationPromise) return migrationPromise;
  migrationPromise = (async () => {
    const raw = globalThis.localStorage?.getItem(LEGACY_STORAGE_KEY);
    if (!raw) return;
    let items = [];
    try {
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed)) items = parsed;
    } catch {
      return;
    }
    for (const item of items) {
      if (!item?.idempotencyKey || !item?.payload) continue;
      await queueOfflineSaleInternal(item);
    }
    globalThis.localStorage?.removeItem(LEGACY_STORAGE_KEY);
  })();
  return migrationPromise;
}

async function queueOfflineSaleInternal({ payload, total, idempotencyKey, ...existingMeta }) {
  const db = await openDb();
  if (!db) {
    const items = readFallback();
    if (items.some((item) => item.idempotencyKey === idempotencyKey)) return idempotencyKey;
    items.push({
      idempotencyKey,
      payload,
      total,
      status: existingMeta.status || 'pending',
      createdAt: existingMeta.createdAt || new Date().toISOString(),
      attempts: Number(existingMeta.attempts || 0),
      lastError: existingMeta.lastError || null,
    });
    writeFallback(items);
    return idempotencyKey;
  }

  const readTx = db.transaction(SALES_STORE, 'readonly');
  const readDone = transactionDone(readTx);
  const existing = await requestResult(readTx.objectStore(SALES_STORE).get(idempotencyKey));
  await readDone;
  if (existing) return idempotencyKey;
  await putIndexed(db, {
    idempotencyKey,
    payload,
    total,
    status: existingMeta.status || 'pending',
    createdAt: existingMeta.createdAt || new Date().toISOString(),
    attempts: Number(existingMeta.attempts || 0),
    lastError: existingMeta.lastError || null,
  });
  return idempotencyKey;
}

export async function getOfflineSales() {
  await migrateLegacyQueue();
  const db = await openDb();
  if (!db) return readFallback().sort((a, b) => a.createdAt.localeCompare(b.createdAt));
  const tx = db.transaction(SALES_STORE, 'readonly');
  const done = transactionDone(tx);
  const rows = await requestResult(tx.objectStore(SALES_STORE).getAll());
  await done;
  const decoded = [];
  for (const row of rows) {
    decoded.push({ ...row, payload: await decodePayload(db, row) });
  }
  return decoded.sort((a, b) => a.createdAt.localeCompare(b.createdAt));
}

export async function queueOfflineSale(data) {
  await migrateLegacyQueue();
  const result = await queueOfflineSaleInternal(data);
  notifyChange();
  return result;
}

export async function removeOfflineSale(idempotencyKey) {
  await migrateLegacyQueue();
  const db = await openDb();
  if (!db) {
    writeFallback(readFallback().filter((item) => item.idempotencyKey !== idempotencyKey));
  } else {
    const tx = db.transaction(SALES_STORE, 'readwrite');
    tx.objectStore(SALES_STORE).delete(idempotencyKey);
    await transactionDone(tx);
  }
  notifyChange();
}

async function updateOfflineSale(idempotencyKey, mutator) {
  const db = await openDb();
  if (!db) {
    const items = readFallback().map((item) => (
      item.idempotencyKey === idempotencyKey ? mutator(item) : item
    ));
    writeFallback(items);
    notifyChange();
    return;
  }
  const tx = db.transaction(SALES_STORE, 'readwrite');
  const done = transactionDone(tx);
  const store = tx.objectStore(SALES_STORE);
  const row = await requestResult(store.get(idempotencyKey));
  if (row) store.put(mutator(row));
  await done;
  notifyChange();
}

async function syncUnlocked(api) {
  const items = await getOfflineSales();
  if (globalThis.navigator?.onLine === false) {
    return {
      synced: 0,
      pending: items.filter((item) => item.status === 'pending').length,
      needsAttention: items.filter((item) => item.status === 'needs_attention').length,
    };
  }

  let synced = 0;
  for (const item of items) {
    if (item.status === 'needs_attention') continue;
    try {
      await api.request('/sales', {
        method: 'POST',
        headers: { 'Idempotency-Key': item.idempotencyKey },
        body: JSON.stringify(item.payload),
      });
      await removeOfflineSale(item.idempotencyKey);
      synced += 1;
    } catch (error) {
      const attempts = Number(item.attempts || 0) + 1;
      if (error?.network || error?.status === 0) {
        await updateOfflineSale(item.idempotencyKey, (row) => ({
          ...row,
          attempts,
          status: 'pending',
          lastError: error.message,
        }));
        break;
      }
      await updateOfflineSale(item.idempotencyKey, (row) => ({
        ...row,
        attempts,
        status: 'needs_attention',
        lastError: error?.message || 'Error de sincronización',
      }));
    }
  }

  const remaining = await getOfflineSales();
  return {
    synced,
    pending: remaining.filter((item) => item.status === 'pending').length,
    needsAttention: remaining.filter((item) => item.status === 'needs_attention').length,
  };
}

export async function syncOfflineSales(api) {
  const work = async () => {
    if (syncInFlight) return syncInFlight;
    syncInFlight = syncUnlocked(api).finally(() => { syncInFlight = null; });
    return syncInFlight;
  };
  if (globalThis.navigator?.locks?.request) {
    return navigator.locks.request('mily-zebra-offline-sales-sync', work);
  }
  return work();
}

export async function retryOfflineSale(idempotencyKey) {
  await migrateLegacyQueue();
  await updateOfflineSale(idempotencyKey, (row) => ({
    ...row,
    status: 'pending',
    lastError: null,
  }));
}

export const OFFLINE_DB_NAME = DB_NAME;
export const OFFLINE_SALES_STORE = SALES_STORE;
