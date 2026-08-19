import { useEffect, useMemo, useState } from 'react';
import { api } from './api';

export default function ModuleSettings() {
  const [modules, setModules] = useState([]);
  const [busy, setBusy] = useState('');
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const load = async () => {
    try { setModules(await api.request('/admin/modules')); setError(''); } catch (err) { setError(err.message); }
  };
  useEffect(() => { load(); }, []);
  const grouped = useMemo(() => modules.reduce((acc, item) => {
    (acc[item.category] ||= []).push(item); return acc;
  }, {}), [modules]);
  const toggle = async (item) => {
    if (item.core) return;
    setBusy(item.key); setError(''); setMessage('');
    try {
      await api.request(`/admin/modules/${item.key}?enabled=${String(!item.enabled)}`, { method: 'PUT' });
      await load();
    } catch (err) { setError(err.message); } finally { setBusy(''); }
  };
  const restoreFull = async () => {
    setBusy('full'); setError(''); setMessage('');
    try {
      const result = await api.request('/admin/modules/profiles/full-internal/enable', { method: 'POST' });
      setMessage(`Perfil ERP interno restaurado: ${result.enabled.length} módulos. Los módulos con certificación externa siguen separados.`);
      await load();
    } catch (err) { setError(err.message); } finally { setBusy(''); }
  };
  return <div className="stack"><section className="panel"><div className="panel-title"><div><p className="eyebrow">Arquitectura modular</p><h2>Módulos del ERP</h2></div><button className="primary" disabled={Boolean(busy)} onClick={restoreFull}>{busy === 'full' ? 'Restaurando…' : 'Restaurar perfil ERP interno'}</button></div><p className="muted">La instalación estable inicia con el ERP interno validado activo. Puede desactivar módulos opcionales respetando sus dependencias. Fiscal, pagos externos, música física y experiencias visuales permanecen bloqueados hasta su certificación correspondiente.</p>{message && <div className="notice">{message}</div>}{error && <div className="error">{error}</div>}</section>{Object.entries(grouped).map(([category, rows]) => <section className="panel" key={category}><div className="panel-title"><div><p className="eyebrow">{category}</p><h2>{rows.length} módulos</h2></div></div><div className="module-grid">{rows.map((item) => <article className="module-card" key={item.key}><div><span className={`badge ${item.enabled ? 'delivered' : 'pending'}`}>{item.enabled ? 'activo' : 'inactivo'}</span><h3>{item.name}</h3><small>{item.key}</small></div><p>{item.dependencies.length ? `Depende de: ${item.dependencies.join(', ')}` : 'Sin dependencias adicionales'}</p>{item.external_gate && <div className="notice">{item.external_gate}</div>}<button className={item.enabled ? 'danger' : 'primary'} disabled={item.core || busy === item.key || Boolean(item.external_gate && !item.enabled)} onClick={() => toggle(item)}>{item.core ? 'Núcleo' : item.external_gate && !item.enabled ? 'Requiere certificación' : item.enabled ? 'Desactivar' : 'Activar'}</button></article>)}</div></section>)}</div>;
}
