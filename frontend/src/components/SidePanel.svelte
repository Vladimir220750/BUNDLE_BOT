<script>
  import { onMount } from "svelte";
  import Modal from "./Modal.svelte";
  import { sidebarVisible } from "../lib/stores.js";
  import {
    wallets,
    loadWallets,
    archiveWallet,
    createWallets,
    getPrivateKey,
    distributeFunds,
    withdrawToFund,
    exportWallets,
    withdrawExternal,
    reloadWallets,
  } from "../lib/api.js";

  // — локальный state —
  let dev = false,
    fund = false,
    group1 = 0,
    group2 = 0;
  let amounts = {};
  let withdrawAddr = "";
  let withdrawPopup = false;
  let withdrawMessage = "";
  let withdrawLoading = false;

  onMount(loadWallets);

  const copy = (txt) => navigator.clipboard.writeText(txt);

  async function copyPK(addr) {
    const base58 = await getPrivateKey(addr);
    copy(base58);
  }
  const handleCreate = async () => {
    await createWallets({ dev, fund, group1, group2 });
  };

  const handleDistrib = () => {
    const payload = Object.fromEntries(
      Object.entries(amounts).filter(([, v]) => v > 0),
    );
    if (Object.keys(payload).length) distributeFunds(payload);
  };

  const handleExport = async () => {
    try {
      const data = await exportWallets();
      const json = JSON.stringify(data, null, 2);
      await navigator.clipboard.writeText(json);
      alert("Wallets JSON скопирован в буфер!");
    } catch (err) {
      alert("Ошибка при экспорте: " + err.message);
    }
  };
  const handleReload = async () => await reloadWallets();

  async function handleWithdraw() {
    withdrawLoading = true;
    try {
      const res = await withdrawExternal(withdrawAddr);
      withdrawMessage = res.message || res.msg || "OK";
    } catch (err) {
      withdrawMessage = err.message;
    } finally {
      withdrawLoading = false;
    }
  }
</script>

{#if $sidebarVisible}
  <aside class="sidebar-wrap">
    <div class="sidebar">
      <button class="close" on:click={() => sidebarVisible.set(false)}>✕</button
      >

      <details class="section">
        <summary>Create Wallets</summary>
        <label><input type="checkbox" bind:checked={dev} /> Dev Wallet</label>
        <label><input type="checkbox" bind:checked={fund} /> Fund Wallet</label>
        <label
          ><input
            type="checkbox"
            bind:checked={group1}
            on:change={() => (group1 = group1 || 1)}
          /> 1 Group</label
        >
        <input type="number" min="0" bind:value={group1} />
        <label
          ><input
            type="checkbox"
            bind:checked={group2}
            on:change={() => (group2 = group2 || 1)}
          /> 2 Group</label
        >
        <input type="number" min="0" bind:value={group2} />
        <button class="btn primary" on:click={handleCreate}>Create</button>
      </details>

      <details class="section wallets">
        <summary>Wallets</summary>
        {#each ["dev", "fund", "group1", "group2"] as g}
          {#if $wallets.filter((w) => w.group === g).length}
            <details>
              <summary>{g}</summary>
              {#each $wallets.filter((w) => w.group === g) as w}
                <div class="wallet-row">
                  <button
                    class="wallet-btn btn primary small"
                    on:click={() => copy(w.address)}
                    >{w.name || w.address.slice(0, 6)}</button
                  >
                  <!-- svelte-ignore a11y-click-events-have-key-events -->
                  <!-- svelte-ignore a11y-no-static-element-interactions -->
                  <span
                    class="icon"
                    title="copy PK"
                    on:click={() => copyPK(w.address)}>🔒</span
                  >
                  <!-- svelte-ignore a11y-click-events-have-key-events -->
                  <!-- svelte-ignore a11y-no-static-element-interactions -->
                  <span
                    class="icon"
                    title="Archive Wallet"
                    on:click={() => archiveWallet(w.address)}>🗑️</span
                  >
                </div>
              {/each}
            </details>
          {/if}
        {/each}
        <button class="btn primary small" on:click={handleExport}>Export</button
        >
        <button class="btn primary small" on:click={handleReload}>Reload</button
        >
      </details>

      <details class="section">
        <summary>Distribute SOL</summary>

        {#each ["dev", "group1", "group2"] as g}
          {#if $wallets.filter((w) => w.group === g).length}
            <details class="distribute-group">
              <summary>{g}</summary>

              {#each $wallets.filter((w) => w.group === g) as w (w.address)}
                <div class="distribute-row">
                  <!-- svelte-ignore a11y-label-has-associated-control -->
                  <label class="wallet-label">
                    {w.name || w.address.slice(0, 6)}
                  </label>

                  <input
                    type="number"
                    min="0"
                    step="0.01"
                    value={amounts[w.address] || ""}
                    on:input={(e) => {
                      const val = parseFloat(e.target.value) || 0;
                      amounts = { ...amounts, [w.address]: val };
                    }}
                  />
                </div>
              {/each}
            </details>
          {/if}
        {/each}

        <button class="btn primary" on:click={handleDistrib}>Distribute</button>
      </details>

      <details class="section">
        <summary>Закрытие аккаунтов</summary>
        <button class="btn primary" on:click={withdrawToFund}
          >Withdraw to Fund</button
        >
        <button
          class="btn primary"
          on:click={() => {
            withdrawPopup = true;
            withdrawMessage = "";
            withdrawAddr = "";
          }}
        >
          Вывести на
        </button>
      </details>
    </div>
  </aside>
  {#if withdrawPopup}
    <Modal onClose={() => (withdrawPopup = false)}>
      <input placeholder="Адрес" bind:value={withdrawAddr} />
      <button
        class="btn primary"
        on:click={handleWithdraw}
        disabled={withdrawLoading}>OK</button
      >
      {#if withdrawMessage}
        <p>{withdrawMessage}</p>
      {/if}
    </Modal>
  {/if}
{/if}
