import { useEffect, useMemo, useState } from 'react';
import { api } from './api';

const money = new Intl.NumberFormat('es-HN', { style: 'currency', currency: 'HNL' });

function SectionTitle({ eyebrow, title, action }) {
  return <div className="panel-title"><div><p className="eyebrow">{eyebrow}</p><h2>{title}</h2></div>{action}</div>;
}

function ErrorBox({ error }) {
  return error ? <div className="error">{error}</div> : null;
}

export function AnalyticsView() {
  const [dashboard, setDashboard] = useState(null);
  const [top, setTop] = useState([]);
  const [forecast, setForecast] = useState(null);
  const [error, setError] = useState('');
  const load = async () => {
    setError('');
    try {
      const [summary, products, projection] = await Promise.all([
        api.request('/analytics/dashboard?days=30'),
        api.request('/analytics/top-products?days=30&limit=8'),
        api.request('/analytics/sales-forecast?lookback_days=28&forecast_days=14'),
      ]);
      setDashboard(summary); setTop(products); setForecast(projection);
    } catch (err) { setError(err.message); }
  };
  useEffect(() => { load(); }, []);
  return <div className="stack"><ErrorBox error={error} />{dashboard && <div className="dashboard"><article><small>Ventas POS · 30 días</small><strong>{money.format(Number(dashboard.pos_sales_total))}</strong><span>{dashboard.pos_sales_count} tickets</span></article><article><small>Pedidos web</small><strong>{money.format(Number(dashboard.online_orders_total))}</strong><span>{dashboard.online_orders_count} pedidos</span></article><article><small>Inventario a costo</small><strong>{money.format(Number(dashboard.inventory_cost_value))}</strong><span>{dashboard.inventory_units} unidades</span></article><article><small>Proyección · 14 días</small><strong>{money.format(Number(forecast?.projected_sales || 0))}</strong><span>{forecast?.method || '—'}</span></article></div>}<section className="panel"><SectionTitle eyebrow="Analítica" title="Productos con mayor venta" action={<button className="link" onClick={load}>Actualizar</button>} /><div className="table"><div className="tr th"><span>SKU</span><span>Producto</span><span>Unidades</span><span>Ingreso</span></div>{top.map((row) => <div className="tr" key={row.product_id}><span>{row.sku}</span><strong>{row.name}</strong><span>{row.quantity}</span><b>{money.format(Number(row.revenue))}</b></div>)}</div></section></div>;
}

export function AccountingView() {
  const [accounts, setAccounts] = useState([]);
  const [trial, setTrial] = useState([]);
  const [income, setIncome] = useState(null);
  const [balance, setBalance] = useState(null);
  const [form, setForm] = useState({ code: '', name: '', account_type: 'asset', parent_id: null });
  const [error, setError] = useState('');
  const load = async () => {
    setError('');
    try {
      const [a, t, i, b] = await Promise.all([
        api.request('/accounting/accounts'), api.request('/accounting/trial-balance'),
        api.request('/accounting/income-statement'), api.request('/accounting/balance-sheet'),
      ]);
      setAccounts(a); setTrial(t); setIncome(i); setBalance(b);
    } catch (err) { setError(err.message); }
  };
  useEffect(() => { load(); }, []);
  const create = async (event) => {
    event.preventDefault(); setError('');
    try { await api.request('/accounting/accounts', { method: 'POST', body: JSON.stringify(form) }); setForm({ code: '', name: '', account_type: 'asset', parent_id: null }); await load(); } catch (err) { setError(err.message); }
  };
  return <div className="stack"><ErrorBox error={error} /><div className="dashboard"><article><small>Ingresos</small><strong>{money.format(Number(income?.total_income || 0))}</strong><span>asientos publicados</span></article><article><small>Gastos</small><strong>{money.format(Number(income?.total_expenses || 0))}</strong><span>asientos publicados</span></article><article><small>Resultado</small><strong>{money.format(Number(income?.net_income || 0))}</strong><span>utilidad / pérdida</span></article><article><small>Balance</small><strong>{money.format(Number(balance?.difference || 0))}</strong><span>diferencia A = P + C</span></article></div><section className="panel"><SectionTitle eyebrow="Contabilidad" title="Plan de cuentas" /><form className="grid-form" onSubmit={create}><input required placeholder="Código" value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })} /><input required placeholder="Nombre" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /><select value={form.account_type} onChange={(e) => setForm({ ...form, account_type: e.target.value })}>{['asset','liability','equity','income','expense'].map((type) => <option key={type} value={type}>{type}</option>)}</select><button className="primary">Crear cuenta</button></form><div className="table"><div className="tr th"><span>Código</span><span>Cuenta</span><span>Tipo</span><span>Saldo</span></div>{trial.map((row) => <div className="tr" key={row.account_id}><span>{row.code}</span><strong>{row.name}</strong><span>{row.account_type}</span><b>{money.format(Number(row.balance))}</b></div>)}</div><small className="muted">{accounts.length} cuentas registradas. Los reportes consideran únicamente asientos publicados.</small></section></div>;
}

