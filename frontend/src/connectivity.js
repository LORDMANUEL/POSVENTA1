export function setConnectivity(online) {
  if (typeof document !== 'undefined') {
    document.documentElement.dataset.mzConnectivity = online ? 'online' : 'offline';
  }
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent('mz-connectivity', { detail: { online } }));
  }
}

export function installConnectivityIndicator() {
  if (typeof document === 'undefined' || typeof window === 'undefined') return;
  let banner = document.getElementById('mz-connectivity-banner');
  if (!banner) {
    banner = document.createElement('div');
    banner.id = 'mz-connectivity-banner';
    banner.setAttribute('role', 'status');
    banner.setAttribute('aria-live', 'polite');
    Object.assign(banner.style, {
      position: 'fixed', top: '0', left: '0', right: '0', zIndex: '99999',
      padding: '8px 12px', textAlign: 'center', fontFamily: 'system-ui, sans-serif',
      fontSize: '13px', fontWeight: '700', background: '#222', color: '#fff',
      transform: 'translateY(-100%)', transition: 'transform .2s ease',
    });
    banner.textContent = 'Modo sin conexión · las ventas quedan pendientes y se validarán al sincronizar.';
    document.body.appendChild(banner);
  }
  const render = (online) => {
    document.documentElement.dataset.mzConnectivity = online ? 'online' : 'offline';
    banner.style.transform = online ? 'translateY(-100%)' : 'translateY(0)';
  };
  render(navigator.onLine !== false);
  window.addEventListener('online', () => render(true));
  window.addEventListener('offline', () => render(false));
  window.addEventListener('mz-connectivity', (event) => render(Boolean(event.detail?.online)));
}
