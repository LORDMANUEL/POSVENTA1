import fs from 'node:fs';

const source = fs.readFileSync(new URL('../src/Operations.jsx', import.meta.url), 'utf8');
const required = [
  "api.request('/platform/access')",
  "api.request('/platform/tenants')",
  "api.request('/platform/tenants', { method: 'POST'",
  'Empresas / tenants',
  'Crear empresa aislada',
  'admin_login_path',
];

for (const token of required) {
  if (!source.includes(token)) throw new Error(`UI de plataforma sin contrato requerido: ${token}`);
}

console.log('PLATFORM_TENANT_UI=PASS');
