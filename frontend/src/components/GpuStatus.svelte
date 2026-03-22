<!-- Compact GPU VRAM status indicator for the TTS page -->
<script lang="ts">
  import { onMount } from 'svelte';
  import axiosInstance from '$lib/axios';

  let {
    selectedModelVram = 0,
    generating = false,
  }: {
    selectedModelVram?: number;
    generating?: boolean;
  } = $props();

  interface GpuInfo {
    available: boolean;
    device_name?: string;
    vram_total_gb?: number;
    vram_used_gb?: number;
    nvidia_smi?: {
      memory_used_mb: number;
      memory_total_mb: number;
      utilization_pct: number;
      temperature_c: number;
    };
  }

  let gpuInfo: GpuInfo | null = $state(null);
  let currentModel: string | null = $state(null);
  let connected = $state(false);
  let fetchError = $state(false);

  let ws: WebSocket | null = null;
  let pollInterval: ReturnType<typeof setInterval> | null = null;

  // Derived GPU stats
  let vramUsedGb = $derived.by(() => {
    if (!gpuInfo) return 0;
    if (gpuInfo.nvidia_smi) return gpuInfo.nvidia_smi.memory_used_mb / 1024;
    return gpuInfo.vram_used_gb ?? 0;
  });
  let vramTotalGb = $derived.by(() => {
    if (!gpuInfo) return 0;
    if (gpuInfo.nvidia_smi) return gpuInfo.nvidia_smi.memory_total_mb / 1024;
    return gpuInfo.vram_total_gb ?? 0;
  });
  let vramPct = $derived(
    vramTotalGb > 0 ? Math.round((vramUsedGb / vramTotalGb) * 100) : 0
  );
  let availableVram = $derived(vramTotalGb - vramUsedGb);
  let modelWontFit = $derived(
    selectedModelVram > 0 && availableVram > 0 && selectedModelVram > availableVram
  );

  function vramBarColor(pct: number): string {
    if (pct > 90) return 'bg-red-500';
    if (pct > 75) return 'bg-orange-500';
    return 'bg-primary-500';
  }

  function connectWs(): void {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host;
    ws = new WebSocket(`${protocol}//${host}/ws/gpu`);

    ws.onopen = () => {
      connected = true;
      fetchError = false;
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === 'gpu_stats') {
          gpuInfo = data.gpu;
          currentModel = data.current_model;
        }
      } catch {
        // Ignore malformed messages
      }
    };

    ws.onclose = () => {
      connected = false;
      startPolling();
    };

    ws.onerror = () => {
      connected = false;
    };
  }

  async function fetchSystemInfo(): Promise<void> {
    try {
      const res = await axiosInstance.get('/system/info');
      gpuInfo = res.data.gpu;
      currentModel = res.data.current_model;
      fetchError = false;
    } catch {
      fetchError = true;
    }
  }

  function startPolling(): void {
    fetchSystemInfo();
    pollInterval = setInterval(fetchSystemInfo, 10000);
  }

  function cleanup(): void {
    if (ws) {
      ws.close();
      ws = null;
    }
    if (pollInterval) {
      clearInterval(pollInterval);
      pollInterval = null;
    }
  }

  onMount(() => {
    connectWs();
    return cleanup;
  });
</script>

{#if gpuInfo?.available}
  <div class="rounded-lg border border-gray-200 dark:border-gray-700/50 p-3 space-y-2">
    <!-- Row 1: Device name + VRAM bar + numbers -->
    <div class="flex items-center gap-3">
      <!-- GPU icon -->
      <svg
        class="w-4 h-4 text-gray-400 flex-shrink-0"
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
      >
        <path
          stroke-linecap="round"
          stroke-linejoin="round"
          stroke-width="2"
          d="M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2zM9 9h6v6H9V9z"
        />
      </svg>

      <span class="text-xs font-medium text-gray-600 dark:text-gray-300 whitespace-nowrap">
        {gpuInfo.device_name ?? 'GPU'}
      </span>

      <!-- VRAM bar -->
      <div class="flex-1 h-2 bg-gray-100 dark:bg-[#2a2a2f] rounded-full overflow-hidden">
        <div
          class="h-full rounded-full transition-all duration-500 {vramBarColor(vramPct)}"
          style="width: {vramPct}%"
        ></div>
      </div>

      <span class="text-xs text-gray-400 whitespace-nowrap">
        {vramUsedGb.toFixed(1)} / {vramTotalGb.toFixed(1)} GB
      </span>

      <!-- Active indicator -->
      {#if generating}
        <div class="flex items-center gap-1">
          <div class="w-1.5 h-1.5 rounded-full bg-amber-500 animate-pulse"></div>
          <span class="text-xs text-amber-500">Active</span>
        </div>
      {:else if connected}
        <div class="flex items-center gap-1">
          <div class="w-1.5 h-1.5 rounded-full bg-emerald-500"></div>
          <span class="text-xs text-emerald-500/70">Live</span>
        </div>
      {/if}
    </div>

    <!-- Row 2: Warning if model won't fit -->
    {#if modelWontFit}
      <div
        class="flex items-start gap-2 p-2 rounded-md bg-amber-50 dark:bg-amber-500/10
               border border-amber-200 dark:border-amber-500/20"
      >
        <svg
          class="w-3.5 h-3.5 flex-shrink-0 mt-0.5 text-amber-500"
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
        <p class="text-xs text-amber-700 dark:text-amber-300">
          This model needs ~{selectedModelVram} GB VRAM but only {availableVram.toFixed(1)} GB is
          free. It may fail to load.
        </p>
      </div>
    {/if}
  </div>
{/if}
