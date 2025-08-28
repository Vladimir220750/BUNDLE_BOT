<script>
  import { onMount, onDestroy } from "svelte";
  import Modal from "../components/Modal.svelte";
  import { step, wallets, loadWallets } from "../lib/api.js";
  import { groupBuy, groupSell, sellAll } from "../lib/api.js";
  import { connectDataWS, stats, refresh } from "../lib/ws.js";
  import {
    volumeStart,
    volumeStop,
    volumePause,
    volumeResume,
    volumeBiasUp,
    volumeBiasDown,
    saveBalance,
    generatePnL,
  } from "../lib/api.js";

  const buy = [0.1, 0.2, 0.5, 1];
  const sell = [5, 10, 25, 100];

  let showPnlModal = false;
  let show_chart = false;
  let chart_contract_address = "";
  $: chartUrl = `https://dexscreener.com/solana/${chart_contract_address}?embed=1&loadChartSettings=0&tabs=0&info=0&chartLeftToolbar=0&chartTimeframesToolbar=0&chartTheme=dark&theme=dark&chartStyle=1&chartType=marketCap&interval=1`;
  let pnlImageUrl = "";

  $: if (!showPnlModal && pnlImageUrl) {
    URL.revokeObjectURL(pnlImageUrl);
    pnlImageUrl = "";
  }

  let volumeMessage = "";

  function notifyVolume(msg) {
    volumeMessage = msg;
    setTimeout(() => (volumeMessage = ""), 1000);
  }

  async function handleGeneratePnL() {
    const res = await generatePnL();
    pnlImageUrl = res;
    console.log("Modal triggered:", pnlImageUrl);
    showPnlModal = true;
  }

  const groups = [
    { k: "group2", l: "Бандл 2" },
    { k: "dev", l: "Dev" },
    { k: "group1", l: "Бандл 1" },
  ];

  let buyCustom = { group2: "", dev: "", group1: "" };
  let sellCustom = { group2: "", dev: "", group1: "" };

  let minVol = 0,
    maxVol = 0;

  let bias = 0;
  let ws;

  onMount(() => {
    loadWallets();
    ws = connectDataWS();
  });

  onDestroy(() => {
    if (ws) ws.close();
  });

  const groupLabels = {
    group2: "Бандл2",
    dev: "Dev",
    group1: "Бандл1",
    fund: "Fund",
  };

  $: grouped = Object.keys(groupLabels).map((k) => {
    const wsList = $wallets.filter((w) => w.group === k);
    const sol = wsList.reduce((t, w) => t + (w.sol_balance || 0), 0);
    const token = wsList.reduce((t, w) => t + (w.token_balance || 0), 0);
    return { key: k, label: groupLabels[k], wallets: wsList, sol, token };
  });

  $: totalSol = grouped.reduce((t, g) => t + g.sol, 0);
  $: totalToken = grouped.reduce((t, g) => t + g.token, 0);
</script>

