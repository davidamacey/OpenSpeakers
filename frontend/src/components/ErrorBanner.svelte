<script lang="ts">
  let { message = '', onRetry, onDismiss }: {
    message: string;
    onRetry?: () => void;
    onDismiss?: () => void;
  } = $props();
</script>

{#if message}
  <div role="alert" class="flex items-start gap-3 p-4 rounded-lg bg-red-950/50 border border-red-900/50 text-red-300 text-sm">
    <svg class="w-5 h-5 flex-shrink-0 text-red-400 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
        d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z" />
    </svg>
    <div class="flex-1 min-w-0">
      <p class="break-words">{message}</p>
    </div>
    {#if onRetry}
      <button onclick={onRetry}
        class="flex-shrink-0 px-3 py-1 text-xs font-medium rounded-md
               bg-red-900/50 hover:bg-red-900 text-red-200 transition-colors">
        Retry
      </button>
    {/if}
    {#if onDismiss}
      <button onclick={onDismiss}
        class="flex-shrink-0 text-red-400 hover:text-red-200 transition-colors"
        aria-label="Dismiss">
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>
    {/if}
  </div>
{/if}
