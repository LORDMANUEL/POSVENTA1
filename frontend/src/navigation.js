export const FULL_VIEWS = [
  'home', 'analytics', 'pos', 'returns', 'products', 'inventory', 'cash', 'customers', 'crm',
  'suppliers', 'purchases', 'transfers', 'deliveries', 'finance', 'accounting',
  'people', 'automation', 'modules', 'admin',
];

const ROLE_VIEWS = {
  cashier: ['home', 'pos', 'returns', 'cash', 'customers'],
  sales: ['home', 'pos', 'returns', 'products', 'customers', 'crm', 'deliveries'],
  warehouse: ['home', 'inventory', 'products', 'purchases', 'transfers', 'suppliers', 'deliveries'],
  driver: ['home', 'deliveries'],
};

export function allowedViewsForRole(role) {
  return ROLE_VIEWS[role] ? [...ROLE_VIEWS[role]] : [...FULL_VIEWS];
}

export function defaultViewForRole(role) {
  if (role === 'cashier' || role === 'sales') return 'pos';
  if (role === 'warehouse') return 'inventory';
  if (role === 'driver') return 'deliveries';
  return 'home';
}
