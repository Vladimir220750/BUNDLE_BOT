<script>
  import { onMount, onDestroy } from "svelte";
  import { step, token } from "../lib/api.js";
  import Modal from "../components/Modal.svelte";
  import {
    fetchToken,
    prepareToken,
    updateToken,
    devBuy,
    createATA,
    closeATA,
    fetchCopiedToken,
  } from "../lib/api.js";

  let createdTokenMint = "";
  let showConfirmModal = false;
  let tokenMintForCopy = "";
  let tokenTelegram = "";
  let tokenWebsite = "";
  let tokenTwitter = "";
  let creating = true,
    tokenName = "",
    tokenSymbol = "",
    tokenDescription = "";
  let tokenImage = null,
    previewUrl = "",
    fileInput,
    devQty = 0,
    g1Qty = 0;

  const copy = (txt) => navigator.clipboard.writeText(txt);
  onMount(async () => {
    await fetchToken();
    creating = !$token;
  });

  const finalize_update = (address) =>
    updateToken(address).then(() => (creating = false));

  const doDevBuy = () =>
    devBuy({ dev: devQty, group1: g1Qty }).then(() => step.set("control"));

  const drop = (e) => {
    e.preventDefault();
    handleFile(e.dataTransfer?.files?.[0]);
  };

  function handleFile(file) {
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    tokenImage = file;
    previewUrl = file ? URL.createObjectURL(file) : "";
  }

  onDestroy(() => {
    if (previewUrl) URL.revokeObjectURL(previewUrl);
  });

  async function handleCopyToken() {
    try {
      const data = await fetchCopiedToken(tokenMintForCopy);

      tokenName = data.name || "";
      tokenSymbol = data.symbol || "";
      tokenDescription = data.description || "";
      tokenTelegram = data.telegram || "";
      tokenTwitter = data.twitter || "";
      tokenWebsite = data.website || "";

      if (previewUrl) {
        URL.revokeObjectURL(previewUrl);
        previewUrl = "";
      }

      if (data.image_base64) {
        const blob = await (
          await fetch(`data:image/png;base64,${data.image_base64}`)
        ).blob();
        tokenImage = new File([blob], "image.png", { type: blob.type });
        previewUrl = URL.createObjectURL(blob);
      } else if (data.image) {
        const imgResp = await fetch(data.image);
        const imgBlob = await imgResp.blob();
        tokenImage = new File([imgBlob], "image.png", { type: imgBlob.type });
        previewUrl = URL.createObjectURL(imgBlob);
      }
    } catch (e) {
      alert("Не удалось скопировать токен: " + e.message);
    }
  }

  async function handlePrepareToken() {
    const payload = {
      name: tokenName,
      symbol: tokenSymbol,
      description: tokenDescription,
      telegram: tokenTelegram,
      twitter: tokenTwitter,
      website: tokenWebsite,
      image: tokenImage,
    };
    createdTokenMint = await prepareToken(payload);
    copy(createdTokenMint);
    console.log(createdTokenMint)
    showConfirmModal = true;
  }
</script>

<div class="main">
  <h1 class="center">ПЕЧАТНАЯ МАШИНКА 3000</h1>
  <div class="right">
    <a href="/raydium/" class="btn raydium small">Raydium</a>
  </div>
  <div class="token-card">
    <div class="header-row">
      {#if $token?.uri}
        <a class="btn primary small" href={$token.uri} target="_blank"
          >Метаданные</a
        >
      {/if}
      {#if !creating}
        <button class="btn danger small" on:click={() => (creating = true)}
          >Создать другой токен</button
        >
      {:else}
        <button
          class="btn neutral small"
          on:click={() => {
            creating = false;
            fetchToken();
          }}>Назад</button
        >
      {/if}
    </div>
    {#if creating}
      <div class="token-inputs">
        <label
          >Mint Address<input
            bind:value={tokenMintForCopy}
            placeholder="Адрес монеты для копирования"
          /></label
        >
        <label>Name: <input bind:value={tokenName} /></label>
        <label>Symbol: <input bind:value={tokenSymbol} /></label>
        <label>Description: <input bind:value={tokenDescription} /></label>
        <label
          >Telegram <input
            bind:value={tokenTelegram}
            placeholder="https://t.me/..."
          /></label
        >
        <label
          >Twitter <input
            bind:value={tokenTwitter}
            placeholder="https://twitter.com/..."
          /></label
        >
        <label
          >Website <input
            bind:value={tokenWebsite}
            placeholder="https://..."
          /></label
        >

        <!-- svelte-ignore a11y-no-static-element-interactions -->
        <!-- svelte-ignore a11y-click-events-have-key-events -->
        <div
          class="drop-zone"
          on:dragover|preventDefault
          on:drop={drop}
          on:click={() => fileInput.click()}
        >
          {#if previewUrl}
            <img class="preview" src={previewUrl} alt="preview" />
          {:else}
            1:1 до 512 px, ≤1 MB
          {/if}
          <input
            type="file"
            accept="image/*"
            bind:this={fileInput}
            on:change={(e) => handleFile(e.target.files[0])}
            hidden
          />
        </div>
        <button class="btn neutral big" on:click={handleCopyToken}
          >Скопировать монету</button
        >
        <button class="btn neutral big" on:click={handlePrepareToken}>Добавить токен</button
        >
      </div>
      {#if showConfirmModal}
        <Modal onClose={() => (showConfirmModal = false)}>
          <h2>Предпросмотр токена:</h2>
          <button class="token-mint-btn" on:click={() => copy(createdTokenMint)}
            >{createdTokenMint}</button
          >
          <img
            src={previewUrl}
            alt="preview"
            style="max-width: 128px; max-height: 128px;"
          />
          <ul>
            <li><b>Name:</b> {tokenName}</li>
            <li><b>Symbol:</b> {tokenSymbol}</li>
            <li><b>Description:</b> {tokenDescription}</li>
            <li><b>Telegram:</b> {tokenTelegram}</li>
            <li><b>Twitter:</b> {tokenTwitter}</li>
            <li><b>Website:</b> {tokenWebsite}</li>
          </ul>
        </Modal>
      {/if}
    {:else}
      <div class="token-inputs">
        <label
          >Дев покупает (млн): <input
            type="number"
            min="0"
            bind:value={devQty}
          /></label
        >
        <label
          >Бандл покупает (млн): <input
            type="number"
            min="0"
            bind:value={g1Qty}
          /></label
        >
      </div>
      <button class="btn neutral big" on:click={createATA}>Создать АТА</button>
      <button class="btn neutral big" on:click={doDevBuy}>Dev Buy</button>
      <button class="btn neutral big" on:click={closeATA}
        >Закрыть все АТА</button
      >
    {/if}
  </div>

  <button class="arrow next" on:click={() => step.set("control")}>➡</button>
</div>
