import { useEffect, useMemo, useState } from 'react';
import { api } from './api';
import {
  CustomersView,
  DeliveriesView,
  PurchasesView,
  SuppliersView,
  TransfersView,
  UsersDevicesView,
} from './Operations';
import {
  AccountingView,
  AnalyticsView,
  AutomationView,
  CrmView,
  FinanceView,
  PeopleView,
} from './ErpModules';
import ModuleSettings from './ModuleSettings';
import CatalogImportTools from './CatalogImportTools';

const money = new Intl.NumberFormat('es-HN', { style: 'currency', currency: 'HNL' });
const queryMode = new URLSearchParams(window.location.search).get('mode');

const roleViews = {
  cashier: ['pos', 'cash', 'customers'],
  sales: ['pos', 'products', 'customers', 'crm', 'deliveries'],
  warehouse: ['inventory', 'products', 'purchases', 'transfers', 'suppliers', 'deliveries'],
  driver: ['deliveries'],
};

const labels = {
  home: 'Panel de tienda',
  pos: 'Punto de venta',
  products: 'Catálogo',
  inventory: 'Inventario',
  cash: 'Caja',
  customers: 'Clientes',
  suppliers: 'Proveedores',
  purchases: 'Compras',
  transfers: 'Transferencias',
  deliveries: 'Entregas',
  crm: 'CRM',
  finance: 'Finanzas',
  accounting: 'Contabilidad',
  people: 'Personal',
  automation: 'Automatización',
  analytics: 'Analítica',
  modules: 'Módulos ERP',
  admin: 'Usuarios y dispositivos',
};

function Login({ onReady }) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [bootstrap, setBootstrap] = useState(false);
  const submit = async (event) => {
    event.preventDefault(); setError('');
    try {
      if (bootstrap) {
        const result = await api.bootstrap({ store_name: 'Mily Zebra', branch_name: 'Roatán', email, full_name: 'Propietario Mily Zebra', password });
        api.setToken(result.access_token);
      } else await api.login(email, password);
      onReady();
    } catch (err) { setError(err.message); }
  };
  return <main className="auth-shell"><section className="auth-card"><div className="brand-mark">MZ</div><p className="eyebrow">Mily Zebra Commerce OS</p><h1>{bootstrap ? 'Configurar la tienda' : 'Bienvenida de nuevo'}</h1><p className="muted">Moda, ventas e inventario en un mismo lugar.</p><form onSubmit={submit}><label>Correo<input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} /></label><label>Contraseña<input type="password" minLength="10" required value={password} onChange={(e) => setPassword(e.target.value)} /></label>{error && <div className="error">{error}</div>}<button className="primary" type="submit">{bootstrap ? 'Crear tienda' : 'Entrar'}</button></form><button className="link" onClick={() => setBootstrap(!bootstrap)}>{bootstrap ? 'Ya tengo una cuenta' : 'Primera instalación'}</button></section></main>;
}

function ProductForm({ onSaved }) {
  const initial = { sku: '', barcode: '', name: '', description: '', category: 'Mily Basics', size: '', color: '', unit_cost: '0', sale_price: '' };
  const [form, setForm] = useState(initial);
  const [busy, setBusy] = useState(false);
  const update = (name, value) => setForm((current) => ({ ...current, [name]: value }));
  const save = async (event) => { event.preventDefault(); setBusy(true); try { await api.request('/products', { method: 'POST', body: JSON.stringify(form) }); setForm(initial); await onSaved(); } finally { setBusy(false); } };
  return <form className="grid-form" onSubmit={save}><input placeholder="SKU" required value={form.sku} onChange={(e) => update('sku', e.target.value)} /><input placeholder="Código de barras" value={form.barcode} onChange={(e) => update('barcode', e.target.value)} /><input className="span-2" placeholder="Nombre del producto" required value={form.name} onChange={(e) => update('name', e.target.value)} /><input placeholder="Categoría" value={form.category} onChange={(e) => update('category', e.target.value)} /><input placeholder="Talla" value={form.size} onChange={(e) => update('size', e.target.value)} /><input placeholder="Color" value={form.color} onChange={(e) => update('color', e.target.value)} /><input type="number" step="0.01" placeholder="Costo" value={form.unit_cost} onChange={(e) => update('unit_cost', e.target.value)} /><input type="number" step="0.01" placeholder="Precio de venta" required value={form.sale_price} onChange={(e) => update('sale_price', e.target.value)} /><button className="primary" disabled={busy}>{busy ? 'Guardando…' : 'Crear producto'}</button></form>;
}

