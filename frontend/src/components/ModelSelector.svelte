<script lang="ts">
  import type { ModelInfo } from '$api/models';

  let {
    models = [],
    value = $bindable(''),
    disabled = false
  }: {
    models?: ModelInfo[];
    value?: string;
    disabled?: boolean;
  } = $props();

  let selected = $derived(models.find((m) => m.id === value));

  function statusClass(status: string): string {
    if (status === 'loaded') return 'badge-loaded';
    if (status === 'loading') return 'badge-loading';
    return 'badge-available';
  }

  function statusDot(status: string): string {
    if (status === 'loaded') return 'bg-green-500';
    if (status === 'loading') return 'bg-yellow-500 animate-pulse';
    return 'bg-gray-400';
  }
</script>

<div class="space-y-2">
  <select
    bind:value
    {disabled}
    class="input pr-8"
  >
    <option value="">-- Select a model --</option>
    {#each models as model}
      <option value={model.id}>{model.name} ({model.vram_gb_estimate} GB VRAM)</option>
    {/each}
  </select>

  {#if selected}
    <div class="flex items-start gap-3 p-3 rounded-lg bg-gray-50 dark:bg-white/[0.04] text-sm">
      <div class="mt-0.5 h-2 w-2 rounded-full flex-shrink-0 {statusDot(selected.status)}"></div>
      <div class="flex-1 min-w-0">
        <div class="flex items-center gap-2 flex-wrap">
          <span class="font-medium">{selected.name}</span>
          <span class="{statusClass(selected.status)}">{selected.status}</span>
          {#if selected.supports_voice_cloning}
            <span class="inline-flex items-center px-2 py-0.5 rounded-full text-xs bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400">
              voice cloning
            </span>
          {/if}
        </div>
        <p class="text-gray-500 dark:text-gray-400 mt-0.5 truncate">{selected.description}</p>
        <div class="flex gap-2 mt-1 text-xs text-gray-400">
          <span>Languages: {selected.supported_languages.slice(0, 6).join(', ')}{selected.supported_languages.length > 6 ? '...' : ''}</span>
        </div>
      </div>
    </div>
  {/if}
</div>
