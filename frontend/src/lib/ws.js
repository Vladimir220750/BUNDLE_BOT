import { writable } from 'svelte/store';
import { wallets } from './api.js';

export const stats = writable({ liq: 0, mcap: 0 });

let ws;
let pingId;

export function connectDataWS() {
  ws = new WebSocket("/pumpfun/ws/data/");

  ws.addEventListener('open', () => {
    ws.send(JSON.stringify({ type: 'ping' }));
    pingId = setInterval(() => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'ping' }));
      }
    }, 5000);
  });

  ws.addEventListener('message', (e) => {
    try {
      const data = JSON.parse(e.data);
      if (data.type === 'pong') return;
      if (data.type === 'update') handleUpdate(data.payload);
    } catch (err) {
      console.error('WS message error', err);
    }
  });

  ws.addEventListener('close', () => {
    if (pingId) clearInterval(pingId);
  });

  return ws;
}

function handleUpdate(payload) {
  if (!payload) return;
  if (payload.curve_state) {
    stats.update(s => ({ ...s, ...payload.curve_state }));
  }
  if (payload.lam) {
    wallets.update(list => list.map(w => {
      if (payload.lam[w.name] !== undefined) {
        w.sol_balance = payload.lam[w.name];
      }
      return w;
    }));
  }
  if (payload.token) {
    wallets.update(list => list.map(w => {
      if (payload.token[w.name] !== undefined) {
        w.token_balance = payload.token[w.name];
      }
      return w;
    }));
  }
}
export function refresh() {
  ws.send(JSON.stringify({ type: 'command', command: 'refresh'}));
}

export function connectRaydiumWS(onUpdate) {
  let pingId = null;
  let rws = new WebSocket('/raydium/ws/data/');

  rws.addEventListener('open', () => {
    rws.send(JSON.stringify({ type: 'ping' }));
    pingId = setInterval(() => {
      if (rws.readyState === WebSocket.OPEN) {
        rws.send(JSON.stringify({ type: 'ping' }));
      }
    }, 5000);
  });

  rws.addEventListener('message', (e) => {
    try {
      const data = JSON.parse(e.data);
      if (!data) return;

      if (data.type === 'pong') return;
      if (data.type === 'update' && onUpdate) {
        onUpdate(data.payload);
      }
    } catch (err) {
      console.error('WS message error', err);
    }
  });

  rws.addEventListener('close', () => {
    if (pingId) clearInterval(pingId);
    pingId = null;
  });

  return rws;
}
