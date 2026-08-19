import { useEffect, useMemo, useState } from 'react';

const API_URL = import.meta.env.VITE_API_URL || '/api';
const STORE_SLUG = 'mily-zebra';
const money = new Intl.NumberFormat('es-HN', { style: 'currency', currency: 'HNL' });

async function publicRequest(path, options = {}) {
  const headers = new Headers(options.headers || {});
  if (options.body) headers.set('Content-Type', 'application/json');
  const response = await fetch(`${API_URL}${path}`, { ...options, headers });
  const text = await response.text();
  let body = null;
  try { body = text ? JSON.parse(text) : null; } catch { body = text; }
  if (!response.ok) throw new Error(body?.detail || body || `HTTP ${response.status}`);
  return body;
}

function CartDrawer({ cart, onClose, onQty, onCheckout }) {
  const total = cart.reduce((sum, item) => sum + Number(item.sale_price) * item.qty, 0);
  return <div className="sf-overlay" onClick={onClose}><aside className="sf-cart" onClick={(e) => e.stopPropagation()}><header><div><small>Tu selección</small><h2>Bolsa Mily</h2></div><button onClick={onClose}>×</button></header><div className="sf-cart-lines">{cart.length === 0 && <p className="sf-muted">Tu bolsa está vacía.</p>}{cart.map((item) => <div className="sf-cart-line" key={item.id}><div><strong>{item.name}</strong><small>{item.size || 'Talla única'} · {item.color || 'Color surtido'}</small></div><div className="sf-qty"><button onClick={() => onQty(item.id, -1)}>−</button><span>{item.qty}</span><button onClick={() => onQty(item.id, 1)}>+</button></div><b>{money.format(Number(item.sale_price) * item.qty)}</b></div>)}</div><footer><div><span>Total</span><strong>{money.format(total)}</strong></div><button className="sf-primary" disabled={!cart.length} onClick={onCheckout}>Continuar compra</button></footer></aside></div>;
}

function Checkout({ cart, onBack, onCompleted }) {
  const [form, setForm] = useState({ full_name: '', email: '', phone: '', payment_method: 'manual_transfer', fulfillment_method: 'pickup', delivery_address: '' });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const submit = async (event) => {
    event.preventDefault(); setBusy(true); setError('');
    try {
      const order = await publicRequest(`/store/${STORE_SLUG}/checkout`, {
        method: 'POST',
        headers: { 'Idempotency-Key': crypto.randomUUID() },
        body: JSON.stringify({ ...form, delivery_address: form.fulfillment_method === 'delivery' ? form.delivery_address : null, lines: cart.map((item) => ({ product_id: item.id, quantity: item.qty })) }),
      });
      onCompleted(order);
    } catch (err) { setError(err.message); } finally { setBusy(false); }
  };
  return <main className="sf-checkout"><button className="sf-back" onClick={onBack}>← Volver a la tienda</button><div className="sf-checkout-grid"><section><p className="sf-kicker">Compra segura</p><h1>Finaliza tu pedido</h1><p>Tu inventario se reserva durante la ventana de checkout para evitar vender la misma pieza dos veces.</p><form onSubmit={submit}><label>Nombre completo<input required value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} /></label><label>WhatsApp / teléfono<input value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} /></label><label>Correo<input type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></label><div className="sf-radio-row"><label><input type="radio" name="fulfillment" checked={form.fulfillment_method === 'pickup'} onChange={() => setForm({ ...form, fulfillment_method: 'pickup' })} /> Recoger en tienda</label><label><input type="radio" name="fulfillment" checked={form.fulfillment_method === 'delivery'} onChange={() => setForm({ ...form, fulfillment_method: 'delivery' })} /> Entrega</label></div>{form.fulfillment_method === 'delivery' && <label>Dirección de entrega<textarea required value={form.delivery_address} onChange={(e) => setForm({ ...form, delivery_address: e.target.value })} /></label>}<label>Método de pago<select value={form.payment_method} onChange={(e) => setForm({ ...form, payment_method: e.target.value })}><option value="manual_transfer">Transferencia bancaria</option><option value="cash_on_delivery">Pago contra entrega</option></select></label>{error && <div className="sf-error">{error}</div>}<button className="sf-primary" disabled={busy}>{busy ? 'Creando pedido…' : 'Confirmar pedido'}</button></form></section><aside className="sf-summary"><p className="sf-kicker">Resumen</p>{cart.map((item) => <div key={item.id}><span>{item.qty} × {item.name}</span><strong>{money.format(item.qty * Number(item.sale_price))}</strong></div>)}<footer><span>Total</span><strong>{money.format(cart.reduce((sum, item) => sum + item.qty * Number(item.sale_price), 0))}</strong></footer></aside></div></main>;
}

function Confirmation({ order, onHome }) {
  return <main className="sf-confirm"><div className="sf-confirm-mark">✓</div><p className="sf-kicker">Pedido recibido</p><h1>Gracias por elegir Mily Zebra</h1><p>Pedido <strong>{order.id.slice(0, 8)}</strong> · estado <strong>{order.status.replaceAll('_', ' ')}</strong></p><div className="sf-confirm-card"><span>Total</span><strong>{money.format(Number(order.total))}</strong><small>Guarda este código de seguimiento. Se almacena únicamente en este navegador.</small><code>{order.tracking_token}</code></div><button className="sf-primary" onClick={onHome}>Volver al catálogo</button></main>;
}

