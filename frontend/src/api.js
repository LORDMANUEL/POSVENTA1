import { setConnectivity } from './connectivity';
import { clearSnapshots, isSnapshotPath, loadSnapshot, saveSnapshot } from './offlineSnapshot';

const API_URL = import.meta.env.VITE_API_URL || '/api';
const TOKEN_KEY = 'mz_token';
const TENANT_ID_KEY = 'mz_tenant_id';
const TENANT_SLUG_KEY = 'mz_tenant_slug';

export function tenantSlugFromLocation(locationLike = globalThis.location) {
  try {
    const params = new URLSearchParams(locationLike?.search || '');
    return String(params.get('tenant') || '').trim().toLowerCase();
  } catch {
    return '';
  }
}

function tokenTenantId(token) {
  try {
    const segment = String(token || '').split('.')[1];
    if (!segment || typeof globalThis.atob !== 'function') return '';
    const normalized = segment.replaceAll('-', '+').replaceAll('_', '/');
    const padded = normalized.padEnd(Math.ceil(normalized.length / 4) * 4, '=');
    const payload = JSON.parse(globalThis.atob(padded));
    return String(payload?.tenant_id || '');
  } catch {
    return '';
  }
}

export class ApiError extends Error {
  constructor(message, status = 0, body = null, network = false) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.body = body;
    this.network = network;
  }
}

export class ApiClient {
  constructor() {
    this.token = localStorage.getItem(TOKEN_KEY) || '';
    const requestedTenant = tenantSlugFromLocation();
    const storedTenantSlug = localStorage.getItem(TENANT_SLUG_KEY) || '';

    // A tenant-qualified URL is an explicit context switch. Never keep a token
    // from another tenant in the persistent WebView2 profile.
    if (requestedTenant && this.token && storedTenantSlug !== requestedTenant) {
      this.setToken('');
    } else if (this.token && !localStorage.getItem(TENANT_ID_KEY)) {
      const tenantId = tokenTenantId(this.token);
      if (tenantId) localStorage.setItem(TENANT_ID_KEY, tenantId);
    }
  }

  setToken(token, tenantSlug = null) {
    this.token = token;
    if (token) {
      localStorage.setItem(TOKEN_KEY, token);
      const tenantId = tokenTenantId(token);
      if (tenantId) localStorage.setItem(TENANT_ID_KEY, tenantId);
      if (tenantSlug !== null) localStorage.setItem(TENANT_SLUG_KEY, String(tenantSlug || '').trim().toLowerCase());
    } else {
      // Clear tenant-scoped snapshots while the old tenant id is still known.
      clearSnapshots();
      localStorage.removeItem(TOKEN_KEY);
      localStorage.removeItem(TENANT_ID_KEY);
      localStorage.removeItem(TENANT_SLUG_KEY);
    }
  }

  async request(path, options = {}) {
    const method = String(options.method || 'GET').toUpperCase();
    const headers = new Headers(options.headers || {});
    if (this.token) headers.set('Authorization', `Bearer ${this.token}`);
    if (options.body && !(options.body instanceof FormData)) headers.set('Content-Type', 'application/json');
    let response;
    try {
      response = await fetch(`${API_URL}${path}`, { ...options, headers });
      setConnectivity(true);
    } catch (error) {
      setConnectivity(false);
      if (method === 'GET' && isSnapshotPath(path)) {
        const cached = loadSnapshot(path);
        if (cached) return cached.value;
      }
      throw new ApiError('Sin conexión con el servidor', 0, null, true, { cause: error });
    }
    const text = await response.text();
    let body = null;
    try { body = text ? JSON.parse(text) : null; } catch { body = text; }
    if (!response.ok) {
      const detail = body?.detail;
      const message = typeof detail === 'string' ? detail : (detail ? JSON.stringify(detail) : (body || `HTTP ${response.status}`));
      throw new ApiError(String(message), response.status, body, false);
    }
    if (method === 'GET' && isSnapshotPath(path)) saveSnapshot(path, body);
    return body;
  }

  async bootstrap(data, installationCode = '') {
    const supplied = String(
      installationCode
      || window.prompt('Ingrese el código de primera instalación guardado por el instalador en .bootstrap-token:')
      || '',
    ).trim();
    if (!supplied) throw new ApiError('Se requiere el código de primera instalación', 403);
    const body = await this.request('/bootstrap', {
      method: 'POST',
      headers: { 'X-Bootstrap-Token': supplied },
      body: JSON.stringify(data),
    });
    this.setToken(body.access_token, data.store_slug || tenantSlugFromLocation() || '');
    return body;
  }

  async login(email, password, tenantSlug = '') {
    const selectedTenant = String(tenantSlug || tenantSlugFromLocation()).trim().toLowerCase();
    const username = selectedTenant ? `${selectedTenant}:${email}` : email;
    const form = new URLSearchParams({ username, password });
    let response;
    try {
      response = await fetch(`${API_URL}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: form,
      });
      setConnectivity(true);
    } catch (error) {
      setConnectivity(false);
      throw new ApiError('Sin conexión con el servidor', 0, null, true, { cause: error });
    }
    const body = await response.json();
    if (response.status === 409 && !selectedTenant && String(body?.detail || '').includes('varias tiendas')) {
      const selected = String(window.prompt('Este correo pertenece a varias tiendas. Ingrese el identificador de su tienda:') || '').trim();
      if (selected) return this.login(email, password, selected);
    }
    if (!response.ok) throw new ApiError(body.detail || 'No se pudo iniciar sesión', response.status, body);
    this.setToken(body.access_token, selectedTenant);
    return body;
  }
}

export const api = new ApiClient();
