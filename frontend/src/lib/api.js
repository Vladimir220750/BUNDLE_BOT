/* ---------- src/lib/api.js ---------- */
import { writable } from 'svelte/store';

// ---------- STORES ----------
export const wallets = writable([]);        // список кошельков
export const token = writable(null);      // метаданные токена
export const step = writable('main');    // 'main' | 'control'

// ---------- HELPERS ----------
const JSON_HEADERS = { 'Content-Type': 'application/json' };

async function handle(resPromise) {
  const res = await resPromise;
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status} — ${text}`);
  }
  return res.status === 204 ? null : res.json();
}

// ---------- WALLETS ----------
export async function loadWallets() {
  const data = await handle(fetch('/pumpfun/api/wallets/list/'));
  wallets.set(data);
}

export async function archiveWallet(payload) {
  const data = await handle(fetch('/pumpfun/api/wallets/archive/', {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify({ "wallet_pub": payload })
  }));
  wallets.set(data);
}

export async function reloadWallets() {
  await handle(fetch('/pumpfun/api/wallets/reload/'));
  await loadWallets()
}

export async function createWallets({ dev, fund, group1, group2 }) {
  await handle(fetch('/pumpfun/api/wallets/create/', {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify({
      dev,
      fund,
      group1: Number(group1) || 0,
      group2: Number(group2) || 0
    })
  }));
  await reloadWallets();
}

export async function getPrivateKey(pubkey) {
  const { base58 } = await handle(fetch(`/pumpfun/api/wallets/private_key/${pubkey}/`));
  return base58;
}

// ---------- FUNDS ----------
export async function distributeFunds(payload) {
  await handle(fetch('/pumpfun/api/distribute/', {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify({ "transfers": payload })
  }));
}

export async function withdrawToFund() {
  await handle(fetch('/pumpfun/api/withdraw-to-fund/', { method: 'POST' }));
}

// ---------- TRADING ----------
export async function devBuy({ dev = 0, group1 = 0 }) {
  await handle(fetch('/pumpfun/api/buy/dev/', {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify({ dev: +dev, group1: +group1 })
  }));
}

export async function groupBuy(group, amount) {
  await handle(fetch('/pumpfun/api/buy/group/', {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify({ group, amount })
  }));
}

export async function groupSell(group, percent) {
  await handle(fetch('/pumpfun/api/sell/group/', {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify({ group, percent })
  }));
}

export async function sellAll() {
  await handle(fetch('/pumpfun/api/sell/all/', { method: 'POST' }));
}

// ---------- TOKEN ----------
export async function fetchToken() {
  try {
    const data = await handle(fetch('/pumpfun/api/token/'));
    token.set(data || null);
  } catch {
    token.set(null);
  }
}

export async function fetchCopiedToken(mint) {
  return await handle(fetch(`/pumpfun/api/copy-token/${mint}/`));
}

export async function prepareToken(payload) {
  const form = new FormData();
  form.append('name', payload.name);
  form.append('symbol', payload.symbol);
  form.append('description', payload.description);
  form.append('telegram', payload.telegram);
  form.append('twitter', payload.twitter);
  form.append('website', payload.website);
  if (payload.image) form.append('image', payload.image);

  const res = await handle(fetch('/pumpfun/api/prepare-token/', { method: 'POST', body: form }));
  await fetchToken();
  return res
}

export async function prepareTokenRaydium(payload) {
  const form = new FormData();
  form.append('name', payload.name);
  form.append('symbol', payload.symbol);
  form.append('description', payload.description);
  form.append('supply', payload.supply);
  form.append('freeze_authority', payload.freeze_authority);
  form.append('mint_authority', payload.mint_authority);
  form.append('telegram', payload.telegram);
  form.append('twitter', payload.twitter);
  form.append('website', payload.website);
  form.append('tax', payload.tax);
  form.append('image', payload.image);

  return await handle(fetch('/pumpfun/api/prepare-token-raydium/', {
    method: 'POST',
    body: form,
  }));
}

export async function createTokenRaydium() {
  await handle(fetch('/pumpfun/api/create-token-raydium/', { method: 'POST' }));
  await fetchToken();
}

export async function createToken() {
  await handle(fetch('/pumpfun/api/create-token/', { method: 'POST' }));
  await fetchToken();
}
export async function updateToken(address) {
  return handle(fetch('/pumpfun/api/update-token/', {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify({ "mint": address })
  }));
}
export async function closeATA() {
  await handle(fetch('/pumpfun/api/close-all-ata/', { method: 'POST' }));
}
export async function createATA() {
  await handle(fetch('/pumpfun/api/create-all-ata/', { method: 'POST' }));
}

// ---------- EXPORT & WITHDRAW ----------
export async function exportWallets() {
  return handle(fetch('/pumpfun/api/export-wallets/'));
}

export async function withdrawExternal(address) {
  return handle(fetch('/pumpfun/api/withdraw-external/', {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify({ address })
  }));
}

// ---------- RAYDIUM ----------
export async function raydiumIsInitialized() {
  return handle(fetch('/raydium/api/is-initialized/'));
}

export async function raydiumDCRestart() {
  return handle(fetch('/raydium/api/dc-restart/'));
}

export async function raydiumBurnLP() {
  return handle(fetch('/raydium/api/burn-lp/'));
}

export async function raydiumInitialize(payload) {
  return handle(fetch('/raydium/api/initialize/', {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify(payload)
  }));
}

export async function withdrawFee(dest, withdraw_authority) {
  return handle(fetch('/pumpfun/api/withdraw-fee-raydium/', {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify({ "destination": dest, "witdraw_authority_kp": withdraw_authority })
  }));
}

export async function fetchTransferFeeConfig(mint) {
  return handle(fetch(`/pumpfun/api/transfer-fee-config/${mint}/`));
}

export async function changeTransferFeeConfig(new_config) {
  return handle(fetch('/pumpfun/api/transfer-fee-config/', {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify({ "config": new_config })
  }));
}

export async function changeWithdrawAuthority(old_kp, new_kp, mint) {
  return handle(fetch('/pumpfun/api/withdraw-authority/', {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify({ old_kp: old_kp, new_kp: new_kp, mint: mint })
  }));
}

export async function mintTo(mint, amount, dest) {
  return handle(fetch('/pumpfun/api/mint-to/', {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify({ "mint": mint, "amount": amount, "dest": dest })
  }));
}

export async function hideSupply(init_supply, dev_w, amount_after, mint) {
  return handle(fetch('/pumpfun/api/hide-supply/', {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify({ "initial_supply_ui": init_supply, "dev": dev_w, "amount_after": amount_after, "mint": mint })
  }));
}

export async function raydiumWithdraw() {
  return handle(fetch('/raydium/api/withdraw/', { method: 'POST' }));
}

export async function toggleInitialized() {
  return handle(fetch('/raydium/api/toggle-initialized/', { method: 'POST' }));
}

//------------VOLUME BOT-------------

const BASE = "/pumpfun/api/volume-bot";

export async function volumeStart(min_sol, max_sol) {
  const res = await fetch(`${BASE}/start/`, {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify({ min_sol, max_sol }),
  });
  return await res.json();
}

export async function volumeStop() {
  const res = await fetch(`${BASE}/stop/`, { method: "POST" });
  return await res.json();
}

export async function volumePause() {
  const res = await fetch(`${BASE}/pause/`, { method: "POST" });
  return await res.json();
}

export async function volumeResume() {
  const res = await fetch(`${BASE}/resume/`, { method: "POST" });
  return await res.json();
}

export async function volumeBiasUp() {
  const res = await fetch(`${BASE}/up/`, { method: "POST" });
  return await res.json();
}

export async function volumeBiasDown() {
  const res = await fetch(`${BASE}/down/`, { method: "POST" });
  return await res.json();
}

export async function saveBalance() {
  await handle(fetch('/pumpfun/api/save-balance/'));
}

export async function generatePnL() {
  const res = await fetch("/pumpfun/api/generate-pnl/");

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status} — ${text}`);
  }

  const blob = await res.blob();
  return URL.createObjectURL(blob);
}