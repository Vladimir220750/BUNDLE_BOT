<script>
  export let onClose = () => {};

  function handleKey(e) {
    if (e.key === 'Escape') onClose();
  }
</script>

<svelte:window on:keydown={handleKey} />

<div class="modal-overlay" on:click={onClose}>
  <div class="modal" on:click|stopPropagation>
    <slot />
  </div>
</div>
