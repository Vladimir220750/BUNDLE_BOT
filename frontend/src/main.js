import './app.css';
import App from './App.svelte';

const path = window.location.pathname;

const app = new App({
  target: document.getElementById('app'),
  props: {
    basePath: path.startsWith('/raydium') ? 'raydium' : 'pumpfun'
  }
});

export default app;
