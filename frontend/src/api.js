import { setConnectivity } from './connectivity';
import { clearSnapshots, isSnapshotPath, loadSnapshot, saveSnapshot } from './offlineSnapshot';

const API_URL = import.meta.env.VITE_API_URL || '/api';

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
    this.token = localStorage.getItem('mz_token') || '';
  }

  setToken(token) {
    this.token = token;
    if (token) localStorage.setItem('mz_token', token);
    else {
      localStorage.removeItem('mz_token');
      clearSnapshots();
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

  bootstrap(data, installationCode = '') {
    const supplied = String(installationCode || window.prompt('Ingrese el código de primera instalación mostrado por install.sh:') || '').trim();
    if (!supplied) throw new ApiError('Se requiere el código de primera instalación', 403);
    return this.request('/bootstrap', {
      method: 'POST',
      headers: { 'X-Bootstrap-Token': supplied },
      body: JSON.stringify(data),
    });
  }

  async login(email, password, tenantSlug = '') {
    const username = tenantSlug ? `${tenantSlug}:${email}` : email;
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
    if (response.status === 409 && !tenantSlug && String(body?.detail || '').includes('varias tiendas')) {
      const selected = String(window.prompt('Este correo pertenece a varias tiendas. Ingrese el identificador de su tienda:') || '').trim();
      if (selected) return this.login(email, password, selected);
    }
    if (!response.ok) throw new ApiError(body.detail || 'No se pudo iniciar sesión', response.status, body);
    this.setToken(body.access_token);
    return body;
  }
}

export const api = new ApiClient();
