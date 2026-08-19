const PREFIX = 'mz_offline_snapshot:';
const ALLOWED_PATHS = new Set(['/me', '/products', '/inventory', '/cash/current']);

export function snapshotKey(path) {
  if (!ALLOWED_PATHS.has(path)) return null;
  return `${PREFIX}${path}`;
}

export function saveSnapshot(path, value, storage = globalThis.localStorage) {
  const key = snapshotKey(path);
  if (!key || !storage) return;
  storage.setItem(key, JSON.stringify({ saved_at: new Date().toISOString(), value }));
}

export function loadSnapshot(path, storage = globalThis.localStorage) {
  const key = snapshotKey(path);
  if (!key || !storage) return null;
  const raw = storage.getItem(key);
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
  for (const path of ALLOWED_PATHS) storage.removeItem(snapshotKey(path));
}

export function isSnapshotPath(path) {
  return ALLOWED_PATHS.has(path);
}
