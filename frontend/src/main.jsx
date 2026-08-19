import React from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';
import Storefront from './Storefront';
import { registerServiceWorker } from './registerServiceWorker';
import './styles.css';
import './operations.css';
import './module-settings.css';
import './storefront.css';
import './storefront-media.css';

const params = new URLSearchParams(window.location.search);
const isRoleClient = params.has('mode');
const isAdminRoute = window.location.pathname.startsWith('/admin');
const RootComponent = isRoleClient || isAdminRoute ? App : Storefront;

registerServiceWorker();

createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <RootComponent />
  </React.StrictMode>,
);
