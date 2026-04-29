<!-- TTS Generation Page -->
<script lang="ts">
  import { onMount, tick } from 'svelte';
  import ModelSelector from '$components/ModelSelector.svelte';
  import ModelParams from '$components/ModelParams.svelte';
  import DialogueEditor from '$components/DialogueEditor.svelte';
  import GpuStatus from '$components/GpuStatus.svelte';
  import AudioPlayer from '$components/AudioPlayer.svelte';
  import JobProgress from '$components/JobProgress.svelte';
  import ErrorBanner from '$components/ErrorBanner.svelte';
  import { models, modelsLoading, modelsError, refreshModels } from '$stores/models';
  import { recentJobs, addOrUpdateJob } from '$stores/jobs';
  import { generateTTS, getAudioUrl, pollJob, cancelJob, type TTSJob } from '$api/tts';
  import {
    listBuiltinVoices,
    listVoices,
    type BuiltinVoice,
    type VoiceProfile,
  } from '$api/voices';
  import { addToast } from '$lib/stores/toasts';

  // Guard flag: prevents async callbacks from mutating state after component destruction.
  // Using $effect cleanup instead of onDestroy (Svelte 5 pattern).
  let destroyed = false;
  $effect(() => {
    return () => { destroyed = true; };
  });

  let selectedModel = $state('');
  let text = $state('');
  let selectedVoiceId: string | null = $state(null);
  let speed = $state(1.0);
  let language = $state('en');
  let modelExtras: Record<string, unknown> = $state({});
  let outputFormat = $state('wav');
  let textareaEl = $state<HTMLTextAreaElement | undefined>(undefined);
  let currentJobId: string | null = $state(null);

  let generating = $state(false);
  let currentJob: TTSJob | null = $state(null);
  let audioUrl = $state('');
  let audioDuration: number | null = $state(null);
  let errorMessage = $state('');
  let audioAutoplay = $state(false);

  // persist output format choice
  $effect(() => {
    localStorage.setItem('openspeakers:output_format', outputFormat);
  });
  let streamingActive = $state(false);
  let streamingChunkCount = $state(0);
  let streamingPaused = $state(false);

  let _audioCtx: AudioContext | null = null;
  let _nextAudioStart = 0;
  // Buffer chunks until we have STREAM_BUFFER_S seconds queued before starting playback
  const STREAM_BUFFER_S = 0.75;
  let _pendingChunks: Array<{ float32: Float32Array; sampleRate: number }> = [];
  let _pendingDuration = 0;
  let _streamPlaybackStarted = $state(false);

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

  let dialogueMode = $state(false);

  let charCount = $derived(text.length);
  let canGenerate = $derived(!!selectedModel && !!text.trim() && !generating);
  let hasVoices = $derived(builtinVoices.length > 0 || clonedVoices.length > 0);
  let selectedModelInfo = $derived(models.find((m) => m.id === selectedModel));

  // Persist selected model
  $effect(() => {
    if (selectedModel) localStorage.setItem('openspeakers:selected_model', selectedModel);
  });

  // Turn off dialogue mode when switching to a non-dialogue model
  $effect(() => {
    if (selectedModelInfo && !selectedModelInfo.supports_dialogue) {
      dialogueMode = false;
    }
  });

  // Auto-select first model once models load. Safe now — models is Svelte 5 $state,
  // so Svelte properly cleans up this effect when the component is destroyed.
  $effect(() => {
    if (!selectedModel && models.length > 0) {
      const stored = localStorage.getItem('openspeakers:selected_model');
      selectedModel = (stored && models.some((m) => m.id === stored)) ? stored : models[0].id;
    }
  });

  onMount(() => {
    const storedFormat = localStorage.getItem('openspeakers:output_format');
    if (storedFormat) outputFormat = storedFormat;
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
      if (destroyed) return;
      builtinVoices = builtin;
      clonedVoices = cloned;
      selectedVoiceId = null;
    } finally {
      if (!destroyed) voicesLoading = false;
    }
  }

  async function handleGenerate(): Promise<void> {
    if (!canGenerate) return;

    generating = true;
    errorMessage = '';
    audioUrl = '';
    audioDuration = null;
    audioAutoplay = false;
    currentJob = null;
    stopStreaming();
    // Create AudioContext during user gesture so browser allows playback
    _audioCtx = new AudioContext({ sampleRate: 24000 });
    _nextAudioStart = 0;

    try {
      const resp = await generateTTS({
        model_id: selectedModel,
        text: text.trim(),
        voice_id: selectedVoiceId,
        speed,
        language,
        extra: modelExtras,
        output_format: outputFormat,
      } as Parameters<typeof generateTTS>[0]);

      currentJobId = resp.job_id;
      addToast('success', 'Generation started');

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

      // pollJob is the source of truth. The WS is only for real-time progress bars.
      await pollJob(resp.job_id, (job) => {
        if (destroyed) return;
        currentJob = job;
        addOrUpdateJob(job);
        // Fire completion immediately when status changes — don't wait for WS.
        if (job.status === 'complete' && !audioUrl) {
          handleProgressComplete(getAudioUrl(job.id), job.duration_seconds ?? 0);
        }
      });
    } catch (err) {
      if (destroyed) return;
      const msg = err instanceof Error ? err.message : 'Generation failed';
      errorMessage = msg;
      addToast('error', msg);
    } finally {
      if (!destroyed) generating = false;
    }
  }

  function handleProgressComplete(url: string, dur: number): void {
    stopStreaming();
    audioUrl = url;
    audioDuration = dur;
    audioAutoplay = true;
    if (currentJob) currentJob = { ...currentJob, status: 'complete' };
  }

  function handleProgressError(msg: string): void {
    errorMessage = msg;
    generating = false;
  }

  function dismissError(): void {
    errorMessage = '';
  }

  function _scheduleChunk(float32: Float32Array, sampleRate: number): void {
    if (!_audioCtx) return;
    const buffer = _audioCtx.createBuffer(1, float32.length, sampleRate);
    // Copy chunk into the buffer's own channel data (avoids Float32Array<ArrayBuffer>
    // vs <ArrayBufferLike> type mismatch from lib.dom 2024+).
    buffer.getChannelData(0).set(float32);
    const source = _audioCtx.createBufferSource();
    source.buffer = buffer;
    source.connect(_audioCtx.destination);
    const startAt = Math.max(_audioCtx.currentTime + 0.02, _nextAudioStart);
    source.start(startAt);
    _nextAudioStart = startAt + buffer.duration;
  }

  function handleChunk(data: string, sampleRate: number, index: number): void {
    if (!_audioCtx) return;
    if (_audioCtx.state === 'suspended') _audioCtx.resume();
    if (!streamingActive) streamingActive = true;
    streamingChunkCount = index + 1;

    // Decode base64 → Uint8Array → Int16Array → Float32Array
    const binary = atob(data);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
    const pcm16 = new Int16Array(bytes.buffer);
    const float32 = new Float32Array(pcm16.length);
    for (let i = 0; i < pcm16.length; i++) float32[i] = pcm16[i] / 32767;

    if (_streamPlaybackStarted) {
      _scheduleChunk(float32, sampleRate);
    } else {
      _pendingDuration += float32.length / sampleRate;
      _pendingChunks.push({ float32, sampleRate });
      if (_pendingDuration >= STREAM_BUFFER_S) {
        _streamPlaybackStarted = true;
        _nextAudioStart = _audioCtx.currentTime + 0.05;
        for (const chunk of _pendingChunks) _scheduleChunk(chunk.float32, chunk.sampleRate);
        _pendingChunks = [];
      }
    }
  }

  function toggleStreamingPlayback(): void {
    if (!_audioCtx) return;
    if (_audioCtx.state === 'running') {
      _audioCtx.suspend();
      streamingPaused = true;
    } else {
      _audioCtx.resume();
      streamingPaused = false;
    }
  }

  function stopStreaming(): void {
    // Release reference without closing — already-scheduled chunks finish playing naturally.
    _audioCtx = null;
    _nextAudioStart = 0;
    _pendingChunks = [];
    _pendingDuration = 0;
    _streamPlaybackStarted = false;
    streamingActive = false;
    streamingChunkCount = 0;
    streamingPaused = false;
  }

  function loadRecentJob(job: TTSJob): void {
    audioUrl = getAudioUrl(job.id);
    audioDuration = job.duration_seconds;
    currentJob = job;
    audioAutoplay = true;
  }
