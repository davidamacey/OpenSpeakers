<!-- Model Comparison Page — generate the same text with multiple models sequentially -->
<script lang="ts">
  import { onMount } from 'svelte';
  import AudioPlayer from '$components/AudioPlayer.svelte';
  import ErrorBanner from '$components/ErrorBanner.svelte';
  import { models, modelsLoading, modelsError, refreshModels } from '$stores/models';
  import { generateTTS, getAudioUrl, pollJob, type TTSJob } from '$api/tts';
  import type { ModelInfo } from '$api/models';

  let text = $state('The quick brown fox jumps over the lazy dog.');
  let selectedModelIds: string[] = $state([]);
  let speed = $state(1.0);
  let language = $state('en');

  type ResultStatus = 'idle' | 'queued' | 'pending' | 'running' | 'complete' | 'failed';

  interface ComparisonResult {
    model: ModelInfo;
    status: ResultStatus;
    statusDetail: string;
    audioUrl: string;
    duration: number | null;
    processingMs: number | null;
    error: string | null;
  }

  let results: ComparisonResult[] = $state([]);
  let generating = $state(false);
  let cancelled = $state(false);
  let currentIndex = $state(-1);

  let allModels = $derived($models);
  let totalSelected = $derived(selectedModelIds.length);
  let canCompare = $derived(!!text.trim() && totalSelected >= 1 && !generating);
  let progressLabel = $derived(
    currentIndex >= 0 && totalSelected > 0
      ? `Processing ${currentIndex + 1} of ${totalSelected}...`
      : ''
  );
  let completedCount = $derived(results.filter((r) => r.status === 'complete').length);
  let failedCount = $derived(results.filter((r) => r.status === 'failed').length);

  const LANGUAGES = [
    { code: 'en', name: 'English' },
    { code: 'de', name: 'German' },
    { code: 'fr', name: 'French' },
    { code: 'es', name: 'Spanish' },
    { code: 'it', name: 'Italian' },
    { code: 'pt', name: 'Portuguese' },
    { code: 'ja', name: 'Japanese' },
    { code: 'ko', name: 'Korean' },
    { code: 'zh', name: 'Chinese' },
    { code: 'nl', name: 'Dutch' },
  ];

  onMount(refreshModels);

  function toggleModel(modelId: string): void {
    if (selectedModelIds.includes(modelId)) {
      selectedModelIds = selectedModelIds.filter((id) => id !== modelId);
    } else if (selectedModelIds.length < 4) {
      selectedModelIds = [...selectedModelIds, modelId];
    }
  }

  function handleCancel(): void {
    cancelled = true;
  }

  async function handleCompare(): Promise<void> {
    if (!canCompare) return;
    generating = true;
    cancelled = false;
    currentIndex = -1;

    // Build initial results with queue positions
    results = selectedModelIds
      .map((id) => allModels.find((m) => m.id === id)!)
      .filter(Boolean)
      .map((model, idx) => ({
        model,
        status: 'queued' as ResultStatus,
        statusDetail: `Queued (${idx + 1} of ${selectedModelIds.length})`,
        audioUrl: '',
        duration: null,
        processingMs: null,
        error: null,
      }));

    // Process sequentially — the Celery worker has concurrency=1 so
    // parallel requests would just queue anyway and provide no benefit
    for (let idx = 0; idx < results.length; idx++) {
      if (cancelled) {
        // Mark remaining as cancelled
        for (let j = idx; j < results.length; j++) {
          results[j] = {
            ...results[j],
            status: 'failed',
            statusDetail: 'Cancelled',
            error: 'Cancelled by user',
          };
        }
        break;
      }

      currentIndex = idx;
      results[idx] = {
        ...results[idx],
        status: 'pending',
        statusDetail: 'Submitting...',
      };

      try {
        const resp = await generateTTS({
          model_id: results[idx].model.id,
          text: text.trim(),
          speed,
          language,
        });

        if (cancelled) {
          results[idx] = {
            ...results[idx],
            status: 'failed',
            statusDetail: 'Cancelled',
            error: 'Cancelled by user',
          };
          continue;
        }

        results[idx] = {
          ...results[idx],
          status: 'running',
          statusDetail: 'Generating audio...',
        };

        const finalJob = await pollJob(resp.job_id, (job) => {
          if (cancelled) return;
          const jobStatus = job.status as ResultStatus;
          let detail = 'Processing...';
          if (jobStatus === 'pending') detail = 'Loading model...';
          else if (jobStatus === 'running') detail = 'Generating audio...';
          results[idx] = {
            ...results[idx],
            status: jobStatus,
            statusDetail: detail,
          };
        });

        if (finalJob.status === 'failed') {
          results[idx] = {
            ...results[idx],
            status: 'failed',
            statusDetail: 'Failed',
            error: finalJob.error_message ?? 'Generation failed',
          };
        } else {
          results[idx] = {
            ...results[idx],
            status: 'complete',
            statusDetail: 'Complete',
            audioUrl: getAudioUrl(finalJob.id),
            duration: finalJob.duration_seconds,
            processingMs: finalJob.processing_time_ms,
          };
        }
      } catch (err) {
        results[idx] = {
          ...results[idx],
          status: 'failed',
          statusDetail: 'Failed',
          error: err instanceof Error ? err.message : 'Generation failed',
        };
      }
    }

    currentIndex = -1;
    generating = false;
    cancelled = false;
  }

  function statusBadgeClass(status: ResultStatus): string {
    if (status === 'complete') return 'badge-loaded';
    if (status === 'failed') return 'badge-error';
    if (status === 'running') return 'badge-loading';
    if (status === 'pending') return 'badge-loading';
    return 'badge-available';
  }