function Pos({ products, refresh }) {
  const [cart, setCart] = useState([]);
  const [message, setMessage] = useState('');
  const [method, setMethod] = useState('cash');
  const add = (product) => setCart((items) => { const found = items.find((item) => item.product.id === product.id); return found ? items.map((item) => item.product.id === product.id ? { ...item, qty: item.qty + 1 } : item) : [...items, { product, qty: 1 }]; });
  const total = cart.reduce((sum, item) => sum + Number(item.product.sale_price) * item.qty, 0);
  const sell = async () => {
    if (!cart.length) return; setMessage('');
    try {
      const result = await api.request('/sales', { method: 'POST', headers: { 'Idempotency-Key': crypto.randomUUID() }, body: JSON.stringify({ payment_method: method, lines: cart.map((item) => ({ product_id: item.product.id, quantity: item.qty })) }) });
      setCart([]); setMessage(`Venta ${result.id.slice(0, 8)} completada por ${money.format(Number(result.total))}`); await refresh();
    } catch (err) { setMessage(err.message); }
  };
  return <div className="pos-layout"><section className="panel"><div className="panel-title"><div><p className="eyebrow">Venta rápida</p><h2>Productos</h2></div><span>{products.length} activos</span></div><div className="product-grid">{products.map((product) => <button className="product-card" key={product.id} onClick={() => add(product)}><span className="product-avatar">{product.name.slice(0, 2).toUpperCase()}</span><strong>{product.name}</strong><small>{product.sku} · {product.size || 'Única'} · {product.color || '—'}</small><b>{money.format(Number(product.sale_price))}</b></button>)}</div></section><aside className="panel cart"><p className="eyebrow">Caja</p><h2>Venta actual</h2><div className="cart-lines">{cart.length === 0 && <p className="muted">Escanee o seleccione un producto.</p>}{cart.map((item) => <div className="cart-line" key={item.product.id}><span>{item.qty} × {item.product.name}</span><strong>{money.format(item.qty * Number(item.product.sale_price))}</strong></div>)}</div><label>Método de pago<select value={method} onChange={(e) => setMethod(e.target.value)}><option value="cash">Efectivo</option><option value="transfer">Transferencia</option><option value="card">Tarjeta / terminal externa</option></select></label><div className="total"><span>Total</span><strong>{money.format(total)}</strong></div><button className="primary checkout" onClick={sell} disabled={!cart.length}>Cobrar</button>{message && <div className="notice">{message}</div>}</aside></div>;
}

function Inventory({ rows, products, refresh }) {
  const [productId, setProductId] = useState(''); const [delta, setDelta] = useState('1'); const [reason, setReason] = useState('receiving');
  const apply = async () => { await api.request('/inventory/movements', { method: 'POST', body: JSON.stringify({ product_id: productId, quantity_delta: delta, reason }) }); setDelta('1'); await refresh(); };
  return <section className="panel"><div className="panel-title"><div><p className="eyebrow">Bodega</p><h2>Inventario</h2></div></div><div className="inventory-action"><select value={productId} onChange={(e) => setProductId(e.target.value)}><option value="">Producto…</option>{products.map((p) => <option key={p.id} value={p.id}>{p.sku} — {p.name}</option>)}</select><input type="number" step="0.001" value={delta} onChange={(e) => setDelta(e.target.value)} /><input value={reason} onChange={(e) => setReason(e.target.value)} /><button className="primary" disabled={!productId} onClick={apply}>Registrar movimiento</button></div><div className="table"><div className="tr th"><span>SKU</span><span>Producto</span><span>Sucursal</span><span>Existencia</span></div>{rows.map((row) => <div className="tr" key={`${row.branch_id}-${row.product_id}`}><span>{row.sku}</span><strong>{row.name}</strong><span>{row.branch_id.slice(0, 8)}</span><b>{row.quantity}</b></div>)}</div></section>;
}

function Cash() {
  const [opening, setOpening] = useState('0'); const [session, setSession] = useState(null); const [closing, setClosing] = useState('0'); const [message, setMessage] = useState('');
  const open = async () => { const result = await api.request('/cash/open', { method: 'POST', body: JSON.stringify({ opening_amount: opening }) }); setSession(result); setMessage('Caja abierta correctamente'); };
  const close = async () => { if (!session) return; await api.request(`/cash/${session.id}/close`, { method: 'POST', body: JSON.stringify({ closing_amount: closing }) }); setSession(null); setMessage('Caja cerrada y auditada'); };
  return <section className="panel narrow"><p className="eyebrow">Control de efectivo</p><h2>Caja diaria</h2>{!session ? <div className="stack"><label>Fondo inicial<input type="number" value={opening} onChange={(e) => setOpening(e.target.value)} /></label><button className="primary" onClick={open}>Abrir caja</button></div> : <div className="stack"><div className="notice">Sesión {session.id.slice(0, 8)} activa</div><label>Efectivo contado<input type="number" value={closing} onChange={(e) => setClosing(e.target.value)} /></label><button className="danger" onClick={close}>Cerrar caja</button></div>}{message && <p className="muted">{message}</p>}</section>;
}

