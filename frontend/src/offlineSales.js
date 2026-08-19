const DB_NAME = 'mily-zebra-pos-offline';
const DB_VERSION = 2;
const SALES_STORE = 'sales_by_tenant';
const LEGACY_INDEXED_STORE = 'sales';
const KEYS_STORE = 'keys';
const LEGACY_STORAGE_KEY = 'mz_offline_sales_v1';
const FALLBACK_STORAGE_KEY = 'mz_offline_sales_fallback_v2';
const TENANT_ID_KEY = 'mz_tenant_id';
const LEGACY_CRYPTO_KEY_ID = 'payload-key';

let dbPromise = null;
let migrationPromise = null;
let syncInFlight = null;

function tenantScope() {
  const scope = String(globalThis.localStorage?.getItem(TENANT_ID_KEY) || '').trim();
  if (!scope) throw new Error('La sesión no tiene tenant; no se puede operar la cola offline');
  return scope;
}

function notifyChange(scope = '') {
  if (globalThis.window?.dispatchEvent && globalThis.CustomEvent) {
    window.dispatchEvent(new CustomEvent('mz:offline-sales-changed', { detail: { tenantScope: scope } }));
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
        const store = db.createObjectStore(SALES_STORE, { keyPath: ['tenantScope', 'idempotencyKey'] });
        store.createIndex('tenantScope', 'tenantScope', { unique: false });
        store.createIndex('tenantStatus', ['tenantScope', 'status'], { unique: false });
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

function readFallbackAll() {
  try {
    const parsed = JSON.parse(globalThis.localStorage?.getItem(FALLBACK_STORAGE_KEY) || '[]');
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function writeFallbackAll(items) {
  if (!globalThis.localStorage) return;
  globalThis.localStorage.setItem(FALLBACK_STORAGE_KEY, JSON.stringify(items));
}

function readFallback(scope) {
  return readFallbackAll().filter((item) => item.tenantScope === scope);
}

async function getCryptoKey(db, scope) {
  if (!db || !globalThis.crypto?.subtle) return null;
  const keyId = `payload-key:${scope}`;
  const readTx = db.transaction(KEYS_STORE, 'readonly');
  const readDone = transactionDone(readTx);
  const existing = await requestResult(readTx.objectStore(KEYS_STORE).get(keyId));
  await readDone;
  if (existing?.key) return existing.key;

  const key = await crypto.subtle.generateKey(
    { name: 'AES-GCM', length: 256 },
    false,
    ['encrypt', 'decrypt'],
  );
  const writeTx = db.transaction(KEYS_STORE, 'readwrite');
  writeTx.objectStore(KEYS_STORE).put({ id: keyId, key });
  await transactionDone(writeTx);
  return key;
}

async function getLegacyCryptoKey(db) {
  if (!db || !globalThis.crypto?.subtle || !db.objectStoreNames.contains(KEYS_STORE)) return null;
  const tx = db.transaction(KEYS_STORE, 'readonly');
  const done = transactionDone(tx);
  const existing = await requestResult(tx.objectStore(KEYS_STORE).get(LEGACY_CRYPTO_KEY_ID));
  await done;
  return existing?.key || null;
}

async function encodePayload(db, scope, payload) {
  const raw = JSON.stringify(payload);
  const key = await getCryptoKey(db, scope);
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

async function decodePayload(db, scope, row) {
  if (row.payloadJson != null) return JSON.parse(row.payloadJson);
  const key = await getCryptoKey(db, scope);
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

async function decodeLegacyPayload(db, row) {
  if (row.payload != null) return row.payload;
  if (row.payloadJson != null) return JSON.parse(row.payloadJson);
  const key = await getLegacyCryptoKey(db);
  if (!key || !row.iv || !row.ciphertext) {
    throw new Error('No se puede descifrar una venta offline heredada');
  }
  const plaintext = await crypto.subtle.decrypt(
    { name: 'AES-GCM', iv: new Uint8Array(row.iv) },
    key,
    new Uint8Array(row.ciphertext),
  );
  return JSON.parse(new TextDecoder().decode(plaintext));
}

async function putIndexed(db, scope, item) {
  const encoded = await encodePayload(db, scope, item.payload);
  const row = { ...item, tenantScope: scope, ...encoded };
  delete row.payload;
  const tx = db.transaction(SALES_STORE, 'readwrite');
  tx.objectStore(SALES_STORE).put(row);
  await transactionDone(tx);
}

async function queueOfflineSaleInternal({ payload, total, idempotencyKey, ...existingMeta }, scope) {
  const db = await openDb();
  if (!db) {
    const all = readFallbackAll();
    if (all.some((item) => item.tenantScope === scope && item.idempotencyKey === idempotencyKey)) return idempotencyKey;
    all.push({
      tenantScope: scope,
      idempotencyKey,
      payload,
      total,
      status: existingMeta.status || 'pending',
      createdAt: existingMeta.createdAt || new Date().toISOString(),
      attempts: Number(existingMeta.attempts || 0),
      lastError: existingMeta.lastError || null,
    });
    writeFallbackAll(all);
    return idempotencyKey;
  }

  const readTx = db.transaction(SALES_STORE, 'readonly');
  const readDone = transactionDone(readTx);
  const existing = await requestResult(readTx.objectStore(SALES_STORE).get([scope, idempotencyKey]));
  await readDone;
  if (existing) return idempotencyKey;
  await putIndexed(db, scope, {
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

async function migrateLegacyQueue() {
  const scope = tenantScope();
  if (migrationPromise) return migrationPromise;
  migrationPromise = (async () => {
    const raw = globalThis.localStorage?.getItem(LEGACY_STORAGE_KEY);
    if (raw) {
      let items = [];
      try {
        const parsed = JSON.parse(raw);
        if (Array.isArray(parsed)) items = parsed;
      } catch {
        items = [];
      }
      for (const item of items) {
        if (!item?.idempotencyKey || !item?.payload) continue;
        await queueOfflineSaleInternal(item, scope);
      }
      globalThis.localStorage?.removeItem(LEGACY_STORAGE_KEY);
    }

    const fallback = readFallbackAll();
    let fallbackChanged = false;
    for (const item of fallback) {
      if (!item.tenantScope) {
        item.tenantScope = scope;
        fallbackChanged = true;
      }
    }
    if (fallbackChanged) writeFallbackAll(fallback);

    const db = await openDb();
    if (db?.objectStoreNames.contains(LEGACY_INDEXED_STORE)) {
      const tx = db.transaction(LEGACY_INDEXED_STORE, 'readonly');
      const done = transactionDone(tx);
      const rows = await requestResult(tx.objectStore(LEGACY_INDEXED_STORE).getAll());
      await done;
      for (const row of rows) {
        if (!row?.idempotencyKey) continue;
        const payload = await decodeLegacyPayload(db, row);
        await queueOfflineSaleInternal({ ...row, payload }, scope);
      }
      if (rows.length) {
        const clearTx = db.transaction(LEGACY_INDEXED_STORE, 'readwrite');
        clearTx.objectStore(LEGACY_INDEXED_STORE).clear();
        await transactionDone(clearTx);
      }
    }
  })();
  return migrationPromise;
}

export async function getOfflineSales() {
  const scope = tenantScope();
  await migrateLegacyQueue();
  const db = await openDb();
  if (!db) return readFallback(scope).sort((a, b) => a.createdAt.localeCompare(b.createdAt));
  const tx = db.transaction(SALES_STORE, 'readonly');
  const done = transactionDone(tx);
  const rows = await requestResult(tx.objectStore(SALES_STORE).index('tenantScope').getAll(scope));
  await done;
  const decoded = [];
  for (const row of rows) {
    decoded.push({ ...row, payload: await decodePayload(db, scope, row) });
  }
  return decoded.sort((a, b) => a.createdAt.localeCompare(b.createdAt));
}

export async function queueOfflineSale(data) {
  const scope = tenantScope();
  await migrateLegacyQueue();
  const result = await queueOfflineSaleInternal(data, scope);
  notifyChange(scope);
  return result;
}

export async function removeOfflineSale(idempotencyKey) {
  const scope = tenantScope();
  await migrateLegacyQueue();
  const db = await openDb();
  if (!db) {
    writeFallbackAll(readFallbackAll().filter((item) => !(item.tenantScope === scope && item.idempotencyKey === idempotencyKey)));
  } else {
    const tx = db.transaction(SALES_STORE, 'readwrite');
    tx.objectStore(SALES_STORE).delete([scope, idempotencyKey]);
    await transactionDone(tx);
  }
  notifyChange(scope);
}

async function updateOfflineSale(scope, idempotencyKey, mutator) {
  const db = await openDb();
  if (!db) {
    const items = readFallbackAll().map((item) => (
      item.tenantScope === scope && item.idempotencyKey === idempotencyKey ? mutator(item) : item
    ));
    writeFallbackAll(items);
    notifyChange(scope);
    return;
  }
  const tx = db.transaction(SALES_STORE, 'readwrite');
  const done = transactionDone(tx);
  const store = tx.objectStore(SALES_STORE);
  const row = await requestResult(store.get([scope, idempotencyKey]));
  if (row) store.put(mutator(row));
  await done;
  notifyChange(scope);
}

async function syncUnlocked(api, scope) {
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
        await updateOfflineSale(scope, item.idempotencyKey, (row) => ({
          ...row,
          attempts,
          status: 'pending',
          lastError: error.message,
        }));
        break;
      }
      await updateOfflineSale(scope, item.idempotencyKey, (row) => ({
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
  const scope = tenantScope();
  const work = async () => {
    if (syncInFlight) return syncInFlight;
    syncInFlight = syncUnlocked(api, scope).finally(() => { syncInFlight = null; });
    return syncInFlight;
  };
  if (globalThis.navigator?.locks?.request) {
    return navigator.locks.request(`mily-zebra-offline-sales-sync:${scope}`, work);
  }
  return work();
}

export async function retryOfflineSale(idempotencyKey) {
  const scope = tenantScope();
  await migrateLegacyQueue();
  await updateOfflineSale(scope, idempotencyKey, (row) => ({
    ...row,
    status: 'pending',
    lastError: null,
  }));
}

export const OFFLINE_DB_NAME = DB_NAME;
export const OFFLINE_SALES_STORE = SALES_STORE;
