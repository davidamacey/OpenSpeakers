<!-- Settings Page -->
<script lang="ts">
  import { onMount } from 'svelte';
  import { models, refreshModels } from '$stores/models';
  import axiosInstance from '$lib/axios';

  interface NvidiaSmi {
    utilization_pct: number;
    temperature_c: number;
    power_draw_w: number;
    power_limit_w: number;
    fan_speed_pct: number | null;
    memory_used_mb: number;
    memory_total_mb: number;
  }

  interface SystemInfo {
    current_model: string | null;
    registered_models: string[];
    gpu: {
      available: boolean;
      device_id?: number;
      device_name?: string;
      vram_total_gb?: number;
      vram_used_gb?: number;
      vram_reserved_gb?: number;
      note?: string;
      nvidia_smi?: NvidiaSmi;
    };
    disk: {
      total_gb: number;
      used_gb: number;
      free_gb: number;
    };
    audio_output_dir: string;
    model_cache_dir: string;
  }

  let systemInfo: SystemInfo | null = $state(null);
  let loadingInfo = $state(false);
  let loadError = $state('');
  let autoRefresh = $state(false);

  // Derived GPU stats
  let vramPct = $derived.by(() => {
    if (!systemInfo?.gpu.vram_total_gb || !systemInfo?.gpu.vram_used_gb) return 0;
    return Math.round((systemInfo.gpu.vram_used_gb / systemInfo.gpu.vram_total_gb) * 100);
  });

  let gpuUtilPct = $derived(systemInfo?.gpu.nvidia_smi?.utilization_pct ?? 0);

  let temperature = $derived(systemInfo?.gpu.nvidia_smi?.temperature_c ?? null);

  let tempColor = $derived.by(() => {
    if (temperature === null) return '';
    if (temperature < 60) return 'text-emerald-500 dark:text-emerald-400';
    if (temperature <= 80) return 'text-amber-500 dark:text-amber-400';
    return 'text-red-500 dark:text-red-400';
  });

  let tempBadgeClass = $derived.by(() => {
    if (temperature === null) return 'badge-available';
    if (temperature < 60) return 'badge-loaded';
    if (temperature <= 80) return 'badge-loading';
    return 'badge-error';
  });

  let diskPct = $derived.by(() => {
    if (!systemInfo?.disk) return 0;
    return Math.round((systemInfo.disk.used_gb / systemInfo.disk.total_gb) * 100);
  });

  // Auto-refresh effect with cleanup
  $effect(() => {
    if (!autoRefresh) return;
    const interval = setInterval(() => {
      loadSystemInfo();
    }, 5000);
    return () => clearInterval(interval);
  });

  onMount(async () => {
    await refreshModels();
    await loadSystemInfo();
  });

  async function loadSystemInfo(): Promise<void> {
    // Only show loading spinner on initial load, not on auto-refresh
    if (!systemInfo) loadingInfo = true;
    loadError = '';
    try {
      const res = await axiosInstance.get<SystemInfo>('/system/info');
      systemInfo = res.data;
    } catch (err) {
      loadError = err instanceof Error ? err.message : 'Failed to load system info';
    } finally {
      loadingInfo = false;
    }
  }

  function vramBarColor(pct: number): string {
    if (pct > 90) return 'bg-red-500';
    if (pct > 75) return 'bg-orange-500';
    return 'bg-primary-500';
  }

  function utilBarColor(pct: number): string {
    if (pct > 90) return 'bg-red-500';
    if (pct > 60) return 'bg-amber-500';
    return 'bg-emerald-500';
  }
</script>