function App() {
  const [me, setMe] = useState(null); const [products, setProducts] = useState([]); const [inventory, setInventory] = useState([]); const [loading, setLoading] = useState(Boolean(api.token));
  const initialView = queryMode === 'warehouse' ? 'inventory' : queryMode === 'cashier' ? 'pos' : queryMode === 'driver' ? 'deliveries' : 'home';
  const [view, setView] = useState(initialView);
  const refresh = async () => { const [meData, productData, stockData] = await Promise.all([api.request('/me'), api.request('/products'), api.request('/inventory')]); setMe(meData); setProducts(productData); setInventory(stockData); };
  useEffect(() => { if (api.token) refresh().catch(() => api.setToken('')).finally(() => setLoading(false)); }, []);
  const fullViews = ['home', 'analytics', 'pos', 'products', 'inventory', 'cash', 'customers', 'crm', 'suppliers', 'purchases', 'transfers', 'deliveries', 'finance', 'accounting', 'people', 'automation', 'modules', 'admin'];
  const allowed = useMemo(() => queryMode && roleViews[queryMode] ? roleViews[queryMode] : fullViews, []);
  if (loading) return <main className="center">Cargando Mily Zebra…</main>;
  if (!me) return <Login onReady={() => refresh().then(() => setView(initialView))} />;
  const managementOnly = new Set(['analytics', 'finance', 'accounting', 'people', 'automation']);
  const nav = allowed.filter((item) => {
    if (['admin', 'modules'].includes(item) && !['owner', 'admin'].includes(me.role)) return false;
    if (managementOnly.has(item) && !['owner', 'admin', 'manager', 'auditor'].includes(me.role)) return false;
    return true;
  });
  return <div className="app-shell"><aside className="sidebar"><div className="logo"><span>MZ</span><div><strong>Mily Zebra</strong><small>Commerce OS</small></div></div><nav>{nav.map((item) => <button key={item} className={view === item ? 'active' : ''} onClick={() => setView(item)}>{labels[item]}</button>)}</nav><div className="user-card"><strong>{me.full_name}</strong><small>{me.role}</small><button className="link" onClick={() => { api.setToken(''); location.reload(); }}>Cerrar sesión</button></div></aside><main className="workspace"><header><div><p className="eyebrow">Roatán · operación en vivo</p><h1>{labels[view] || 'Mily Zebra'}</h1></div><div className="status"><i /> API conectada</div></header>{view === 'home' && <div className="dashboard"><article><small>Productos</small><strong>{products.length}</strong><span>catálogo activo</span></article><article><small>Unidades visibles</small><strong>{inventory.reduce((sum, row) => sum + Number(row.quantity), 0)}</strong><span>en inventario</span></article><article><small>Modo</small><strong>{queryMode || 'completo'}</strong><span>{me.role}</span></article></div>}{view === 'analytics' && <AnalyticsView />}{view === 'pos' && <Pos products={products} refresh={refresh} />}{view === 'products' && <><section className="panel"><div className="panel-title"><div><p className="eyebrow">Catálogo</p><h2>Nuevo producto</h2></div></div><ProductForm onSaved={refresh} /><div className="product-list">{products.map((p) => <div key={p.id}><span><strong>{p.name}</strong><small>{p.sku} · {p.category}</small></span><b>{money.format(Number(p.sale_price))}</b></div>)}</div></section><CatalogImportTools onCatalogCommitted={refresh} /></>}{view === 'inventory' && <Inventory rows={inventory} products={products} refresh={refresh} />}{view === 'cash' && <Cash />}{view === 'customers' && <CustomersView />}{view === 'crm' && <CrmView />}{view === 'suppliers' && <SuppliersView />}{view === 'purchases' && <PurchasesView products={products} refreshInventory={refresh} />}{view === 'transfers' && <TransfersView products={products} refreshInventory={refresh} />}{view === 'deliveries' && <DeliveriesView me={me} />}{view === 'finance' && <FinanceView />}{view === 'accounting' && <AccountingView />}{view === 'people' && <PeopleView />}{view === 'automation' && <AutomationView />}{view === 'modules' && <ModuleSettings />}{view === 'admin' && <UsersDevicesView />}</main></div>;
}

export default App;