</script>

<svelte:head>
  <title>Text to Speech | OpenSpeakers</title>
</svelte:head>

<svelte:window onkeydown={(e) => {
  if (e.ctrlKey && e.key === 'Enter' && !generating) handleGenerate();
}} />

<div class="p-6 max-w-4xl mx-auto space-y-6">
  <div class="page-header">
    <h1 class="page-title">Text to Speech</h1>
    <p class="page-description">Generate speech from text using open-source models.</p>
  </div>

  <!-- Models loading error -->
  {#if modelsError()}
    <ErrorBanner message={modelsError()} onRetry={refreshModels} />
  {/if}

  <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
    <!-- Left: controls -->
    <div class="lg:col-span-2 space-y-4">
      <!-- Model selection -->
      <div class="card p-4 space-y-3">
        <h2 class="section-title text-sm">Model</h2>

        {#if modelsLoading()}
          <!-- Loading skeleton -->
          <div class="space-y-2 animate-pulse">
            <div class="h-10 bg-gray-200 dark:bg-[#1e1e22] rounded-lg"></div>
            <div class="h-16 bg-gray-100 dark:bg-[#18181b] rounded-lg"></div>
          </div>
        {:else if models.length === 0 && !modelsError()}
          <div class="text-sm text-gray-500 dark:text-gray-400 py-4 text-center">
            <p>No models available.</p>
            <button onclick={refreshModels} class="btn-secondary mt-2 text-xs">
              Refresh models
            </button>
          </div>
        {:else}
          <ModelSelector models={models} bind:value={selectedModel} disabled={generating} />
        {/if}
      </div>

      <!-- GPU Status -->
      <GpuStatus
        selectedModelVram={selectedModelInfo?.vram_gb_estimate ?? 0}
        {generating}
      />

      <!-- Text input -->
      <div class="card p-4 space-y-2">
        <div class="flex items-center justify-between">
          <label class="label" for="tts-text">Text</label>
          {#if selectedModelInfo?.supports_dialogue}
            <label class="flex items-center gap-2 text-xs text-gray-400 cursor-pointer select-none">
              <input type="checkbox" bind:checked={dialogueMode} disabled={generating} class="accent-amber-500" />
              Dialogue mode
            </label>
          {/if}
        </div>

        {#if dialogueMode && selectedModelInfo?.supports_dialogue}
          <DialogueEditor
            dialogueFormat={selectedModelInfo.dialogue_format}
            bind:value={text}
            disabled={generating}
          />
        {:else}
          <textarea
            id="tts-text"
            bind:this={textareaEl}
            bind:value={text}
            rows={5}
            placeholder="Enter the text you want to synthesize... (Ctrl+Enter to generate)"
            disabled={generating}
            class="input resize-none"
            maxlength={4096}
          ></textarea>
        {/if}
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
                    <option value={v.id}>
                      {v.name} {v.reference_text ? '— ✓ Transcript' : '— ⚠ No transcript'}
                    </option>
                  {/each}
                </optgroup>
              {/if}
            </select>
            <!-- Transcript-state hint for the currently selected cloned voice -->
            {#if selectedVoiceId}
              {@const sel = clonedVoices.find((v) => v.id === selectedVoiceId)}
              {#if sel}
                {#if sel.reference_text && sel.reference_text.length > 0}
                  <p class="text-xs mt-1 text-green-600 dark:text-green-400">
                    ✓ Transcript ready — better cloning quality
                  </p>
                {:else}
                  <p class="text-xs mt-1 text-amber-600 dark:text-amber-400">
                    ⚠ No transcript on this voice profile —
                    <a href="/clone" class="underline hover:text-amber-500">add one on the Clone page</a>
                    for higher cloning fidelity.
                  </p>
                {/if}
              {/if}
            {/if}
          {/if}
        </div>
      {/if}

      <!-- Parameters -->
      <div class="card p-4 space-y-4">
        <h2 class="section-title text-sm">Parameters</h2>

        <!-- Language and output format row -->
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div>
            <label class="label" for="language">Language</label>
            <select id="language" bind:value={language} disabled={generating} class="input">
              {#each LANGUAGES as lang}
                <option value={lang.code}>{lang.name}</option>
              {/each}
            </select>
          </div>
          <div>
            <label class="label" for="output-format">Output Format</label>
            <select id="output-format" bind:value={outputFormat} disabled={generating} class="input">
              <option value="wav">WAV (lossless)</option>
              <option value="mp3">MP3</option>
              <option value="ogg">OGG</option>
            </select>
          </div>
        </div>

        <!-- Speed: only when model supports it -->
        {#if selectedModelInfo?.supports_speed === true}
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

        <!-- Pitch: only when model supports it -->
        {#if selectedModelInfo?.supports_pitch === true}
          <div>
            <label class="label" for="pitch">
              Pitch: {(modelExtras.pitch as number ?? 0).toFixed(1)}
              {#if (modelExtras.pitch as number ?? 0) === 0}<span class="label-hint">(default)</span>{/if}
            </label>
            <input
              id="pitch"
              type="range"
              min="-12"
              max="12"
              step="0.5"
              value={modelExtras.pitch as number ?? 0}
              oninput={(e) => { modelExtras = { ...modelExtras, pitch: parseFloat((e.currentTarget as HTMLInputElement).value) }; }}
              disabled={generating}
              class="w-full"
            />
          </div>
        {/if}

        <!-- Model-specific parameters -->
        <ModelParams
          modelId={selectedModel}
          model={selectedModelInfo}
          disabled={generating}
          bind:extras={modelExtras}
          onInsertTag={(tag: string) => {
            const el = textareaEl;
            if (el) {
              const start = el.selectionStart ?? el.value.length;
              const end = el.selectionEnd ?? start;
              const newText = text.slice(0, start) + tag + text.slice(end);
              text = newText;
              tick().then(() => { el.selectionStart = el.selectionEnd = start + tag.length; });
            } else {
              text = text + tag;
            }
          }}
        />
      </div>

      <!-- Generate button -->
      <button onclick={handleGenerate} disabled={!canGenerate} class="btn-primary w-full py-3 text-base" aria-label={generating ? 'Generating speech...' : 'Generate speech from text'}>
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
          <ErrorBanner message={errorMessage} onDismiss={dismissError} onRetry={handleGenerate} />
        {/if}

        <!-- Live progress via WebSocket -->
        <JobProgress
          job={currentJob}
          onComplete={handleProgressComplete}
          onError={handleProgressError}
          onChunk={handleChunk}
          onCancel={async () => {
            if (!currentJobId) return;
            try {
              await cancelJob(currentJobId);
              addToast('info', 'Job cancelled');
              generating = false;
              currentJobId = null;
              currentJob = null;
            } catch {
              addToast('error', 'Failed to cancel job');
            }
          }}
        />

        <!-- Streaming audio player (shown while chunks arrive, before full WAV is ready) -->
        {#if streamingActive && !audioUrl}
          <div class="flex items-center gap-3">
            <!-- Play/Pause button -->
            <button
              onclick={toggleStreamingPlayback}
              class="flex-shrink-0 w-9 h-9 flex items-center justify-center rounded-full
                     bg-primary-600 hover:bg-primary-700 text-white transition-colors"
              aria-label={streamingPaused ? 'Resume' : 'Pause'}
            >
              {#if streamingPaused}
                <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
                  <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM9.555 7.168A1 1 0 008 8v4a1 1 0 001.555.832l3-2a1 1 0 000-1.664l-3-2z" clip-rule="evenodd" />
                </svg>
              {:else}
                <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
                  <path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zM7 8a1 1 0 012 0v4a1 1 0 11-2 0V8zm5-1a1 1 0 00-1 1v4a1 1 0 102 0V8a1 1 0 00-1-1z" clip-rule="evenodd" />
                </svg>
              {/if}
            </button>
            <!-- Waveform animation -->
            <div class="flex-1 flex items-center gap-0.5 h-6">
              {#each Array(20) as _, i}
                <div
                  class="flex-1 rounded-full bg-primary-400 dark:bg-primary-500 transition-all"
                  class:animate-pulse={!streamingPaused}
                  style="height: {streamingPaused ? '3px' : `${8 + Math.sin(i * 0.9) * 6}px`}; animation-delay: {i * 50}ms"
                ></div>
              {/each}
            </div>
            <!-- Status -->
            <span class="text-xs text-gray-500 dark:text-gray-400 flex-shrink-0 tabular-nums">
              {streamingPaused ? 'Paused' : _streamPlaybackStarted ? 'Playing' : 'Buffering…'}
            </span>
          </div>
        {/if}

        <!-- Audio player (shown once complete) -->
        <AudioPlayer src={audioUrl} duration={audioDuration} autoplay={audioAutoplay} />

        <!-- Speaker similarity badge (Phase 5) -->
        {#if currentJob?.status === 'complete' && currentJob.speaker_similarity != null}
          {@const score = currentJob.speaker_similarity}
          {@const tier =
            score >= 0.5
              ? 'bg-green-100 text-green-800 dark:bg-green-500/15 dark:text-green-300'
              : score >= 0.3
                ? 'bg-amber-100 text-amber-800 dark:bg-amber-500/15 dark:text-amber-300'
                : 'bg-red-100 text-red-800 dark:bg-red-500/15 dark:text-red-300'}
          {@const tierLabel = score >= 0.5 ? 'good match' : score >= 0.3 ? 'fair match' : 'weak match'}
          <div class="flex items-center gap-2">
            <span
              class="inline-flex items-center text-xs px-2 py-1 rounded-full font-medium {tier}"
              title="Cosine similarity between the generated audio and the reference voice (range -1 to 1; ≥0.5 typically means same speaker)"
              aria-label={`Voice match score ${score.toFixed(2)} out of 1.0 — ${tierLabel} to the reference voice`}
            >
              Voice match: {score.toFixed(2)}
            </span>
          </div>
        {/if}

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
        <div class="flex items-center justify-between">
          <h2 class="section-title text-sm">Recent Jobs</h2>
          <a href="/history" class="text-xs text-primary-500 hover:text-primary-400 transition-colors">View all →</a>
        </div>
        {#if recentJobs.length === 0}
          <p class="text-xs text-gray-400 dark:text-gray-600">No jobs yet.</p>
        {:else}
          <ul class="space-y-1.5">
            {#each recentJobs.slice(0, 8) as job (job.id)}
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
                  <button
                    onclick={() => loadRecentJob(job)}
                    class="text-primary-500 hover:underline flex-shrink-0"
                  >
                    ▶ play
                  </button>
                {/if}
              </li>
            {/each}
          </ul>
        {/if}
      </div>
    </div>
  </div>
</div>
