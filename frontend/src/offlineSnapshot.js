const PREFIX = 'mz_offline_snapshot:v2:';
const LEGACY_PREFIX = 'mz_offline_snapshot:';
const TENANT_ID_KEY = 'mz_tenant_id';
const ALLOWED_PATHS = new Set(['/me', '/products', '/inventory', '/cash/current']);

function tenantScope(storage = globalThis.localStorage) {
  return String(storage?.getItem(TENANT_ID_KEY) || 'unscoped');
}

export function snapshotKey(path, storage = globalThis.localStorage) {
  if (!ALLOWED_PATHS.has(path)) return null;
  return `${PREFIX}${tenantScope(storage)}:${path}`;
}

function legacyKey(path) {
  return `${LEGACY_PREFIX}${path}`;
}

export function saveSnapshot(path, value, storage = globalThis.localStorage) {
  const key = snapshotKey(path, storage);
  if (!key || !storage) return;
  storage.setItem(key, JSON.stringify({ saved_at: new Date().toISOString(), value }));
}

export function loadSnapshot(path, storage = globalThis.localStorage) {
  const key = snapshotKey(path, storage);
  if (!key || !storage) return null;
  let raw = storage.getItem(key);

  // v0.12.0/v0.12.1-RC used unscoped snapshot keys. Multitenancy was not
  // operational there, so a legacy snapshot belongs to the current first
  // tenant and can be migrated once when that user upgrades.
  if (!raw) {
    const oldKey = legacyKey(path);
    raw = storage.getItem(oldKey);
    if (raw) {
      storage.setItem(key, raw);
      storage.removeItem(oldKey);
    }
  }
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw);
    return parsed && Object.prototype.hasOwnProperty.call(parsed, 'value') ? parsed : null;
  } catch {
    storage.removeItem(key);
    return null;
  }
}

export function clearSnapshots(storage = globalThis.localStorage) {
  if (!storage) return;
  for (const path of ALLOWED_PATHS) {
    storage.removeItem(snapshotKey(path, storage));
    storage.removeItem(legacyKey(path));
  }
}

export function isSnapshotPath(path) {
  return ALLOWED_PATHS.has(path);
}