<div class="control-layout">
  <div class="manual">
    <button class="btn-pnl" on:click={handleGeneratePnL}>PnL</button>
    <button class="btn primary small" on:click={saveBalance}
      >Запомнить Баланс</button
    >
    {#each groups as g}
      <div class="group-box">
        <h3>{g.l}</h3>
        <div class="custom">
          <input type="number" bind:value={buyCustom[g.k]} placeholder="buy" />
          <button
            class="btn neutral small"
            on:click={() => groupBuy(g.k, +buyCustom[g.k])}>OK</button
          >
        </div>
        <div class="row">
          {#each buy as a}
            <button class="buy" on:click={() => groupBuy(g.k, a)}>{a}</button>
          {/each}
        </div>
        <div class="custom">
          <input
            type="number"
            bind:value={sellCustom[g.k]}
            placeholder="sell %"
          />
          <button
            class="btn neutral small"
            on:click={() => groupSell(g.k, +sellCustom[g.k])}>OK</button
          >
        </div>
        <div class="row">
          {#each sell as p}
            <button class="sell" on:click={() => groupSell(g.k, p)}>{p}%</button
            >
          {/each}
        </div>
      </div>
    {/each}

    <button class="btn danger big sell-all" on:click={sellAll}>RUG PULL</button>
  </div>

  <div class="monitor">
    <div class="stats">
      <span
        >LIQ: <span class="red">{$stats.liq.toFixed(3)}</span>/<span
          class="green">0</span
        >
        SOL</span
      >
      <span>MCAP: {$stats.mcap.toFixed(1)} $</span>
      <span>TOTAL_BALANCE: {totalSol} SOL/{totalToken.toFixed(2)} МЛН</span>
      <span>BIAS: {bias.toFixed(2)}</span>
      <button class="btn neutral small" on:click={refresh}>Refresh</button>
    </div>
    <div class="logs">
      {#if show_chart == true}
        <div id="dexscreener-embed" style="width: 100%; height: 100%;">
          <!-- svelte-ignore a11y-missing-attribute -->
          <iframe
            src={chartUrl}
            width="100%"
            height="100%"
            style="border: 0; display: block;"
          ></iframe>
        </div>
      {:else}
        <label
          >CA:
          <input bind:value={chart_contract_address} />
          <button class="btn neutral small" on:click={() => (show_chart = true)}
            >Загрузить график</button
          >
        </label>
      {/if}
    </div>
    <div class="balances">
      {#each grouped as g (g.key)}
        <details class="balance">
          <summary>
            <div class="group-label">{g.label}</div>
            <div class="group-balance">
              {g.sol.toFixed(2)} SOL / {g.token.toFixed(2)} МЛН
            </div>
          </summary>
          <ul>
            {#each g.wallets as w (w.name)}
              <li class="group-label">{w.name}</li>
              <li class="group-balance">
                {w.sol_balance.toFixed(2)} SOL/{w.token_balance.toFixed(2)} МЛН
              </li>
            {/each}
          </ul>
        </details>
      {/each}
    </div>
  </div>

  <div class="volume">
    <label>Min SOL <input type="number" bind:value={minVol} /></label>
    <label>Max SOL <input type="number" bind:value={maxVol} /></label>
    <button
      class="btn primary small"
      on:click={async () => {
        const res = await volumeStart(minVol, maxVol);
        notifyVolume(res.message);
        if (res.bias !== undefined) bias = res.bias;
      }}>Start</button
    >

    <button
      class="btn danger small"
      on:click={async () => {
        const res = await volumeStop();
        notifyVolume(res.message);
      }}>Stop</button
    >

    <button
      class="btn neutral small"
      on:click={async () => {
        const res = await volumePause();
        notifyVolume(res.message);
      }}>Pause</button
    >
    <button
      class="btn neutral small"
      on:click={async () => {
        const res = await volumeResume();
        notifyVolume(res.message);
      }}>Resume</button
    >

    {#if volumeMessage}
      <div class="volume-message">{volumeMessage}</div>
    {/if}

    <div class="side-buttons">
      <button
        class="btn up small"
        on:click={async () => {
          const res = await volumeBiasUp();
          if (res.bias !== undefined) bias = res.bias;
          notifyVolume(res.message);
        }}>UP</button
      >

      <button
        class="btn down small"
        on:click={async () => {
          const res = await volumeBiasDown();
          if (res.bias !== undefined) bias = res.bias;
          notifyVolume(res.message);
        }}>DOWN</button
      >
    </div>
  </div>

  {#if showPnlModal}
    <Modal onClose={() => (showPnlModal = false)}>
      <h2>PnL Отчет</h2>
      <img
        src={pnlImageUrl}
        alt="PnL отчет"
        style="max-width: 100%; border: 2px solid #fff;"
      />
      <div class="modal-buttons">
        <a class="btn primary" href={pnlImageUrl} download="profit.png"
          >Скачать</a
        >
        <button class="btn neutral" on:click={() => (showPnlModal = false)}
          >Закрыть</button
        >
      </div>
    </Modal>
  {/if}

  <button
    class="arrow prev"
    style="right:20px;left:unset;"
    on:click={() => step.set("main")}>⬅</button
  >
</div>
