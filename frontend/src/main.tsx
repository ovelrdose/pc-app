import '@mantine/core/styles.css';
import '@mantine/notifications/styles.css';
import '@mantine/charts/styles.css';

// Настройка Monaco (воркеры из node_modules, без CDN) — до первого рендера редакторов.
import './lib/monaco';

import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';

import { App } from './app/App';

const root = document.getElementById('root');
if (!root) {
  throw new Error('Не найден корневой элемент #root');
}

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
