import { useState } from 'react';
import { api } from './api';

function UploadCard({ title, help, accept, previewPath, commitPath, onCommitted }) {
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);

  const send = async (path) => {
    if (!file) return null;
    const form = new FormData();
    form.append('file', file);
    return api.request(path, { method: 'POST', body: form });
  };

  const inspect = async () => {
    setBusy(true); setMessage(''); setPreview(null);
    try {
      const result = await send(previewPath);
      setPreview(result);
      setMessage(result.valid ? 'Archivo válido para importar.' : 'Revise los errores antes de continuar.');
    } catch (error) {
      setMessage(error.message);
    } finally { setBusy(false); }
  };

  const commit = async () => {
    if (!preview?.valid) return;
    setBusy(true); setMessage('');
    try {
      const result = await send(commitPath);
      setMessage(`Importación completada: ${result.created ?? result.image_count ?? 0} elemento(s).`);
      setPreview(null); setFile(null);
      if (onCommitted) await onCommitted();
    } catch (error) {
      setMessage(error.message);
    } finally { setBusy(false); }
  };

  const rows = preview?.preview || [];
  const errors = preview?.errors || [];
  return <section className="panel">
    <div className="panel-title"><div><p className="eyebrow">Carga controlada</p><h2>{title}</h2></div></div>
    <p className="muted">{help}</p>
    <div className="stack">
      <input type="file" accept={accept} onChange={(event) => { setFile(event.target.files?.[0] || null); setPreview(null); setMessage(''); }} />
      <div className="inventory-action">
        <button className="primary" disabled={!file || busy} onClick={inspect}>{busy ? 'Validando…' : 'Validar / preview'}</button>
        <button className="primary" disabled={!preview?.valid || busy} onClick={commit}>Importar definitivamente</button>
      </div>
    </div>
    {message && <div className={preview && !preview.valid ? 'error' : 'notice'}>{message}</div>}
    {errors.length > 0 && <div className="product-list">{errors.slice(0, 30).map((error, index) => <div key={`${error.row || index}-${index}`}><span><strong>Fila {error.row || '—'}</strong><small>{error.sku || error.filename || ''}</small></span><b>{String(error.error)}</b></div>)}</div>}
    {rows.length > 0 && <div className="product-list">{rows.slice(0, 30).map((row, index) => <div key={`${row.sku || row.name || index}-${index}`}><span><strong>{row.sku || row.name || `Elemento ${index + 1}`}</strong><small>{row.filename || row.category || ''}</small></span><b>{row.analysis ? `${row.analysis.width}×${row.analysis.height}` : row.sale_price || ''}</b></div>)}</div>}
  </section>;
}

export default function CatalogImportTools({ onCatalogCommitted }) {
  return <div className="two-panels">
    <UploadCard
      title="Importar productos CSV"
      help="CSV UTF-8. Columnas mínimas: sku, name, sale_price. El preview detecta duplicados y errores antes de escribir datos. El commit es atómico."
      accept=".csv,text/csv"
      previewPath="/catalog/import/preview"
      commitPath="/catalog/import/commit"
      onCommitted={onCatalogCommitted}
    />
    <UploadCard
      title="Importar fotografías ZIP"
      help="ZIP con manifest.csv en la raíz. Columnas: sku, filename, position, primary. Se valida seguridad del ZIP, máximo 5 fotos, resolución y formato; luego se normaliza a WebP."
      accept=".zip,application/zip"
      previewPath="/catalog/media-import/preview"
      commitPath="/catalog/media-import/commit"
      onCommitted={onCatalogCommitted}
    />
  </div>;
}