export function FinanceView() {
  const [receivables, setReceivables] = useState([]);
  const [payables, setPayables] = useState([]);
  const [banks, setBanks] = useState([]);
  const [unmatched, setUnmatched] = useState([]);
  const [error, setError] = useState('');
  const load = async () => {
    setError('');
    try {
      const [r, p, b, u] = await Promise.all([
        api.request('/finance/receivables'), api.request('/finance/payables'),
        api.request('/finance/banking/accounts'), api.request('/finance/reconciliation/unmatched'),
      ]);
      setReceivables(r); setPayables(p); setBanks(b); setUnmatched(u);
    } catch (err) { setError(err.message); }
  };
  useEffect(() => { load(); }, []);
  const ar = useMemo(() => receivables.reduce((sum, row) => sum + Number(row.balance), 0), [receivables]);
  const ap = useMemo(() => payables.reduce((sum, row) => sum + Number(row.balance), 0), [payables]);
  return <div className="stack"><ErrorBox error={error} /><div className="dashboard"><article><small>Cuentas por cobrar</small><strong>{money.format(ar)}</strong><span>{receivables.filter((r) => r.status !== 'paid').length} abiertas</span></article><article><small>Cuentas por pagar</small><strong>{money.format(ap)}</strong><span>{payables.filter((r) => r.status !== 'paid').length} abiertas</span></article><article><small>Cuentas bancarias</small><strong>{banks.length}</strong><span>registradas</span></article><article><small>Sin conciliar</small><strong>{unmatched.length}</strong><span>movimientos bancarios</span></article></div><div className="two-panels"><section className="panel"><SectionTitle eyebrow="CxC" title="Saldos de clientes" /><div className="product-list">{receivables.map((row) => <div key={row.id}><span><strong>{row.reference}</strong><small>{row.status} · vence {row.due_date || 'sin fecha'}</small></span><b>{money.format(Number(row.balance))}</b></div>)}</div></section><section className="panel"><SectionTitle eyebrow="CxP" title="Saldos de proveedores" /><div className="product-list">{payables.map((row) => <div key={row.id}><span><strong>{row.reference}</strong><small>{row.status} · vence {row.due_date || 'sin fecha'}</small></span><b>{money.format(Number(row.balance))}</b></div>)}</div></section></div><section className="panel"><SectionTitle eyebrow="Bancos" title="Pendientes de conciliación" action={<button className="link" onClick={load}>Actualizar</button>} /><div className="table"><div className="tr th"><span>Fecha</span><span>Descripción</span><span>Referencia</span><span>Monto</span></div>{unmatched.map((row) => <div className="tr" key={row.id}><span>{row.transaction_date}</span><strong>{row.description || 'Sin descripción'}</strong><span>{row.external_reference}</span><b>{money.format(Number(row.amount))}</b></div>)}</div></section></div>;
}

export function CrmView() {
  const [leads, setLeads] = useState([]);
  const [form, setForm] = useState({ full_name: '', email: '', phone: '', source: 'manual', notes: '' });
  const [error, setError] = useState('');
  const load = () => api.request('/crm/leads').then(setLeads).catch((err) => setError(err.message));
  useEffect(() => { load(); }, []);
  const save = async (event) => { event.preventDefault(); setError(''); try { await api.request('/crm/leads', { method: 'POST', body: JSON.stringify(form) }); setForm({ full_name: '', email: '', phone: '', source: 'manual', notes: '' }); await load(); } catch (err) { setError(err.message); } };
  return <section className="panel"><SectionTitle eyebrow="CRM" title="Prospectos y oportunidades" /><ErrorBox error={error} /><form className="grid-form" onSubmit={save}><input required placeholder="Nombre" value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} /><input type="email" placeholder="Correo" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /><input placeholder="Teléfono" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} /><input placeholder="Origen" value={form.source} onChange={(e) => setForm({ ...form, source: e.target.value })} /><button className="primary">Crear lead</button></form><div className="product-list">{leads.map((lead) => <div key={lead.id}><span><strong>{lead.full_name}</strong><small>{lead.source} · {lead.email || lead.phone || 'sin contacto'}</small></span><b>{lead.status}</b></div>)}</div></section>;
}

