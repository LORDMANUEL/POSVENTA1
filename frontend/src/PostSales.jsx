import { useEffect, useState } from 'react';
import { api } from './api';

const money = new Intl.NumberFormat('es-HN', { style: 'currency', currency: 'HNL' });

export default function ReturnsView({ refreshInventory }) {
  const [sales, setSales] = useState([]);
  const [returns, setReturns] = useState([]);
  const [saleId, setSaleId] = useState('');
  const [detail, setDetail] = useState(null);
  const [quantities, setQuantities] = useState({});
  const [reason, setReason] = useState('Cambio solicitado por cliente');
  const [returnKey, setReturnKey] = useState(() => crypto.randomUUID());
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const loadLists = async () => {
    const [saleRows, returnRows] = await Promise.all([
      api.request('/post-sales/sales?limit=100'),
      api.request('/post-sales/returns'),
    ]);
    setSales(saleRows);
    setReturns(returnRows);
    if (!saleId && saleRows[0]) setSaleId(saleRows[0].id);
  };

  const loadDetail = async (id) => {
    if (!id) { setDetail(null); setQuantities({}); return; }
    const row = await api.request(`/post-sales/sales/${id}`);
    setDetail(row);
    setQuantities(Object.fromEntries(row.lines.map((line) => [line.sale_line_id, '0'])));
  };

  useEffect(() => { loadLists().catch((err) => setError(err.message)); }, []);
  useEffect(() => { if (saleId) loadDetail(saleId).catch((err) => setError(err.message)); }, [saleId]);

  const submit = async (event) => {
    event.preventDefault();
    setMessage(''); setError('');
    const lines = Object.entries(quantities)
      .filter(([, value]) => Number(value) > 0)
      .map(([sale_line_id, quantity]) => ({ sale_line_id, quantity }));
    if (!saleId || lines.length === 0) { setError('Seleccione al menos una cantidad para devolver.'); return; }
    setBusy(true);
    try {
      const result = await api.request('/post-sales/returns', {
        method: 'POST',
        headers: { 'Idempotency-Key': returnKey },
        body: JSON.stringify({ sale_id: saleId, reason, lines }),
      });
      setReturnKey(crypto.randomUUID());
      setMessage(`Devolución registrada por ${money.format(Number(result.total))}. Reembolso: ${result.refund.status}.`);
      await Promise.all([loadDetail(saleId), loadLists(), refreshInventory?.()]);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return <div className="two-panels">
    <section className="panel">
      <div className="panel-title"><div><p className="eyebrow">Postventa</p><h2>Devolución de venta</h2></div></div>
      <label>Venta
        <select value={saleId} onChange={(event) => setSaleId(event.target.value)}>
          <option value="">Seleccione una venta…</option>
          {sales.map((sale) => <option key={sale.id} value={sale.id}>{sale.id.slice(0, 8)} · {money.format(Number(sale.total))} · {sale.payment_method}</option>)}
        </select>
      </label>
      {detail && <form className="stack" onSubmit={submit}>
        <div className="notice">Venta {detail.id.slice(0, 8)} · {money.format(Number(detail.total))} · {detail.payment_method}</div>
        <div className="product-list">
          {detail.lines.map((line) => <div key={line.sale_line_id}>
            <span><strong>{line.name}</strong><small>{line.sku} · vendido {line.quantity_sold} · ya devuelto {line.quantity_returned}</small></span>
            <label>Devolver
              <input
                aria-label={`Devolver ${line.name}`}
                type="number"
                min="0"
                max={line.quantity_returnable}
                step="0.001"
                disabled={Number(line.quantity_returnable) <= 0}
                value={quantities[line.sale_line_id] ?? '0'}
                onChange={(event) => setQuantities((current) => ({ ...current, [line.sale_line_id]: event.target.value }))}
              />
              <small>máx. {line.quantity_returnable}</small>
            </label>
          </div>)}
        </div>
        <label>Motivo<input required minLength="3" value={reason} onChange={(event) => setReason(event.target.value)} /></label>
        <button className="primary" disabled={busy}>{busy ? 'Registrando…' : 'Registrar devolución'}</button>
      </form>}
      {message && <div className="notice">{message}</div>}
      {error && <div className="error">{error}</div>}
    </section>
    <section className="panel">
      <div className="panel-title"><div><p className="eyebrow">Auditoría</p><h2>Devoluciones recientes</h2></div></div>
      <div className="product-list">
        {returns.length === 0 && <p className="muted">Aún no hay devoluciones.</p>}
        {returns.map((row) => <div key={row.id}><span><strong>{row.reason}</strong><small>Venta {row.sale_id.slice(0, 8)} · devolución {row.id.slice(0, 8)}</small></span><b>{money.format(Number(row.total))}</b></div>)}
      </div>
    </section>
  </div>;
}
