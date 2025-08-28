<script>
  export let basePath;

  import { step } from "./lib/api.js";
  import { sidebarVisible } from "./lib/stores.js";
  import SidePanel from "./components/SidePanel.svelte";
  import MainPage from "./pages/MainPage.svelte";
  import ControlPage from "./pages/ControlPage.svelte";
  import Simulator from "./components/Simulator.svelte";
  import RaydiumPage from "./pages/RaydiumPage.svelte";
</script>

<div class="container">
{#if basePath === 'raydium'}
  <RaydiumPage />
{:else}
  {#if !$sidebarVisible}
    <button
      class="hamburger"
      title="Show panel"
      on:click={() => sidebarVisible.set(true)}>☰</button
    >
  {/if}

  {#if $sidebarVisible}
    <SidePanel />
  {/if}

  {#if $step === 'main'}
    <MainPage />
  {:else if $step === 'control'}
    <ControlPage />
  {:else if $step === 'sim'}
    <Simulator />
  {/if}
{/if}
</div>