export default function Storefront() {
  const [catalog, setCatalog] = useState({ store: { name: 'Mily Zebra' }, products: [] });
  const [cart, setCart] = useState(() => { try { return JSON.parse(localStorage.getItem('mz_store_cart') || '[]'); } catch { return []; } });
  const [category, setCategory] = useState('Todos');
  const [search, setSearch] = useState('');
  const [cartOpen, setCartOpen] = useState(false);
  const [screen, setScreen] = useState('store');
  const [order, setOrder] = useState(null);
  const [error, setError] = useState('');
  useEffect(() => { publicRequest(`/store/${STORE_SLUG}/catalog`).then(setCatalog).catch((err) => setError(err.message)); }, []);
  useEffect(() => { localStorage.setItem('mz_store_cart', JSON.stringify(cart)); }, [cart]);
  const categories = useMemo(() => ['Todos', ...new Set(catalog.products.map((p) => p.category))], [catalog]);
  const filtered = useMemo(() => catalog.products.filter((p) => (category === 'Todos' || p.category === category) && `${p.name} ${p.description} ${p.sku}`.toLowerCase().includes(search.toLowerCase())), [catalog, category, search]);
  const add = (product) => { setCart((items) => { const found = items.find((x) => x.id === product.id); return found ? items.map((x) => x.id === product.id ? { ...x, qty: x.qty + 1 } : x) : [...items, { ...product, qty: 1 }]; }); setCartOpen(true); };
  const qty = (id, delta) => setCart((items) => items.map((x) => x.id === id ? { ...x, qty: x.qty + delta } : x).filter((x) => x.qty > 0));
  const completed = (created) => { setOrder(created); localStorage.setItem(`mz_tracking_${created.id}`, created.tracking_token); setCart([]); setScreen('confirmation'); };
  if (screen === 'checkout') return <Checkout cart={cart} onBack={() => setScreen('store')} onCompleted={completed} />;
  if (screen === 'confirmation') return <Confirmation order={order} onHome={() => { setOrder(null); setScreen('store'); }} />;
  return <div className="sf-page"><header className="sf-nav"><a className="sf-logo" href="/"><span>MZ</span><b>Mily Zebra</b></a><nav><a href="#coleccion">Colección</a><a href="#universo">Universo Mily</a><a href="/admin">Equipo</a></nav><button className="sf-bag" onClick={() => setCartOpen(true)}>Bolsa <span>{cart.reduce((sum, item) => sum + item.qty, 0)}</span></button></header><main><section className="sf-hero"><div className="sf-zebra-lines" /><div className="sf-hero-copy"><p className="sf-kicker">Mily Zebra · Roatán</p><h1>Tu estilo.<br/><em>Tu momento.</em></h1><p>Moda cómoda, femenina y fresca para sentirte segura siendo tú.</p><a className="sf-primary" href="#coleccion">Ver colección</a></div><div className="sf-hero-art"><div className="sf-heart">♥</div><div className="sf-model-card"><span>MILY</span><strong>ZEBRA</strong><small>Island · Pink · Everyday</small></div></div></section><section className="sf-marquee"><span>MILY BASICS ✦ PINK VIBES ✦ ISLAND MOOD ✦ MILY DETAILS ✦</span><span>MILY BASICS ✦ PINK VIBES ✦ ISLAND MOOD ✦ MILY DETAILS ✦</span></section><section className="sf-collection" id="coleccion"><div className="sf-section-head"><div><p className="sf-kicker">Encuentra tu favorito</p><h2>La colección Mily</h2></div><input placeholder="Buscar prendas o detalles…" value={search} onChange={(e) => setSearch(e.target.value)} /></div><div className="sf-filters">{categories.map((item) => <button className={category === item ? 'active' : ''} onClick={() => setCategory(item)} key={item}>{item}</button>)}</div>{error && <div className="sf-error">{error}</div>}<div className="sf-products">{filtered.map((product, index) => <article className="sf-product" key={product.id}><div className={`sf-product-image tone-${index % 4}`}><span>{product.category}</span><strong>{product.name.slice(0, 1)}</strong></div><div className="sf-product-info"><small>{product.sku} · {product.size || 'Talla flexible'}</small><h3>{product.name}</h3><p>{product.description || `${product.color || 'Estilo Mily'} para combinar a tu manera.`}</p><footer><b>{money.format(Number(product.sale_price))}</b><button onClick={() => add(product)}>Agregar +</button></footer></div></article>)}</div></section><section className="sf-universe" id="universo"><p className="sf-kicker">Universo Mily</p><h2>Segura. Cómoda. Única.</h2><div><article><span>01</span><h3>Mily Basics</h3><p>Prendas para todos los días: fáciles de combinar, cómodas y con personalidad.</p></article><article><span>02</span><h3>Island Mood</h3><p>Roatán inspira una línea fresca, luminosa y lista para el clima tropical.</p></article><article><span>03</span><h3>Mily Details</h3><p>Accesorios y belleza para terminar el look sin complicarlo.</p></article></div></section></main><footer className="sf-footer"><div className="sf-logo"><span>MZ</span><b>Mily Zebra</b></div><p>Roatán, Islas de la Bahía · Honduras</p><p>© 2026 Mily Zebra</p></footer>{cartOpen && <CartDrawer cart={cart} onClose={() => setCartOpen(false)} onQty={qty} onCheckout={() => { setCartOpen(false); setScreen('checkout'); }} />}</div>;
}
