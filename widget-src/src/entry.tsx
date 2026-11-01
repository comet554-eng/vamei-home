import { createRoot } from 'react-dom/client';
import HafillerBot from './components/hafiller-bot';

// Keep the widget styles independent of the host dashboard styles.
if (!document.querySelector('[data-hafiller-widget]')) {
  const host = document.createElement('div');
  host.dataset.hafillerWidget = '';
  document.body.append(host);
  const shadow = host.attachShadow({ mode: 'open' });
  const stylesheet = document.createElement('link');
  stylesheet.rel = 'stylesheet';
  stylesheet.href = new URL('./hafiller-widget.css', import.meta.url).href;
  const mount = document.createElement('div');
  shadow.append(stylesheet, mount);
  createRoot(mount).render(<HafillerBot />);
}
