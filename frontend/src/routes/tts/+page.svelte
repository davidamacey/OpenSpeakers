<!-- TTS Generation Page -->
<script lang="ts">
  import { onMount } from 'svelte';
  import ModelSelector from '$components/ModelSelector.svelte';
  import ModelParams from '$components/ModelParams.svelte';
  import GpuStatus from '$components/GpuStatus.svelte';
  import AudioPlayer from '$components/AudioPlayer.svelte';
  import JobProgress from '$components/JobProgress.svelte';
  import ErrorBanner from '$components/ErrorBanner.svelte';
  import { models, modelsLoading, modelsError, refreshModels } from '$stores/models';
  import { recentJobs, addOrUpdateJob } from '$stores/jobs';
  import { generateTTS, getAudioUrl, pollJob, type TTSJob } from '$api/tts';
  import {
    listBuiltinVoices,
    listVoices,
    type BuiltinVoice,
    type VoiceProfile,
  } from '$api/voices';

  let selectedModel = $state('');
  let text = $state('');
  let selectedVoiceId: string | null = $state(null);
  let speed = $state(1.0);
  let language = $state('en');
  let modelExtras: Record<string, unknown> = $state({});

  let generating = $state(false);
  let currentJob: TTSJob | null = $state(null);
  let audioUrl = $state('');
  let audioDuration: number | null = $state(null);
  let errorMessage = $state('');

  let builtinVoices: BuiltinVoice[] = $state([]);
  let clonedVoices: VoiceProfile[] = $state([]);
  let voicesLoading = $state(false);

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

  let charCount = $derived(text.length);
  let canGenerate = $derived(!!selectedModel && !!text.trim() && !generating);
  let hasVoices = $derived(builtinVoices.length > 0 || clonedVoices.length > 0);
  let selectedModelInfo = $derived($models.find((m) => m.id === selectedModel));

  onMount(() => {
    refreshModels();
  });

  // Reload voices when selected model changes
  $effect(() => {
    if (selectedModel) {
      loadVoices(selectedModel);
    } else {
      builtinVoices = [];
      clonedVoices = [];
      selectedVoiceId = null;
    }
  });

  async function loadVoices(modelId: string): Promise<void> {
    voicesLoading = true;
    try {
      const [builtin, cloned] = await Promise.all([
        listBuiltinVoices(modelId).catch(() => []),
        listVoices(modelId)
          .then((r) => r.voices)
          .catch(() => []),
      ]);
      builtinVoices = builtin;
      clonedVoices = cloned;
      selectedVoiceId = null;
    } finally {
      voicesLoading = false;
    }
  }

  async function handleGenerate(): Promise<void> {
    if (!canGenerate) return;

    generating = true;
    errorMessage = '';
    audioUrl = '';
    audioDuration = null;
    currentJob = null;

    try {
      const resp = await generateTTS({
        model_id: selectedModel,
        text: text.trim(),
        voice_id: selectedVoiceId,
        speed,
        language,
        extra: modelExtras,
      });

      // Seed a minimal job object so the progress component can connect immediately
      currentJob = {
        id: resp.job_id,
        model_id: selectedModel,
        text: text.trim(),
        voice_id: selectedVoiceId,
        voice_profile_id: null,
        parameters: { speed, language, extra: modelExtras },
        status: 'pending',
        error_message: null,
        output_path: null,
        duration_seconds: null,
        processing_time_ms: null,
        created_at: new Date().toISOString(),
        completed_at: null,
      };
      addOrUpdateJob(currentJob);

      // WebSocket handles progress; fallback-poll in case WS fails
      await pollJob(resp.job_id, (job) => {
        currentJob = job;
        addOrUpdateJob(job);
      });
    } catch (err) {
      errorMessage = err instanceof Error ? err.message : 'Generation failed';
    } finally {
      generating = false;
    }
  }

  function handleProgressComplete(url: string, dur: number): void {
    audioUrl = url;
    audioDuration = dur;
    if (currentJob) currentJob = { ...currentJob, status: 'complete' };
  }

  function handleProgressError(msg: string): void {
    errorMessage = msg;
    generating = false;
  }

  function dismissError(): void {
    errorMessage = '';
  }
</script>