export function PeopleView() {
  const [employees, setEmployees] = useState([]);
  const [branches, setBranches] = useState([]);
  const [form, setForm] = useState({ employee_code: '', full_name: '', identity_number: '', position: '', department: 'General', hire_date: new Date().toISOString().slice(0, 10), base_salary: '0', branch_id: null, user_id: null });
  const [error, setError] = useState('');
  const load = async () => { try { const [e, b] = await Promise.all([api.request('/hr/employees'), api.request('/admin/branches')]); setEmployees(e); setBranches(b); } catch (err) { setError(err.message); } };
  useEffect(() => { load(); }, []);
  const save = async (event) => { event.preventDefault(); setError(''); try { await api.request('/hr/employees', { method: 'POST', body: JSON.stringify({ ...form, branch_id: form.branch_id || null }) }); setForm((current) => ({ ...current, employee_code: '', full_name: '', identity_number: '', position: '', base_salary: '0' })); await load(); } catch (err) { setError(err.message); } };
  return <section className="panel"><SectionTitle eyebrow="Personas" title="Recursos humanos" /><ErrorBox error={error} /><form className="grid-form" onSubmit={save}><input required placeholder="Código empleado" value={form.employee_code} onChange={(e) => setForm({ ...form, employee_code: e.target.value })} /><input required placeholder="Nombre completo" value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} /><input required placeholder="Cargo" value={form.position} onChange={(e) => setForm({ ...form, position: e.target.value })} /><input placeholder="Departamento" value={form.department} onChange={(e) => setForm({ ...form, department: e.target.value })} /><input type="date" value={form.hire_date} onChange={(e) => setForm({ ...form, hire_date: e.target.value })} /><input type="number" min="0" step="0.01" value={form.base_salary} onChange={(e) => setForm({ ...form, base_salary: e.target.value })} /><select value={form.branch_id || ''} onChange={(e) => setForm({ ...form, branch_id: e.target.value || null })}><option value="">Sin sucursal fija</option>{branches.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}</select><button className="primary">Crear empleado</button></form><div className="product-list">{employees.map((row) => <div key={row.id}><span><strong>{row.full_name}</strong><small>{row.employee_code} · {row.position} · {row.department}</small></span><b>{money.format(Number(row.base_salary))}</b></div>)}</div></section>;
}

export function AutomationView() {
  const [workflows, setWorkflows] = useState([]);
  const [form, setForm] = useState({ key: '', name: '', event_key: '', topic: '' });
  const [dispatch, setDispatch] = useState({ event_key: '', payload: '{}' });
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const load = () => api.request('/workflows').then(setWorkflows).catch((err) => setError(err.message));
  useEffect(() => { load(); }, []);
  const create = async (event) => { event.preventDefault(); setError(''); try { await api.request('/workflows', { method: 'POST', body: JSON.stringify({ key: form.key, name: form.name, event_key: form.event_key, condition: {}, action: { type: 'outbox', topic: form.topic, payload: {} } }) }); setForm({ key: '', name: '', event_key: '', topic: '' }); await load(); } catch (err) { setError(err.message); } };
  const run = async () => { setError(''); try { const payload = JSON.parse(dispatch.payload || '{}'); const result = await api.request('/workflows/dispatch', { method: 'POST', body: JSON.stringify({ event_key: dispatch.event_key, payload }) }); setMessage(`${result.runs.length} ejecución(es) encolada(s)`); } catch (err) { setError(err.message); } };
  return <div className="two-panels"><section className="panel"><SectionTitle eyebrow="Automatización" title="Workflows" /><ErrorBox error={error} /><form className="stack" onSubmit={create}><input required placeholder="Clave" value={form.key} onChange={(e) => setForm({ ...form, key: e.target.value })} /><input required placeholder="Nombre" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /><input required placeholder="Evento, ej. order.created" value={form.event_key} onChange={(e) => setForm({ ...form, event_key: e.target.value })} /><input required placeholder="Topic de salida" value={form.topic} onChange={(e) => setForm({ ...form, topic: e.target.value })} /><button className="primary">Crear workflow</button></form><div className="product-list">{workflows.map((row) => <div key={row.id}><span><strong>{row.name}</strong><small>{row.event_key}</small></span><b>{row.active ? 'activo' : 'inactivo'}</b></div>)}</div></section><section className="panel"><SectionTitle eyebrow="Prueba controlada" title="Despachar evento" /><div className="stack"><input placeholder="event_key" value={dispatch.event_key} onChange={(e) => setDispatch({ ...dispatch, event_key: e.target.value })} /><textarea rows="8" value={dispatch.payload} onChange={(e) => setDispatch({ ...dispatch, payload: e.target.value })} /><button className="primary" disabled={!dispatch.event_key} onClick={run}>Encolar evento</button>{message && <div className="notice">{message}</div>}<small className="muted">El worker solo marca entregado cuando el destino configurado confirma HTTP 2xx.</small></div></section></div>;
}
