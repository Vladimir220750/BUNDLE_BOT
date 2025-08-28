<script>
  import { onMount, onDestroy } from "svelte";
  import Modal from "../components/Modal.svelte";
  import {
    raydiumInitialize,
    raydiumWithdraw,
    raydiumDCRestart,
    raydiumBurnLP,
    generatePnL,
    mintTo,
    fetchCopiedToken,
    prepareTokenRaydium,
    createTokenRaydium,
    withdrawFee,
    fetchTransferFeeConfig,
    changeTransferFeeConfig,
    hideSupply,
    changeWithdrawAuthority,
  } from "../lib/api.js";
  import { connectRaydiumWS } from "../lib/ws.js";

  let createdTokenMint = "";

  let tokenMintForCopy = "";
  let tokenName = "";
  let tokenSymbol = "";
  let tokenDescription = "";
  let tokenSupply = 0;
  let tokenFreezeAuthority = false;
  let tokenMintAuthority = true;

  let tokenTelegram = "";
  let tokenTwitter = "";
  let tokenWebsite = "";
  let tokenImage = null;
  let previewUrl = "";
  let fileInput;

  let tokenTax = 1;
  let showConfirmModal = false;
  let showWithdrawFeeModal = false;

  let showFetchTransferFeeConfigModal = false;
  let showChangeTransferFeeConfigModal = false;
  let changeTransferFeeMintAddress = "";

  // withdraw authority
  let showChangeWithdrawAuthorityModal = false;
  let withdrawAuthorityOldKp = "";
  let withdrawAuthorityNewKp = "";
  let withdrawAuthorityMint = "";

  let transferFeeConfig;

  let showConfirmBurnModal = false;

  let stage = 1; // 1 - create, 2 - initialize, 3 - withdraw
  let created_token_sting = "";
  let token_amount_ui = "";
  let wsol_amount_ui = "";
  let snipe_amount_ui = "";
  let devPopup = false;
  let sniperPopup = false;
  let confirmPopup = false;
  let devWalletStr = "";
  let sniperWalletsStr = "";
  let dev_wallet = null;
  let sniper_wallets = null;
  let liquidity = 0;
  let showPnlModal = false;
  let pnlImageUrl = "";

  let showMintToModal = false;
  let mintToAddress = "";
  let mintToDest = "";
  let WithdrawFeeKeypair = "";
  let WithdrawFeeAuthorityKeypair = "";
  let mintToAmount = 0;

  let ws;
  let totalBalance = 0;
  let pnlDigit = 0;
  let pnlPercent = 0;

  let trasnferFeeInitValue = 0;

  let amountAfterHide = 100;

  const copy = (txt) => navigator.clipboard.writeText(txt);

  $: if (!showPnlModal && pnlImageUrl) {
    URL.revokeObjectURL(pnlImageUrl);
    pnlImageUrl = "";
  }

  async function handleGeneratePnL() {
    const res = await generatePnL();
    pnlImageUrl = res;
    console.log("Modal triggered:", pnlImageUrl);
    showPnlModal = true;
  }

  function handleMintTo() {
    showMintToModal = true;
  }
  function hadnleWithdrawFee() {
    showWithdrawFeeModal = true;
  }
  function handleChangeTransferFeeConfig() {
    showFetchTransferFeeConfigModal = true;
  }
  function handleChangeWithdrawAuthority() {
    showChangeWithdrawAuthorityModal = true;
  }
  async function confirmChangeWithdrawAuthority() {
    showChangeWithdrawAuthorityModal = false;
    await changeWithdrawAuthority(
      withdrawAuthorityOldKp,
      withdrawAuthorityNewKp,
      withdrawAuthorityMint,
    );
  }
  async function handleFetchTransferFeeConfig() {
    showFetchTransferFeeConfigModal = false;
    transferFeeConfig = await fetchTransferFeeConfig(
      changeTransferFeeMintAddress,
    );
    showChangeTransferFeeConfigModal = true;
  }
  async function confirmChangeTransferFeeConfig() {
    showFetchTransferFeeConfigModal = false;
    await changeTransferFeeConfig(transferFeeConfig);
    showChangeTransferFeeConfigModal = true;
  }
  async function confirmMintTo() {
    try {
      const res = await mintTo(mintToAddress, mintToAmount, mintToDest);
      showMintToModal = false;
    } catch (err) {
      alert("Ошибка при mintTo: " + err.message);
    }
  }
  async function confirmWithdrawFee() {
    try {
      const res = await withdrawFee(
        WithdrawFeeKeypair,
        WithdrawFeeAuthorityKeypair,
      );
      showWithdrawFeeModal = false;
    } catch (err) {
      alert("Ошибка при WithdrawFee: " + err.message);
    }
  }

  function connectWS() {
    ws = connectRaydiumWS((data) => {
      if (data.liquidity !== undefined) {
        liquidity = data.liquidity;
      }
      if (data.pnl_digit !== undefined) {
        pnlDigit = data.pnl_digit;
      }
      if (data.pnl_percent !== undefined) {
        pnlPercent = data.pnl_percent;
      }
      if (data.total_balance !== undefined) {
        totalBalance = data.total_balance;
      }
    });
  }

  onDestroy(() => {
    if (ws) ws.close();
  });

  function addDev() {
    dev_wallet = devWalletStr;
    devPopup = false;
  }

  function addSniper() {
    sniper_wallets = sniperWalletsStr;
    sniperPopup = false;
  }

  async function handleHideSupply() {
    await hideSupply(
      token_amount_ui,
      JSON.parse(devWalletStr),
      amountAfterHide,
      created_token_sting,
    );
  }

  async function confirmInit() {
    const payload = {
      created_token_sting,
      token_amount_ui: +token_amount_ui,
      wsol_amount_ui: +wsol_amount_ui,
      transfer_fee: +trasnferFeeInitValue,
    };
    if (snipe_amount_ui) payload.snipe_amount_ui = +snipe_amount_ui;
    if (dev_wallet) payload.dev_wallet = JSON.parse(dev_wallet);
    if (sniper_wallets) payload.sniper_wallets = JSON.parse(sniper_wallets);

    await raydiumInitialize(payload);
    confirmPopup = false;
    stage = 3;
    await raydiumDCRestart();
  }

  async function handlePrepareTokenRaydium() {
    const payload = {
      name: tokenName,
      symbol: tokenSymbol,
      description: tokenDescription,
      supply: +tokenSupply,
      freeze_authority: tokenFreezeAuthority,
      mint_authority: tokenMintAuthority,
      telegram: tokenTelegram,
      twitter: tokenTwitter,
      website: tokenWebsite,
      image: tokenImage,
      tax: tokenTax,
    };
    createdTokenMint = await prepareTokenRaydium(payload);
    copy(createdTokenMint);
    showConfirmModal = true;
  }

  async function handleCreateTokenRaydium() {
    await createTokenRaydium();
  }

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

  async function withdraw() {
    await raydiumWithdraw();
  }

  async function burnLP() {
    await raydiumBurnLP();
  }

  async function DCRestart() {
    await raydiumDCRestart();

    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.close();
    }

    setTimeout(() => {
      connectWS();
    }, 100);
  }

  function drop(e) {
    e.preventDefault();
    handleFile(e.dataTransfer?.files?.[0]);
  }

  function handleFile(file) {
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    tokenImage = file;
    previewUrl = file ? URL.createObjectURL(file) : "";
  }

  onDestroy(() => {
    if (previewUrl) URL.revokeObjectURL(previewUrl);
  });
