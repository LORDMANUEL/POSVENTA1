import { useEffect, useMemo, useState } from 'react';
import { api } from './api';

const money = new Intl.NumberFormat('es-HN', { style: 'currency', currency: 'HNL' });

function SectionTitle({ eyebrow, title, action }) {
  return <div className="panel-title"><div><p className="eyebrow">{eyebrow}</p><h2>{title}</h2></div>{action}</div>;
}

export function CustomersView() {
  const [rows, setRows] = useState([]);
  const [form, setForm] = useState({ full_name: '', email: '', phone: '', notes: '' });
  const load = () => api.request('/ops/customers').then(setRows);
  useEffect(() => { load(); }, []);
  const save = async (event) => {
    event.preventDefault();
    await api.request('/ops/customers', { method: 'POST', body: JSON.stringify(form) });
    setForm({ full_name: '', email: '', phone: '', notes: '' });
    await load();
  };
  return <section className="panel"><SectionTitle eyebrow="CRM" title="Clientes" /><form className="grid-form" onSubmit={save}><input required placeholder="Nombre completo" value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} /><input type="email" placeholder="Correo" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /><input placeholder="Teléfono" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} /><input placeholder="Notas" value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} /><button className="primary">Guardar cliente</button></form><div className="product-list">{rows.map((row) => <div key={row.id}><span><strong>{row.full_name}</strong><small>{row.phone || 'Sin teléfono'} · {row.email || 'Sin correo'}</small></span><b>{row.loyalty_points} pts</b></div>)}</div></section>;
}

export function SuppliersView() {
  const [rows, setRows] = useState([]);
  const [form, setForm] = useState({ name: '', contact_name: '', email: '', phone: '', tax_id: '', notes: '' });
  const load = () => api.request('/ops/suppliers').then(setRows);
  useEffect(() => { load(); }, []);
  const save = async (event) => { event.preventDefault(); await api.request('/ops/suppliers', { method: 'POST', body: JSON.stringify(form) }); setForm({ name: '', contact_name: '', email: '', phone: '', tax_id: '', notes: '' }); await load(); };
  return <section className="panel"><SectionTitle eyebrow="Compras" title="Proveedores" /><form className="grid-form" onSubmit={save}><input required placeholder="Proveedor" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /><input placeholder="Contacto" value={form.contact_name} onChange={(e) => setForm({ ...form, contact_name: e.target.value })} /><input type="email" placeholder="Correo" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /><input placeholder="Teléfono" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} /><input placeholder="RTN / identificación" value={form.tax_id} onChange={(e) => setForm({ ...form, tax_id: e.target.value })} /><button className="primary">Guardar proveedor</button></form><div className="product-list">{rows.map((row) => <div key={row.id}><span><strong>{row.name}</strong><small>{row.contact_name || 'Sin contacto'} · {row.phone || 'Sin teléfono'}</small></span><small>{row.tax_id || 'Sin RTN'}</small></div>)}</div></section>;
}

export function PurchasesView({ products, refreshInventory }) {
  const [suppliers, setSuppliers] = useState([]);
  const [supplierId, setSupplierId] = useState('');
  const [lines, setLines] = useState([]);
  const [productId, setProductId] = useState('');
  const [quantity, setQuantity] = useState('1');
  const [cost, setCost] = useState('0');
  const [message, setMessage] = useState('');
  useEffect(() => { api.request('/ops/suppliers').then(setSuppliers); }, []);
  const add = () => {
    if (!productId || Number(quantity) <= 0) return;
    const product = products.find((p) => p.id === productId);
    setLines((current) => [...current, { product_id: productId, name: product?.name || productId, quantity, unit_cost: cost }]);
    setProductId(''); setQuantity('1'); setCost('0');
  };
  const total = useMemo(() => lines.reduce((sum, line) => sum + Number(line.quantity) * Number(line.unit_cost), 0), [lines]);
  const createAndReceive = async () => {
    if (!supplierId || !lines.length) return;
    const created = await api.request('/ops/purchases', { method: 'POST', body: JSON.stringify({ supplier_id: supplierId, lines: lines.map(({ product_id, quantity, unit_cost }) => ({ product_id, quantity, unit_cost })) }) });
    await api.request(`/ops/purchases/${created.id}/receive`, { method: 'POST' });
    setLines([]); setMessage(`Compra ${created.id.slice(0, 8)} recibida e inventario actualizado.`); await refreshInventory();
  };
  return <section className="panel"><SectionTitle eyebrow="Bodega" title="Recepción de compra" /><div className="grid-form"><select value={supplierId} onChange={(e) => setSupplierId(e.target.value)}><option value="">Proveedor…</option>{suppliers.map((s) => <option value={s.id} key={s.id}>{s.name}</option>)}</select><select value={productId} onChange={(e) => { setProductId(e.target.value); const p = products.find((x) => x.id === e.target.value); if (p) setCost(String(p.unit_cost)); }}><option value="">Producto…</option>{products.map((p) => <option value={p.id} key={p.id}>{p.sku} — {p.name}</option>)}</select><input type="number" min="0.001" step="0.001" value={quantity} onChange={(e) => setQuantity(e.target.value)} placeholder="Cantidad" /><input type="number" min="0" step="0.01" value={cost} onChange={(e) => setCost(e.target.value)} placeholder="Costo unitario" /><button type="button" className="primary" onClick={add}>Agregar línea</button></div><div className="product-list">{lines.map((line, index) => <div key={`${line.product_id}-${index}`}><span><strong>{line.name}</strong><small>{line.quantity} × {money.format(Number(line.unit_cost))}</small></span><b>{money.format(Number(line.quantity) * Number(line.unit_cost))}</b></div>)}</div><div className="total"><span>Total compra</span><strong>{money.format(total)}</strong></div><button className="primary checkout" disabled={!supplierId || !lines.length} onClick={createAndReceive}>Crear y recibir compra</button>{message && <div className="notice">{message}</div>}</section>;
}

