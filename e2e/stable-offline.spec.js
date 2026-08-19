const { test, expect } = require('@playwright/test');

const BASE = process.env.MZ_E2E_BASE_URL || 'http://127.0.0.1';
const EMAIL = process.env.MZ_E2E_EMAIL || 'owner.e2e@milyzebra.test';
const PASSWORD = process.env.MZ_E2E_PASSWORD || 'StableE2E-2026!';

async function expectOwnerSession(page) {
  await expect(page.locator('.user-card').getByText('owner', { exact: true })).toBeVisible();
}

async function offlineQueueCount(page) {
  return page.evaluate(async () => new Promise((resolve, reject) => {
    const scope = localStorage.getItem('mz_tenant_id');
    if (!scope) return reject(new Error('tenant scope missing'));
    const request = indexedDB.open('mily-zebra-pos-offline', 2);
    request.onerror = () => reject(request.error);
    request.onsuccess = () => {
      const db = request.result;
      const tx = db.transaction('sales_by_tenant', 'readonly');
      const count = tx.objectStore('sales_by_tenant').index('tenantScope').count(scope);
      count.onsuccess = () => resolve(count.result);
      count.onerror = () => reject(count.error);
    };
  }));
}

test('admin WebView/PWA survives offline reload, recovers cash, syncs sale and processes return', async ({ page, context }) => {
  const pageErrors = [];
  page.on('pageerror', (error) => pageErrors.push(String(error)));

  await page.goto(`${BASE}/admin`, { waitUntil: 'networkidle' });
  await page.getByLabel('Correo').fill(EMAIL);
  await page.getByLabel('Contraseña').fill(PASSWORD);
  await page.getByRole('button', { name: 'Entrar' }).click();
  await expect(page.getByText('Mily Zebra', { exact: true }).first()).toBeVisible();
  await expectOwnerSession(page);

  await page.evaluate(async () => {
    await navigator.serviceWorker.ready;
    if (!navigator.serviceWorker.controller) {
      await new Promise((resolve) => navigator.serviceWorker.addEventListener('controllerchange', resolve, { once: true }));
    }
  });
  await page.reload({ waitUntil: 'networkidle' });
  await expectOwnerSession(page);

  await page.getByRole('button', { name: 'Caja' }).click();
  await page.getByLabel('Fondo inicial').fill('50');
  await page.getByRole('button', { name: 'Abrir caja' }).click();
  await expect(page.getByText('Caja abierta correctamente')).toBeVisible();
  await expect(page.getByText(/Sesión .* activa/)).toBeVisible();

  const cached = await page.evaluate(() => {
    const tenant = localStorage.getItem('mz_tenant_id');
    const prefix = `mz_offline_snapshot:v2:${tenant}:`;
    return {
      tenant: Boolean(tenant),
      me: Boolean(localStorage.getItem(`${prefix}/me`)),
      products: Boolean(localStorage.getItem(`${prefix}/products`)),
      inventory: Boolean(localStorage.getItem(`${prefix}/inventory`)),
      cash: Boolean(localStorage.getItem(`${prefix}/cash/current`)),
      token: Boolean(localStorage.getItem('mz_token')),
    };
  });
  expect(cached).toEqual({ tenant: true, me: true, products: true, inventory: true, cash: true, token: true });

  await context.setOffline(true);
  await page.reload({ waitUntil: 'domcontentloaded' });
  await expect(page.locator('#mz-connectivity-banner')).toContainText('Modo sin conexión');
  await expectOwnerSession(page);
  await expect(page.getByText('Modo offline', { exact: true })).toBeVisible();

  await page.getByRole('button', { name: 'Caja' }).click();
  await expect(page.getByText(/Sesión .* activa/)).toBeVisible();

  await page.getByRole('button', { name: 'Punto de venta' }).click();
  await page.getByRole('button', { name: /Blusa E2E/ }).first().click();
  await page.getByRole('button', { name: 'Cobrar' }).click();
  await expect(page.getByText(/guardada localmente/)).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Ventas offline' })).toBeVisible();
  await expect(page.getByText(/1 pendiente\(s\)/)).toBeVisible();
  expect(await offlineQueueCount(page)).toBe(1);

  await context.setOffline(false);
  await page.evaluate(() => window.dispatchEvent(new Event('online')));
  await expect(page.getByText(/1 venta\(s\) offline sincronizada\(s\)/)).toBeVisible({ timeout: 15000 });
  await expect(page.getByText('API conectada', { exact: true })).toBeVisible();
  await expect.poll(() => offlineQueueCount(page)).toBe(0);
  const legacyQueue = await page.evaluate(() => localStorage.getItem('mz_offline_sales_v1'));
  expect(legacyQueue).toBeNull();

  await page.getByRole('button', { name: 'Devoluciones' }).click();
  await expect(page.getByRole('heading', { name: 'Devolución de venta' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Devoluciones recientes' })).toBeVisible();
  const returnInput = page.getByLabel('Devolver Blusa E2E').first();
  await expect(returnInput).toBeEnabled();
  await returnInput.fill('1');
  await page.getByRole('button', { name: 'Registrar devolución' }).click();
  await expect(page.getByText(/Devolución registrada por/)).toBeVisible({ timeout: 10000 });
  await expect(page.getByText(/Reembolso: completed/)).toBeVisible();

  await page.getByRole('button', { name: 'Caja' }).click();
  await expect(page.getByText(/Sesión .* activa/)).toBeVisible();
  await page.getByLabel('Efectivo contado').fill('50');
  await page.getByRole('button', { name: 'Cerrar caja' }).click();
  await expect(page.getByText('Caja cerrada y auditada')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Abrir caja' })).toBeVisible();

  expect(pageErrors).toEqual([]);
});

test('tenant-qualified admin URL clears another tenant session before login', async ({ page }) => {
  await page.goto(`${BASE}/admin`, { waitUntil: 'networkidle' });
  await page.getByLabel('Correo').fill(EMAIL);
  await page.getByLabel('Contraseña').fill(PASSWORD);
  await page.getByRole('button', { name: 'Entrar' }).click();
  await expectOwnerSession(page);
  const firstTenant = await page.evaluate(() => localStorage.getItem('mz_tenant_id'));
  expect(firstTenant).toBeTruthy();

  await page.goto(`${BASE}/admin?tenant=mily-zebra-sps-e2e`, { waitUntil: 'networkidle' });
  await expect(page.getByRole('button', { name: 'Entrar' })).toBeVisible();
  expect(await page.evaluate(() => localStorage.getItem('mz_token'))).toBeNull();

  await page.getByLabel('Correo').fill('owner.sps.e2e@milyzebra.test');
  await page.getByLabel('Contraseña').fill('SecondTenantE2E-2026!');
  await page.getByRole('button', { name: 'Entrar' }).click();
  await expectOwnerSession(page);
  const second = await page.evaluate(async () => {
    const token = localStorage.getItem('mz_token');
    const tenantId = localStorage.getItem('mz_tenant_id');
    const access = await fetch('/api/platform/access', { headers: { Authorization: `Bearer ${token}` } }).then((r) => r.json());
    return { tenantId, platformAdmin: access.platform_admin, slug: localStorage.getItem('mz_tenant_slug') };
  });
  expect(second.tenantId).toBeTruthy();
  expect(second.tenantId).not.toBe(firstTenant);
  expect(second.platformAdmin).toBe(false);
  expect(second.slug).toBe('mily-zebra-sps-e2e');
});

test('second tenant storefront resolves its own catalog and admin route', async ({ page }) => {
  const errors = [];
  page.on('pageerror', (error) => errors.push(String(error)));
  await page.goto(`${BASE}/?store=mily-zebra-sps-e2e`, { waitUntil: 'networkidle' });
  await expect(page.getByText('Mily Zebra SPS E2E', { exact: false }).first()).toBeVisible();
  await expect(page.getByText('Producto tenant dos', { exact: true })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Equipo' })).toHaveAttribute('href', '/admin?tenant=mily-zebra-sps-e2e');
  expect(errors).toEqual([]);
});

test('public storefront renders without browser errors', async ({ page }) => {
  const errors = [];
  page.on('pageerror', (error) => errors.push(String(error)));
  await page.goto(BASE, { waitUntil: 'networkidle' });
  await expect(page.locator('#root')).toBeVisible();
  await expect(page.getByText('Mily Zebra', { exact: false }).first()).toBeVisible();
  expect(errors).toEqual([]);
});
