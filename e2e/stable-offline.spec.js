const { test, expect } = require('@playwright/test');

const BASE = process.env.MZ_E2E_BASE_URL || 'http://127.0.0.1';
const EMAIL = process.env.MZ_E2E_EMAIL || 'owner.e2e@milyzebra.test';
const PASSWORD = process.env.MZ_E2E_PASSWORD || 'StableE2E-2026!';

async function expectOwnerSession(page) {
  await expect(page.locator('.user-card').getByText('owner', { exact: true })).toBeVisible();
}

test('admin WebView/PWA survives offline reload, syncs sale and processes return', async ({ page, context }) => {
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

  const cached = await page.evaluate(() => ({
    me: Boolean(localStorage.getItem('mz_offline_snapshot:/me')),
    products: Boolean(localStorage.getItem('mz_offline_snapshot:/products')),
    inventory: Boolean(localStorage.getItem('mz_offline_snapshot:/inventory')),
    token: Boolean(localStorage.getItem('mz_token')),
  }));
  expect(cached).toEqual({ me: true, products: true, inventory: true, token: true });

  await context.setOffline(true);
  await page.reload({ waitUntil: 'domcontentloaded' });
  await expect(page.locator('#mz-connectivity-banner')).toContainText('Modo sin conexión');
  await expectOwnerSession(page);
  await expect(page.getByText('Modo offline', { exact: true })).toBeVisible();

  await page.getByRole('button', { name: 'Punto de venta' }).click();
  await page.getByRole('button', { name: /Blusa E2E/ }).first().click();
  await page.getByRole('button', { name: 'Cobrar' }).click();
  await expect(page.getByText(/guardada localmente/)).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Ventas offline' })).toBeVisible();
  await expect(page.getByText(/1 pendiente\(s\)/)).toBeVisible();

  await context.setOffline(false);
  await page.evaluate(() => window.dispatchEvent(new Event('online')));
  await expect(page.getByText(/1 venta\(s\) offline sincronizada\(s\)/)).toBeVisible({ timeout: 15000 });
  await expect(page.getByText('API conectada', { exact: true })).toBeVisible();

  const remaining = await page.evaluate(() => JSON.parse(localStorage.getItem('mz_offline_sales_v1') || '[]'));
  expect(remaining).toHaveLength(0);

  await page.getByRole('button', { name: 'Devoluciones' }).click();
  await expect(page.getByRole('heading', { name: 'Devolución de venta' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Devoluciones recientes' })).toBeVisible();
  const returnInput = page.getByLabel('Devolver Blusa E2E').first();
  await expect(returnInput).toBeEnabled();
  await returnInput.fill('1');
  await page.getByRole('button', { name: 'Registrar devolución' }).click();
  await expect(page.getByText(/Devolución registrada por/)).toBeVisible({ timeout: 10000 });
  await expect(page.getByText(/Reembolso: completed/)).toBeVisible();

  expect(pageErrors).toEqual([]);
});

test('public storefront renders without browser errors', async ({ page }) => {
  const errors = [];
  page.on('pageerror', (error) => errors.push(String(error)));
  await page.goto(BASE, { waitUntil: 'networkidle' });
  await expect(page.locator('#root')).toBeVisible();
  await expect(page.getByText('Mily Zebra', { exact: false }).first()).toBeVisible();
  expect(errors).toEqual([]);
});