export function TransfersView({ products, refreshInventory }) {
  const [branches, setBranches] = useState([]);
  const [from, setFrom] = useState('');
  const [to, setTo] = useState('');
  const [productId, setProductId] = useState('');
  const [quantity, setQuantity] = useState('1');
  const [message, setMessage] = useState('');
  useEffect(() => { api.request('/admin/branches').then((rows) => { setBranches(rows); if (rows[0]) setFrom(rows[0].id); }); }, []);
  const transfer = async () => {
    const created = await api.request('/ops/transfers', { method: 'POST', body: JSON.stringify({ from_branch_id: from, to_branch_id: to, lines: [{ product_id: productId, quantity }] }) });
    await api.request(`/ops/transfers/${created.id}/ship`, { method: 'POST' });
    await api.request(`/ops/transfers/${created.id}/receive`, { method: 'POST' });
    setMessage(`Transferencia ${created.id.slice(0, 8)} recibida en destino.`); await refreshInventory();
  };
  return <section className="panel"><SectionTitle eyebrow="Inventario" title="Transferir entre sucursales" /><div className="grid-form"><select value={from} onChange={(e) => setFrom(e.target.value)}><option value="">Origen…</option>{branches.map((b) => <option value={b.id} key={b.id}>{b.code} — {b.name}</option>)}</select><select value={to} onChange={(e) => setTo(e.target.value)}><option value="">Destino…</option>{branches.map((b) => <option value={b.id} key={b.id}>{b.code} — {b.name}</option>)}</select><select value={productId} onChange={(e) => setProductId(e.target.value)}><option value="">Producto…</option>{products.map((p) => <option value={p.id} key={p.id}>{p.sku} — {p.name}</option>)}</select><input type="number" min="0.001" step="0.001" value={quantity} onChange={(e) => setQuantity(e.target.value)} /><button className="primary" disabled={!from || !to || from === to || !productId} onClick={transfer}>Despachar y recibir</button></div>{message && <div className="notice">{message}</div>}</section>;
}

export function DeliveriesView({ me }) {
  const [rows, setRows] = useState([]);
  const [message, setMessage] = useState('');
  const load = () => api.request('/ops/deliveries').then(setRows);
  useEffect(() => { load(); }, []);
  const update = async (id, status) => {
    const proof = status === 'delivered' ? window.prompt('Nota de prueba de entrega:') : null;
    if (status === 'delivered' && !proof) return;
    try { await api.request(`/ops/deliveries/${id}/status`, { method: 'POST', body: JSON.stringify({ status, proof_note: proof }) }); setMessage('Entrega actualizada.'); await load(); } catch (err) { setMessage(err.message); }
  };
  return <section className="panel"><SectionTitle eyebrow={me.role === 'driver' ? 'Mi ruta' : 'Logística'} title="Entregas" /><div className="delivery-grid">{rows.length === 0 && <p className="muted">No hay entregas asignadas.</p>}{rows.map((row) => <article className="delivery-card" key={row.id}><div><span className={`badge ${row.status}`}>{row.status.replaceAll('_', ' ')}</span><h3>{row.address_text}</h3><small>Entrega {row.id.slice(0, 8)}</small></div><div className="delivery-actions">{row.status === 'assigned' && <button className="primary" onClick={() => update(row.id, 'out_for_delivery')}>Salir a entregar</button>}{row.status === 'out_for_delivery' && <><button className="primary" onClick={() => update(row.id, 'delivered')}>Confirmar entrega</button><button className="danger" onClick={() => update(row.id, 'failed')}>No entregada</button></>}</div>{row.proof_note && <p className="notice">{row.proof_note}</p>}</article>)}</div>{message && <div className="notice">{message}</div>}</section>;
}