<div class="p-6 max-w-4xl mx-auto space-y-6">
  <!-- Page header -->
  <div class="page-header">
    <h1 class="page-title">Settings</h1>
    <p class="page-description">
      GPU status, model management, and system configuration.
    </p>
  </div>

  <!-- GPU Status -->
  <div class="card p-5 space-y-4">
    <div class="flex items-center justify-between">
      <h2 class="section-title">GPU Status</h2>
      <div class="flex items-center gap-3">
        <!-- Auto-refresh toggle -->
        <label class="flex items-center gap-2 cursor-pointer select-none">
          <span class="text-xs text-gray-500 dark:text-gray-400">Auto-refresh</span>
          <button
            type="button"
            role="switch"
            aria-checked={autoRefresh}
            onclick={() => (autoRefresh = !autoRefresh)}
            class="relative inline-flex h-5 w-9 items-center rounded-full transition-colors duration-200
                   {autoRefresh
                     ? 'bg-primary-600 dark:bg-primary-500'
                     : 'bg-gray-300 dark:bg-gray-600'}"
          >
            <span
              class="inline-block h-3.5 w-3.5 transform rounded-full bg-white shadow-sm
                     transition-transform duration-200
                     {autoRefresh ? 'translate-x-4' : 'translate-x-0.5'}"
            ></span>
          </button>
        </label>
        <!-- Manual refresh -->
        <button onclick={loadSystemInfo} class="btn-secondary text-xs px-3 py-1.5" disabled={loadingInfo}>
          {#if loadingInfo}
            <div class="spinner-sm"></div>
          {:else}
            <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path
                stroke-linecap="round"
                stroke-linejoin="round"
                stroke-width="2"
                d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
              />
            </svg>
            Refresh
          {/if}
        </button>
      </div>
    </div>

    {#if loadingInfo && !systemInfo}
      <div class="flex items-center gap-3 py-8 justify-center">
        <div class="spinner"></div>
        <span class="text-sm text-gray-400">Loading system info...</span>
      </div>
    {:else if loadError && !systemInfo}
      <div
        class="flex items-start gap-3 p-4 rounded-lg
               bg-red-950/50 border border-red-900/50 text-red-300 text-sm"
      >
        <svg
          class="w-5 h-5 flex-shrink-0 text-red-400 mt-0.5"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            stroke-linecap="round"
            stroke-linejoin="round"
            stroke-width="2"
            d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z"
          />
        </svg>
        <div class="flex-1">
          <p>{loadError}</p>
        </div>
        <button
          onclick={loadSystemInfo}
          class="flex-shrink-0 px-3 py-1 text-xs font-medium rounded-md
                 bg-red-900/50 hover:bg-red-900 text-red-200 transition-colors"
        >
          Retry
        </button>
      </div>
    {:else if systemInfo?.gpu.available}
      <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
        <!-- Left column: core GPU info -->
        <div class="space-y-4">
          <dl class="space-y-3 text-sm">
            <div class="flex justify-between">
              <dt class="text-gray-500 dark:text-gray-400">Device</dt>
              <dd class="font-medium text-gray-900 dark:text-gray-100">
                {systemInfo.gpu.device_name}
                <span class="text-gray-400 font-normal">(GPU {systemInfo.gpu.device_id})</span>
              </dd>
            </div>
            <div class="flex justify-between">
              <dt class="text-gray-500 dark:text-gray-400">Current model</dt>
              <dd>
                {#if systemInfo.current_model}
                  <span class="badge-loaded">{systemInfo.current_model}</span>
                {:else}
                  <span class="text-gray-400">None loaded</span>
                {/if}
              </dd>
            </div>
            {#if temperature !== null}
              <div class="flex justify-between">
                <dt class="text-gray-500 dark:text-gray-400">Temperature</dt>
                <dd>
                  <span class={tempBadgeClass}>
                    <span class={tempColor}>{temperature}&deg;C</span>
                  </span>
                </dd>
              </div>
            {/if}
            {#if systemInfo.gpu.nvidia_smi}
              <div class="flex justify-between">
                <dt class="text-gray-500 dark:text-gray-400">Power</dt>
                <dd class="text-gray-900 dark:text-gray-100">
                  {systemInfo.gpu.nvidia_smi.power_draw_w.toFixed(0)}W
                  <span class="text-gray-400 font-normal">
                    / {systemInfo.gpu.nvidia_smi.power_limit_w.toFixed(0)}W
                  </span>
                </dd>
              </div>
              {#if systemInfo.gpu.nvidia_smi.fan_speed_pct !== null}
                <div class="flex justify-between">
                  <dt class="text-gray-500 dark:text-gray-400">Fan speed</dt>
                  <dd class="text-gray-900 dark:text-gray-100">
                    {systemInfo.gpu.nvidia_smi.fan_speed_pct}%
                  </dd>
                </div>
              {/if}
            {/if}
          </dl>
        </div>

        <!-- Right column: bars -->
        <div class="space-y-4">
          <!-- VRAM usage bar -->
          <div>
            <div class="flex items-center justify-between mb-1.5">
              <span class="text-xs font-medium text-gray-500 dark:text-gray-400">VRAM</span>
              <span class="text-xs text-gray-400">
                {systemInfo.gpu.vram_used_gb?.toFixed(1)} / {systemInfo.gpu.vram_total_gb?.toFixed(1)} GB
                ({vramPct}%)
              </span>
            </div>
            <div class="h-2.5 bg-gray-100 dark:bg-[#2a2a2f] rounded-full overflow-hidden">
              <div
                class="h-full rounded-full transition-all duration-500 {vramBarColor(vramPct)}"
                style="width: {vramPct}%"
              ></div>
            </div>
            {#if systemInfo.gpu.vram_reserved_gb}
              <p class="text-[11px] text-gray-400 mt-1">
                {systemInfo.gpu.vram_reserved_gb.toFixed(2)} GB reserved by PyTorch
              </p>
            {/if}
          </div>

          <!-- GPU utilization bar -->
          {#if systemInfo.gpu.nvidia_smi}
            <div>
              <div class="flex items-center justify-between mb-1.5">
                <span class="text-xs font-medium text-gray-500 dark:text-gray-400">GPU Utilization</span>
                <span class="text-xs text-gray-400">{gpuUtilPct}%</span>
              </div>
              <div class="h-2.5 bg-gray-100 dark:bg-[#2a2a2f] rounded-full overflow-hidden">
                <div
                  class="h-full rounded-full transition-all duration-500 {utilBarColor(gpuUtilPct)}"
                  style="width: {gpuUtilPct}%"
                ></div>
              </div>
            </div>

            <!-- Memory bar (nvidia-smi MB, more granular than PyTorch VRAM) -->
            <div>
              <div class="flex items-center justify-between mb-1.5">
                <span class="text-xs font-medium text-gray-500 dark:text-gray-400">GPU Memory (nvidia-smi)</span>
                <span class="text-xs text-gray-400">
                  {(systemInfo.gpu.nvidia_smi.memory_used_mb / 1024).toFixed(1)} /
                  {(systemInfo.gpu.nvidia_smi.memory_total_mb / 1024).toFixed(1)} GB
                </span>
              </div>
              <div class="h-2.5 bg-gray-100 dark:bg-[#2a2a2f] rounded-full overflow-hidden">
                {@const memPct = Math.round(
                  (systemInfo.gpu.nvidia_smi.memory_used_mb / systemInfo.gpu.nvidia_smi.memory_total_mb) * 100
                )}
                <div
                  class="h-full rounded-full transition-all duration-500 {vramBarColor(memPct)}"
                  style="width: {memPct}%"
                ></div>
              </div>
            </div>
          {/if}
        </div>
      </div>

      <!-- Auto-refresh indicator -->
      {#if autoRefresh}
        <div class="flex items-center gap-2 text-xs text-gray-400 pt-1">
          <div class="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse"></div>
          Live -- refreshing every 5 seconds
        </div>
      {/if}
    {:else if systemInfo}
      <div
        class="flex items-start gap-3 p-4 rounded-lg
               bg-amber-50 dark:bg-amber-500/10
               border border-amber-200 dark:border-amber-500/20
               text-amber-800 dark:text-amber-300 text-sm"
      >
        <svg
          class="w-5 h-5 flex-shrink-0 mt-0.5 text-amber-500"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            stroke-linecap="round"
            stroke-linejoin="round"
            stroke-width="2"
            d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z"
          />
        </svg>
        <div>
          <p class="font-medium">No NVIDIA GPU detected</p>
          <p class="mt-1 text-amber-700 dark:text-amber-400/80">
            {systemInfo.gpu.note ?? 'Models will run on CPU, which is significantly slower.'}
          </p>
        </div>
      </div>
    {/if}
  </div>

  <!-- Registered Models -->
  <div class="card p-5 space-y-3">
    <div class="flex items-center justify-between">
      <h2 class="section-title">Registered Models</h2>
      <button onclick={refreshModels} class="btn-secondary text-xs px-3 py-1.5">
        <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path
            stroke-linecap="round"
            stroke-linejoin="round"
            stroke-width="2"
            d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
          />
        </svg>
        Refresh
      </button>
    </div>

    {#if $models.length === 0}
      <p class="text-sm text-gray-400 py-4 text-center">No models registered.</p>
    {:else}
      <ul class="divide-y divide-gray-100 dark:divide-gray-700/50">
        {#each $models as model (model.id)}
          <li class="py-3 flex items-start gap-3">
            <div
              class="mt-1.5 w-2 h-2 rounded-full flex-shrink-0
                     {model.status === 'loaded'
                       ? 'bg-green-500'
                       : model.status === 'loading'
                         ? 'bg-yellow-500 animate-pulse'
                         : 'bg-gray-400'}"
            ></div>
            <div class="flex-1 min-w-0">
              <div class="flex items-center gap-2 flex-wrap">
                <span class="font-medium text-sm text-gray-900 dark:text-gray-100">
                  {model.name}
                </span>
                <span
                  class={model.status === 'loaded'
                    ? 'badge-loaded'
                    : model.status === 'loading'
                      ? 'badge-loading'
                      : 'badge-available'}
                >
                  {model.status}
                </span>
                {#if model.supports_voice_cloning}
                  <span
                    class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium
                           bg-purple-100 text-purple-700
                           dark:bg-purple-500/15 dark:text-purple-400
                           border border-purple-200 dark:border-purple-500/20"
                  >
                    cloning
                  </span>
                {/if}
              </div>
              <p class="text-xs text-gray-500 dark:text-gray-400 mt-0.5">{model.description}</p>
              <div class="flex gap-3 mt-1 text-xs text-gray-400">
                <span>~{model.vram_gb_estimate} GB VRAM</span>
                <span>{model.supported_languages.join(', ')}</span>
              </div>
            </div>
          </li>
        {/each}
      </ul>
    {/if}
  </div>

  <!-- Storage -->
  {#if systemInfo?.disk}
    <div class="card p-5 space-y-3">
      <h2 class="section-title">Storage</h2>

      <dl class="space-y-3 text-sm">
        <div class="flex justify-between">
          <dt class="text-gray-500 dark:text-gray-400">Audio output</dt>
          <dd class="font-mono text-xs text-gray-700 dark:text-gray-300 truncate max-w-xs">
            {systemInfo.audio_output_dir}
          </dd>
        </div>
        <div class="flex justify-between">
          <dt class="text-gray-500 dark:text-gray-400">Model cache</dt>
          <dd class="font-mono text-xs text-gray-700 dark:text-gray-300 truncate max-w-xs">
            {systemInfo.model_cache_dir}
          </dd>
        </div>
      </dl>

      <!-- Disk usage bar -->
      <div class="pt-1">
        <div class="flex items-center justify-between mb-1.5">
          <span class="text-xs font-medium text-gray-500 dark:text-gray-400">Disk usage</span>
          <span class="text-xs text-gray-400">
            {systemInfo.disk.used_gb.toFixed(0)} / {systemInfo.disk.total_gb.toFixed(0)} GB
            ({diskPct}% used, {systemInfo.disk.free_gb.toFixed(0)} GB free)
          </span>
        </div>
        <div class="h-2.5 bg-gray-100 dark:bg-[#2a2a2f] rounded-full overflow-hidden">
          <div
            class="h-full rounded-full transition-all duration-500
                   {diskPct > 90 ? 'bg-red-500' : diskPct > 75 ? 'bg-orange-500' : 'bg-primary-500'}"
            style="width: {diskPct}%"
          ></div>
        </div>
      </div>
    </div>
  {/if}
</div>
