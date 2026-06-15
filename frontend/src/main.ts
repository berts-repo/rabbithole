import './styles/global.css';
import { mount } from 'svelte';
import App from './app.svelte';

const target = document.getElementById('app');
if (!target) {
  throw new Error('mount target #app not found');
}

async function bootstrap() {
  // In dev, GET / is served by Vite — not the backend — so the session
  // cookie never lands. /__session proxies to the backend's root handler
  // which does mint the cookie. In production this is a no-op because
  // the page is served by the backend in the first place.
  if (import.meta.env.DEV) {
    try {
      await fetch('/__session', { credentials: 'same-origin' });
    } catch {
      // If the backend is down the mount still proceeds; api.ts calls
      // will just fail with their own error message.
    }
  }
  mount(App, { target: target! });
}

void bootstrap();