export function UsersDevicesView() {
  const [users, setUsers] = useState([]);
  const [devices, setDevices] = useState([]);
  const [branches, setBranches] = useState([]);
  const [userForm, setUserForm] = useState({ email: '', full_name: '', password: '', role: 'cashier', branch_id: '' });
  const [deviceForm, setDeviceForm] = useState({ branch_id: '', device_id: '', name: '' });
  const [deviceToken, setDeviceToken] = useState(null);
  const load = async () => {
    const [userRows, deviceRows, branchRows] = await Promise.all([api.request('/ops/users'), api.request('/admin/devices'), api.request('/admin/branches')]);
    setUsers(userRows); setDevices(deviceRows); setBranches(branchRows);
    if (!userForm.branch_id && branchRows[0]) setUserForm((f) => ({ ...f, branch_id: branchRows[0].id }));
    if (!deviceForm.branch_id && branchRows[0]) setDeviceForm((f) => ({ ...f, branch_id: branchRows[0].id }));
  };
  useEffect(() => { load(); }, []);
  const createUser = async (event) => { event.preventDefault(); await api.request('/ops/users', { method: 'POST', body: JSON.stringify(userForm) }); setUserForm((f) => ({ ...f, email: '', full_name: '', password: '' })); await load(); };
  const enroll = async (event) => { event.preventDefault(); const result = await api.request('/admin/devices/enroll', { method: 'POST', body: JSON.stringify(deviceForm) }); setDeviceToken(result); setDeviceForm((f) => ({ ...f, device_id: '', name: '' })); await load(); };
  return <div className="two-panels"><section className="panel"><SectionTitle eyebrow="Seguridad" title="Usuarios" /><form className="stack" onSubmit={createUser}><input type="email" required placeholder="Correo" value={userForm.email} onChange={(e) => setUserForm({ ...userForm, email: e.target.value })} /><input required placeholder="Nombre" value={userForm.full_name} onChange={(e) => setUserForm({ ...userForm, full_name: e.target.value })} /><input type="password" minLength="10" required placeholder="Contraseña temporal" value={userForm.password} onChange={(e) => setUserForm({ ...userForm, password: e.target.value })} /><select value={userForm.role} onChange={(e) => setUserForm({ ...userForm, role: e.target.value })}>{['admin','manager','cashier','sales','warehouse','driver','auditor','support'].map((role) => <option key={role}>{role}</option>)}</select><select value={userForm.branch_id} onChange={(e) => setUserForm({ ...userForm, branch_id: e.target.value })}>{branches.map((b) => <option value={b.id} key={b.id}>{b.name}</option>)}</select><button className="primary">Crear usuario</button></form><div className="product-list">{users.map((u) => <div key={u.id}><span><strong>{u.full_name}</strong><small>{u.email}</small></span><b>{u.role}</b></div>)}</div></section><section className="panel"><SectionTitle eyebrow="Hardware" title="Dispositivos" /><form className="stack" onSubmit={enroll}><select value={deviceForm.branch_id} onChange={(e) => setDeviceForm({ ...deviceForm, branch_id: e.target.value })}>{branches.map((b) => <option value={b.id} key={b.id}>{b.name}</option>)}</select><input required placeholder="ID del equipo, ej. POS-RTN-01" value={deviceForm.device_id} onChange={(e) => setDeviceForm({ ...deviceForm, device_id: e.target.value })} /><input required placeholder="Nombre visible" value={deviceForm.name} onChange={(e) => setDeviceForm({ ...deviceForm, name: e.target.value })} /><button className="primary">Enrolar agente</button></form>{deviceToken && <div className="token-box"><strong>Token mostrado una sola vez</strong><code>{deviceToken.token}</code><small>Configure MZ_AGENT_DEVICE_ID={deviceToken.device_id} y MZ_AGENT_TOKEN con este valor.</small></div>}<div className="product-list">{devices.map((d) => <div key={d.id}><span><strong>{d.name}</strong><small>{d.device_id}</small></span><b>{d.last_seen_at ? 'online/registrado' : 'sin heartbeat'}</b></div>)}</div></section></div>;
}
