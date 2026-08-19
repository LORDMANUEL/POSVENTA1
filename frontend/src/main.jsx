import React from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';
import Storefront from './Storefront';
import './styles.css';
import './operations.css';
import './storefront.css';

const params = new URLSearchParams(window.location.search);
const isRoleClient = params.has('mode');
const isAdminRoute = window.location.pathname.startsWith('/admin');
const RootComponent = isRoleClient || isAdminRoute ? App : Storefront;

createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <RootComponent />
  </React.StrictMode>,
);
