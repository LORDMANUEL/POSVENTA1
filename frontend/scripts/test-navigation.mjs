import assert from 'node:assert/strict';
import { allowedViewsForRole, defaultViewForRole } from '../src/navigation.js';

assert.deepEqual(allowedViewsForRole('cashier'), ['home', 'pos', 'cash', 'customers']);
assert.equal(defaultViewForRole('cashier'), 'pos');

assert.deepEqual(
  allowedViewsForRole('warehouse'),
  ['home', 'inventory', 'products', 'purchases', 'transfers', 'suppliers', 'deliveries'],
);
assert.equal(defaultViewForRole('warehouse'), 'inventory');

assert.deepEqual(allowedViewsForRole('driver'), ['home', 'deliveries']);
assert.equal(defaultViewForRole('driver'), 'deliveries');

const adminViews = allowedViewsForRole('admin');
assert(adminViews.includes('modules'));
assert(adminViews.includes('admin'));
assert.equal(defaultViewForRole('admin'), 'home');

console.log('navigation role contracts: ok');
