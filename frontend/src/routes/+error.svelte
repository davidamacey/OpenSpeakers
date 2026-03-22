<!-- Custom Error Page -->
<script lang="ts">
  import { page } from '$app/stores';
  import { goto } from '$app/navigation';
</script>

<svelte:head>
  <title>{$page.status} Error | OpenSpeakers</title>
</svelte:head>

<div class="flex items-center justify-center min-h-screen p-6">
  <div class="text-center max-w-md space-y-6">
    <!-- Status code -->
    <p class="text-6xl font-bold text-primary-500 dark:text-primary-400">
      {$page.status}
    </p>

    <!-- Error message -->
    <div class="space-y-2">
      <h1 class="page-title text-xl">
        {#if $page.status === 404}
          Page not found
        {:else if $page.status === 403}
          Access denied
        {:else if $page.status >= 500}
          Server error
        {:else}
          Something went wrong
        {/if}
      </h1>
      <p class="page-description">
        {#if $page.error?.message}
          {$page.error.message}
        {:else if $page.status === 404}
          The page you are looking for does not exist or has been moved.
        {:else}
          An unexpected error occurred. Please try again later.
        {/if}
      </p>
    </div>

    <!-- Action buttons -->
    <div class="flex items-center justify-center gap-3">
      <button
        onclick={() => goto('/tts')}
        class="btn-primary"
      >
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-4 0h4" />
        </svg>
        Go to TTS
      </button>
      <button
        onclick={() => history.back()}
        class="btn-secondary"
      >
        Go back
      </button>
    </div>
  </div>
</div>