</script>

<div class="p-6 max-w-5xl mx-auto space-y-6">
  <div class="page-header">
    <h1 class="page-title">Model Comparison</h1>
    <p class="page-description">
      Generate the same text with multiple models to compare quality.
    </p>
  </div>

  <!-- Models loading error -->
  {#if $modelsError}
    <ErrorBanner message={$modelsError} onRetry={refreshModels} />
  {/if}

  <!-- Setup -->
  <div class="card p-5 space-y-4">
    <div>
      <label class="label" for="compare-text">Text (shared across all models)</label>
      <textarea
        id="compare-text"
        bind:value={text}
        rows={3}
        class="input resize-none"
        disabled={generating}
        maxlength={4096}
      ></textarea>
    </div>

    <div>
      <p class="label">Select models to compare (up to 4)</p>

      {#if $modelsLoading}
        <div class="flex gap-2 mt-1">
          {#each [1, 2, 3] as _}
            <div class="h-9 w-28 bg-gray-200 dark:bg-[#1e1e22] rounded-lg animate-pulse"></div>
          {/each}
        </div>
      {:else if allModels.length === 0 && !$modelsError}
        <p class="text-sm text-gray-500 dark:text-gray-500 mt-1">
          No models available.
          <button onclick={refreshModels} class="text-primary-500 hover:underline ml-1">
            Refresh
          </button>
        </p>
      {:else}
        <div class="flex flex-wrap gap-2 mt-1">
          {#each allModels as model}
            <button
              onclick={() => toggleModel(model.id)}
              class="px-3 py-1.5 rounded-lg border text-sm font-medium transition-colors
                {selectedModelIds.includes(model.id)
                ? 'border-primary-500 bg-primary-50 text-primary-700 dark:bg-primary-900/30 dark:text-primary-400'
                : 'border-gray-200 dark:border-[#2a2a2f] text-gray-600 dark:text-gray-300 hover:border-gray-300 dark:hover:border-[#3f3f46]'}"
              disabled={generating ||
                (!selectedModelIds.includes(model.id) && selectedModelIds.length >= 4)}
            >
              {model.name}
            </button>
          {/each}
        </div>
      {/if}
    </div>

    <div class="flex gap-6 items-end flex-wrap">
      <!-- Speed -->
      <div>
        <label class="label" for="cmp-speed">Speed: {speed.toFixed(1)}x</label>
        <input
          id="cmp-speed"
          type="range"
          min="0.5"
          max="2.0"
          step="0.1"
          bind:value={speed}
          disabled={generating}
          class="w-32"
        />
      </div>

      <!-- Language -->
      <div>
        <label class="label" for="cmp-language">Language</label>
        <select id="cmp-language" bind:value={language} disabled={generating} class="input w-32">
          {#each LANGUAGES as lang}
            <option value={lang.code}>{lang.name}</option>
          {/each}
        </select>
      </div>

      <div class="flex gap-2 items-center">
        {#if generating}
          <!-- Cancel button -->
          <button onclick={handleCancel} class="btn-danger" disabled={cancelled}>
            {#if cancelled}
              Cancelling...
            {:else}
              Cancel
            {/if}
          </button>
        {:else}
          <!-- Compare button -->
          <button onclick={handleCompare} disabled={!canCompare} class="btn-primary">
            Compare {totalSelected} Model{totalSelected !== 1 ? 's' : ''}
          </button>
        {/if}
      </div>
    </div>

    <!-- Progress indicator during generation -->
    {#if generating && progressLabel}
      <div class="flex items-center gap-3 pt-2">
        <span class="spinner-sm"></span>
        <span class="text-sm text-gray-600 dark:text-gray-300">{progressLabel}</span>
        {#if completedCount > 0 || failedCount > 0}
          <span class="text-xs text-gray-400 dark:text-gray-600">
            ({completedCount} done{failedCount > 0 ? `, ${failedCount} failed` : ''})
          </span>
        {/if}
      </div>
    {/if}
  </div>

  <!-- Results grid -->
  {#if results.length > 0}
    <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
      {#each results as result, idx (result.model.id)}
        <div
          class="card p-4 space-y-3 transition-all duration-200
            {idx === currentIndex ? 'ring-1 ring-primary-500/50 dark:ring-primary-400/30' : ''}"
        >
          <div class="flex items-center justify-between gap-2">
            <h3 class="font-semibold text-gray-900 dark:text-gray-100 truncate">
              {result.model.name}
            </h3>
            <span class="{statusBadgeClass(result.status)} flex-shrink-0">
              {#if result.status === 'queued'}
                queued
              {:else if result.status === 'pending'}
                submitting
              {:else if result.status === 'running'}
                generating
              {:else}
                {result.status}
              {/if}
            </span>
          </div>

          <!-- Status detail text -->
          {#if result.status !== 'complete' && result.status !== 'failed' && result.status !== 'idle'}
            <div class="flex items-center gap-2">
              {#if idx === currentIndex}
                <span class="spinner-sm"></span>
              {/if}
              <span class="text-sm text-gray-500 dark:text-gray-400">{result.statusDetail}</span>
            </div>

            <!-- Progress bar for active/queued items -->
            <div class="h-1.5 bg-gray-200 dark:bg-[#2a2a2f] rounded-full overflow-hidden">
              <div
                class="h-full bg-primary-500 rounded-full transition-all duration-300
                  {result.status === 'running' ? 'animate-pulse' : ''}"
                style="width: {result.status === 'running' ? '60%' : result.status === 'pending' ? '20%' : '5%'}"
              ></div>
            </div>
          {/if}

          {#if result.status === 'complete'}
            <AudioPlayer src={result.audioUrl} duration={result.duration} />
            <div class="flex gap-4 text-xs text-gray-400 dark:text-gray-600">
              {#if result.duration}
                <span>{result.duration.toFixed(1)}s audio</span>
              {/if}
              {#if result.processingMs}
                <span>{(result.processingMs / 1000).toFixed(1)}s generation</span>
              {/if}
            </div>
          {:else if result.status === 'failed'}
            <div class="text-sm text-red-500 dark:text-red-400 bg-red-50 dark:bg-red-900/20 rounded-lg p-3">
              {result.error}
            </div>
          {/if}
        </div>
      {/each}
    </div>

    <!-- Summary after completion -->
    {#if !generating && (completedCount > 0 || failedCount > 0)}
      <div class="card p-4">
        <p class="text-sm text-gray-600 dark:text-gray-300">
          Comparison complete:
          <span class="font-medium text-green-600 dark:text-green-400">
            {completedCount} succeeded
          </span>
          {#if failedCount > 0}
            ,
            <span class="font-medium text-red-600 dark:text-red-400">
              {failedCount} failed
            </span>
          {/if}
        </p>
      </div>
    {/if}
  {/if}
</div>
