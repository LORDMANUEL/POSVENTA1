import assert from 'node:assert/strict';

globalThis.localStorage = {
  getItem: () => null,
  setItem: () => {},
  removeItem: () => {},
};

const { tenantSlugFromLocation } = await import('../src/api.js');

assert.equal(tenantSlugFromLocation({ search: '?tenant=mily-zebra-sps' }), 'mily-zebra-sps');
assert.equal(tenantSlugFromLocation({ search: '?tenant=MILY-ZEBRA-TGU' }), 'mily-zebra-tgu');
assert.equal(tenantSlugFromLocation({ search: '?other=value' }), '');
assert.equal(tenantSlugFromLocation({ search: '' }), '');

console.log('TENANT_LOGIN_URL=PASS');