<div class="p-6 max-w-4xl mx-auto space-y-6">
  <div class="page-header">
    <h1 class="page-title">Text to Speech</h1>
    <p class="page-description">Generate speech from text using open-source models.</p>
  </div>

  <!-- Models loading error -->
  {#if $modelsError}
    <ErrorBanner message={$modelsError} onRetry={refreshModels} />
  {/if}

  <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
    <!-- Left: controls -->
    <div class="lg:col-span-2 space-y-4">
      <!-- Model selection -->
      <div class="card p-4 space-y-3">
        <h2 class="section-title text-sm">Model</h2>

        {#if $modelsLoading}
          <!-- Loading skeleton -->
          <div class="space-y-2 animate-pulse">
            <div class="h-10 bg-gray-200 dark:bg-[#1e1e22] rounded-lg"></div>
            <div class="h-16 bg-gray-100 dark:bg-[#18181b] rounded-lg"></div>
          </div>
        {:else if $models.length === 0 && !$modelsError}
          <div class="text-sm text-gray-500 dark:text-gray-500 py-4 text-center">
            <p>No models available.</p>
            <button onclick={refreshModels} class="btn-secondary mt-2 text-xs">
              Refresh models
            </button>
          </div>
        {:else}
          <ModelSelector models={$models} bind:value={selectedModel} disabled={generating} />
        {/if}
      </div>

      <!-- GPU Status -->
      <GpuStatus
        selectedModelVram={selectedModelInfo?.vram_gb_estimate ?? 0}
        {generating}
      />

      <!-- Text input -->
      <div class="card p-4 space-y-2">
        <label class="label" for="tts-text">Text</label>
        <textarea
          id="tts-text"
          bind:value={text}
          rows={5}
          placeholder="Enter the text you want to synthesize..."
          disabled={generating}
          class="input resize-none"
          maxlength={4096}
        ></textarea>
        <div class="text-xs text-gray-400 dark:text-gray-600 text-right">
          {charCount} / 4096
        </div>
      </div>

      <!-- Voice selection -->
      {#if hasVoices || voicesLoading}
        <div class="card p-4 space-y-2">
          <label class="label" for="voice-select">Voice</label>
          {#if voicesLoading}
            <div class="h-10 bg-gray-200 dark:bg-[#1e1e22] rounded-lg animate-pulse"></div>
          {:else}
            <select
              id="voice-select"
              bind:value={selectedVoiceId}
              disabled={generating}
              class="input"
            >
              <option value={null}>Default voice</option>
              {#if builtinVoices.length > 0}
                <optgroup label="Built-in voices">
                  {#each builtinVoices as v}
                    <option value={v.id}>
                      {v.name} ({v.language}{v.gender ? ', ' + v.gender : ''})
                    </option>
                  {/each}
                </optgroup>
              {/if}
              {#if clonedVoices.length > 0}
                <optgroup label="My cloned voices">
                  {#each clonedVoices as v}
                    <option value={v.id}>{v.name}</option>
                  {/each}
                </optgroup>
              {/if}
            </select>
          {/if}
        </div>
      {/if}

      <!-- Parameters -->
      <div class="card p-4 space-y-4">
        <h2 class="section-title text-sm">Parameters</h2>

        <!-- Language: all models -->
        <div>
          <label class="label" for="language">Language</label>
          <select id="language" bind:value={language} disabled={generating} class="input">
            {#each LANGUAGES as lang}
              <option value={lang.code}>{lang.name}</option>
            {/each}
          </select>
        </div>

        <!-- Speed: Kokoro only (only model that natively supports it) -->
        {#if selectedModel === 'kokoro'}
          <div>
            <label class="label" for="speed">
              Speed: {speed.toFixed(1)}x
              {#if speed === 1.0}<span class="label-hint">(default)</span>{/if}
            </label>
            <input
              id="speed"
              type="range"
              min="0.5"
              max="2.0"
              step="0.1"
              bind:value={speed}
              disabled={generating}
              class="w-full"
            />
          </div>
        {/if}

        <!-- Model-specific parameters -->
        <ModelParams modelId={selectedModel} disabled={generating} bind:extras={modelExtras} />
      </div>

      <!-- Generate button -->
      <button onclick={handleGenerate} disabled={!canGenerate} class="btn-primary w-full py-3 text-base">
        {#if generating}
          <span class="spinner-sm"></span>
          Generating...
        {:else}
          Generate Speech
        {/if}
      </button>
    </div>

    <!-- Right: result + history -->
    <div class="space-y-4">
      <!-- Result / Progress -->
      <div class="card p-4 space-y-3 overflow-hidden">
        <h2 class="section-title text-sm">Output</h2>

        {#if errorMessage}
          <ErrorBanner message={errorMessage} onDismiss={dismissError} />
        {/if}

        <!-- Live progress via WebSocket -->
        <JobProgress
          job={currentJob}
          onComplete={handleProgressComplete}
          onError={handleProgressError}
        />

        <!-- Audio player (shown once complete) -->
        <AudioPlayer src={audioUrl} duration={audioDuration} />

        {#if audioDuration}
          <p class="text-xs text-gray-400 dark:text-gray-600">
            Duration: {audioDuration.toFixed(1)}s
            {#if currentJob?.processing_time_ms}
              &middot; Generated in {(currentJob.processing_time_ms / 1000).toFixed(1)}s
            {/if}
          </p>
        {/if}
      </div>

      <!-- Job history -->
      <div class="card p-4 space-y-2">
        <h2 class="section-title text-sm">Recent Jobs</h2>
        {#if $recentJobs.length === 0}
          <p class="text-xs text-gray-400 dark:text-gray-600">No jobs yet.</p>
        {:else}
          <ul class="space-y-1.5">
            {#each $recentJobs.slice(0, 8) as job (job.id)}
              <li class="flex items-center gap-2 text-xs">
                <span
                  class="w-2 h-2 rounded-full flex-shrink-0
                    {job.status === 'complete'
                    ? 'bg-green-500'
                    : job.status === 'failed'
                      ? 'bg-red-500'
                      : job.status === 'running'
                        ? 'bg-yellow-500 animate-pulse'
                        : 'bg-gray-400'}"
                ></span>
                <span class="flex-1 truncate text-gray-600 dark:text-gray-300">
                  {job.text.slice(0, 40)}{job.text.length > 40 ? '...' : ''}
                </span>
                {#if job.status === 'complete'}
                  <a
                    href={getAudioUrl(job.id)}
                    class="text-primary-500 hover:underline flex-shrink-0"
                  >
                    play
                  </a>
                {/if}
              </li>
            {/each}
          </ul>
        {/if}
      </div>
    </div>
  </div>
</div>
