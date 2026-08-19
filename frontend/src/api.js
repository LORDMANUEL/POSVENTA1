const API_URL = import.meta.env.VITE_API_URL || '/api';

export class ApiClient {
  constructor() {
    this.token = localStorage.getItem('mz_token') || '';
  }

  setToken(token) {
    this.token = token;
    if (token) localStorage.setItem('mz_token', token);
    else localStorage.removeItem('mz_token');
  }

  async request(path, options = {}) {
    const headers = new Headers(options.headers || {});
    if (this.token) headers.set('Authorization', `Bearer ${this.token}`);
    if (options.body && !(options.body instanceof FormData)) headers.set('Content-Type', 'application/json');
    const response = await fetch(`${API_URL}${path}`, { ...options, headers });
    const text = await response.text();
    let body = null;
    try { body = text ? JSON.parse(text) : null; } catch { body = text; }
    if (!response.ok) throw new Error(body?.detail || body || `HTTP ${response.status}`);
    return body;
  }

  bootstrap(data) {
    return this.request('/bootstrap', { method: 'POST', body: JSON.stringify(data) });
  }

  async login(email, password) {
    const form = new URLSearchParams({ username: email, password });
    const response = await fetch(`${API_URL}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: form,
    });
    const body = await response.json();
    if (!response.ok) throw new Error(body.detail || 'No se pudo iniciar sesión');
    this.setToken(body.access_token);
    return body;
  }
}

export const api = new ApiClient();