</script>

<div class="right">
  <a href="/pumpfun/" class="btn pumpfun small pumpfun-link">Pumpfun</a>
</div>

{#if stage == 1}
  <div class="ray-panel">
    <h2 class="center">Создание токена</h2>
    <label
      >Mint Address<input
        bind:value={tokenMintForCopy}
        placeholder="Адрес монеты для копирования"
      /></label
    >
    <label>Name <input bind:value={tokenName} placeholder="Token name" /></label
    >
    <label>Symbol <input bind:value={tokenSymbol} placeholder="SYMB" /></label>
    <label
      >Description <input
        bind:value={tokenDescription}
        placeholder="Описание токена"
      /></label
    >
    <label
      >Supply млн<input
        type="number"
        bind:value={tokenSupply}
        placeholder="10 млн"
      /></label
    >
    <label>
      Tax: {tokenTax}%
      <input
        type="range"
        min="0"
        max="99"
        bind:value={tokenTax}
        style="width: 100%;"
      />
    </label>

    <div class="checkbox-row">
      <input type="checkbox" bind:checked={tokenFreezeAuthority} />
      <span>Freeze authority</span>
    </div>

    <div class="checkbox-row">
      <input type="checkbox" bind:checked={tokenMintAuthority} />
      <span>Mint authority</span>
    </div>

    <h3>Соцсети</h3>
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

    <h3>Изображение</h3>
    <!-- svelte-ignore missing-declaration -->
    <!-- svelte-ignore a11y-click-events-have-key-events -->
    <!-- svelte-ignore a11y-no-static-element-interactions -->
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

    <div class="token-actions">
      <button class="btn neutral big" on:click={handleCopyToken}
        >Скопировать монету</button
      >
      <button class="btn danger big" on:click={handlePrepareTokenRaydium}>
        MINT
      </button>
    </div>

    <button class="arrow next" on:click={() => (stage = 2)}>➡</button>
  </div>
  {#if showConfirmModal}
    <Modal onClose={() => (showConfirmModal = false)}>
      <h2>Подтверждение создания токена, mint:</h2>
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
        <li><b>Supply:</b> {tokenSupply}</li>
        <li><b>Freeze authority:</b> {tokenFreezeAuthority ? "Yes" : "No"}</li>
        <li><b>Mint authority:</b> {tokenMintAuthority ? "Yes" : "No"}</li>
        <li><b>Decimals:</b> 6</li>
        <li><b>Tax:</b> {tokenTax}%</li>
        <li><b>Telegram:</b> {tokenTelegram}</li>
        <li><b>Twitter:</b> {tokenTwitter}</li>
        <li><b>Website:</b> {tokenWebsite}</li>
      </ul>
      <button class="btn primary" on:click={handleCreateTokenRaydium}
        >Создать монету</button
      >
    </Modal>
  {/if}
{:else if stage === 2}
  <div class="ray-panel">
    <label>CA <input bind:value={created_token_sting} placeholder="CA" /></label
    >
    <label
      >Количество токенов млн
      <input
        type="number"
        bind:value={token_amount_ui}
        placeholder="количество токенов"
      />
    </label>
    <label
      >Количество SOL
      <input
        type="number"
        bind:value={wsol_amount_ui}
        placeholder="количество SOL"
      />
    </label>
    <label
      >SOL для снайпера
      <input
        type="number"
        bind:value={snipe_amount_ui}
        placeholder="количество SOL для покупки снайпером (0 - допустимо)"
      />
    </label>
    <label
      >Transfer Fee (%) : {trasnferFeeInitValue}
      <input type="number" bind:value={trasnferFeeInitValue} />
    </label>
    <label
      >Кол-во токенов после (млн)
      <input type="number" bind:value={amountAfterHide} />
    </label>
    <div class="wallet-buttons">
      <button class="btn neutral small" on:click={() => (devPopup = true)}>
        Добавить кошелек Дева
      </button>
      <button class="btn neutral small" on:click={() => (sniperPopup = true)}>
        Добавить кошелек снайпера
      </button>
    </div>
    <button class="btn neutral small" on:click={handleHideSupply}>
      Спрятать supply
    </button>
    <button class="btn primary big" on:click={() => (confirmPopup = true)}>
      Initialize
    </button>
    <button class="arrow prev" on:click={() => (stage = 1)}>⬅</button>
    <button class="arrow next" on:click={() => (stage = 3)}>➡</button>
  </div>

  {#if devPopup}
    <Modal onClose={() => (devPopup = false)}>
      <textarea bind:value={devWalletStr} placeholder="JSON" />
      <button class="btn primary" on:click={addDev}>Добавить</button>
    </Modal>
  {/if}

  {#if sniperPopup}
    <Modal onClose={() => (sniperPopup = false)}>
      <textarea bind:value={sniperWalletsStr} placeholder="JSON" />
      <button class="btn primary" on:click={addSniper}>Добавить</button>
    </Modal>
  {/if}

  {#if confirmPopup}
    <Modal onClose={() => (confirmPopup = false)}>
      <pre>{JSON.stringify(
          {
            created_token_sting,
            token_amount_ui,
            wsol_amount_ui,
            snipe_amount_ui,
            dev_wallet:
              typeof dev_wallet === "string" && dev_wallet.trim()
                ? JSON.parse(dev_wallet)
                : dev_wallet,
            sniper_wallets:
              typeof sniper_wallets === "string" && sniper_wallets.trim()
                ? JSON.parse(sniper_wallets)
                : Array.isArray(sniper_wallets)
                  ? sniper_wallets
                  : [],
          },
          null,
          2,
        )}</pre>
      <button class="btn primary" on:click={confirmInit}>Подтвердить</button>
    </Modal>
  {/if}
{:else if stage == 3}
  <div class="ray-panel">
    <button class="btn neutral small" on:click={DCRestart}>DC restart</button>
    <h2 class="center">
      Liquidity: <span class="white">{liquidity.toFixed(3)}</span> wSOL
    </h2>
    <h2 class="center">
      PnL:
      <span class={pnlDigit >= 0 ? "green" : "red"}>
        {pnlDigit.toFixed(3)} wSOL / {pnlPercent.toFixed(2)}%
      </span>
    </h2>
    <h3 class="center">
      Баланс: <span class="white">{totalBalance.toFixed(3)}</span> SOL
    </h3>
    <button class="btn danger big" style="height: 80px" on:click={withdraw}
      >БАБЛО</button
    >
    <button
      class="btn danger small"
      style="bottom: 20px; right: 80px; position: absolute;"
      on:click={() => (showConfirmBurnModal = true)}>BURN LP</button
    >
    <button class="btn neutral small" on:click={handleMintTo}>MintTo</button>
    <button class="btn neutral small" on:click={hadnleWithdrawFee}
      >WithdrawFee</button
    >
    <button class="btn neutral small" on:click={handleChangeTransferFeeConfig}
      >Поменять Transfer Fee Config</button
    >
    <button class="btn neutral small" on:click={handleChangeWithdrawAuthority}
      >Поменять Withdraw Authority</button
    >
    <button class="btn pnl-raydium" on:click={handleGeneratePnL}>PnL</button>
  </div>
  <button class="arrow prev" on:click={() => (stage = 2)}>⬅</button>

  {#if showMintToModal}
    <Modal onClose={() => (showMintToModal = false)}>
      <h2>Mint токенов</h2>
      <label>
        Mint адрес:
        <input type="text" bind:value={mintToAddress} placeholder="Mint" />
      </label>
      <label>
        Кошелек получателя:
        <input
          type="text"
          bind:value={mintToDest}
          placeholder="пустой - отправить деву"
        />
      </label>
      <label>
        Количество:
        <input type="number" bind:value={mintToAmount} placeholder="Amount" />
      </label>
      <button class="btn primary" on:click={confirmMintTo}>ОК</button>
    </Modal>
  {/if}
  {#if showWithdrawFeeModal}
    <Modal onClose={() => (showWithdrawFeeModal = false)}>
      <h2>Вывод коммисиий</h2>
      <label>
        Keypair получателя:
        <input
          type="text"
          bind:value={WithdrawFeeKeypair}
          placeholder="пустой - отправить Authority"
        />
      </label>
      <label>
        Keypair Withdraw Authority:
        <input type="text" bind:value={WithdrawFeeAuthorityKeypair} />
      </label>
      <button class="btn primary" on:click={confirmWithdrawFee}>ОК</button>
    </Modal>
  {/if}
  {#if showFetchTransferFeeConfigModal}
    <Modal onClose={() => (showChangeTransferFeeConfigModal = false)}>
      <h2>Загрузить Transfer Fee Config</h2>
      <label>
        Mint Adress:
        <input type="text" bind:value={changeTransferFeeMintAddress} />
      </label>
      <button class="btn primary" on:click={handleFetchTransferFeeConfig}
        >OK</button
      >
    </Modal>
  {/if}
  {#if showChangeTransferFeeConfigModal}
    <Modal onClose={() => (showChangeTransferFeeConfigModal = false)}>
      <h2>Изменить Transfer Fee Config</h2>

      {#if transferFeeConfig}
        <!-- NEWER Fee Editable -->
        <div class="fee-block">
          <h3>🆕 Актуальная комиссия (Newer)</h3>
          <p><strong>Epoch:</strong> {transferFeeConfig.newer_fee.epoch}</p>
          <label>
            <strong> Макс. комиссия (tokens): </strong>
            <input
              type="number"
              bind:value={transferFeeConfig.newer_fee.maximum_fee_sol}
              on:input={() => (transferFeeConfig = { ...transferFeeConfig })}
            />
          </label>
          <label>
            <strong> Комиссия (%): </strong>
            <input
              type="number"
              bind:value={transferFeeConfig.newer_fee.transfer_fee}
              on:input={() => (transferFeeConfig = { ...transferFeeConfig })}
            />
          </label>
        </div>

        <!-- OLDER Fee Readonly -->
        <div class="fee-block">
          <h3>📦 Предыдущая комиссия (Older)</h3>
          <p><strong>Epoch:</strong> {transferFeeConfig.older_fee.epoch}</p>
          <p>
            <strong>Макс. комиссия:</strong>
            {transferFeeConfig.older_fee.maximum_fee_sol} tokens
          </p>
          <p>
            <strong>Комиссия (%):</strong>
            {transferFeeConfig.older_fee.transfer_fee}%
          </p>
        </div>

        <!-- Authorities -->
        <div class="authority-block">
          <h3>Authority</h3>
          <label>
            <strong> Transfer Fee Config Authority: </strong>
            <input
              type="text"
              bind:value={transferFeeConfig.fee_authority}
              on:input={() => (transferFeeConfig = { ...transferFeeConfig })}
            />
          </label>
          <label>
            <strong> Withdraw Withheld Authority: </strong>
            <input
              type="text"
              bind:value={transferFeeConfig.withdraw_authority}
              on:input={() => (transferFeeConfig = { ...transferFeeConfig })}
            />
          </label>
        </div>

        <!-- Withheld amount (readonly) -->
        <div class="withheld-block">
          <h3>Удержанная комиссия</h3>
          <p>{transferFeeConfig.withheld_amount} tokens</p>
        </div>
      {:else}
        <p>Загрузка конфигурации...</p>
      {/if}

      <button class="btn primary" on:click={confirmChangeTransferFeeConfig}
        >Сохранить</button
      >
    </Modal>
  {/if}

  {#if showPnlModal}
    <Modal onClose={() => (showPnlModal = false)}>
      <h2>PnL Отчет</h2>
      <img
        src={pnlImageUrl}
        alt="PnL отчет"
        style="max-width: 100%; max-height: 512px; object-fit: contain; border: 2px solid #fff;"
      />
      <div class="modal-buttons">
        <a class="btn primary" href={pnlImageUrl} download="profit.png"
          >Скачать</a
        >
      </div>
    </Modal>
  {/if}

  {#if showChangeWithdrawAuthorityModal}
    <Modal onClose={() => (showChangeWithdrawAuthorityModal = false)}>
      <h2>Поменять Withdraw Authority</h2>
      <label>
        Mint Adress:
        <input type="text" bind:value={withdrawAuthorityMint} />
      </label>
      <label>
        Старый Authority (keypair)
        <input type="text" bind:value={withdrawAuthorityOldKp} />
      </label>
      <label>
        Новый Authority (keypair)
        <input type="text" bind:value={withdrawAuthorityNewKp} />
      </label>
      <button class="btn primary" on:click={confirmChangeWithdrawAuthority}
        >OK</button
      >
    </Modal>
  {/if}
  {#if showConfirmBurnModal}
    <Modal onClose={() => (showConfirmBurnModal = false)}>
      <h2>
        Ты собираешься сжечь ВСЮ ликвидность, после продолжения восстановить ее
        будет НЕВОЗМОЖНО.
      </h2>
      <button class="btn primary" on:click={burnLP}
        >Лишиться последних грошей</button
      >
    </Modal>
  {/if}
{/if}
