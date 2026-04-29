<!-- Voice Cloning Page -->
<script lang="ts">
  import { onMount } from 'svelte';
  import ModelSelector from '$components/ModelSelector.svelte';
  import AudioPlayer from '$components/AudioPlayer.svelte';
  import WaveformPreview from '$components/WaveformPreview.svelte';
  import ErrorBanner from '$components/ErrorBanner.svelte';
  import { voiceCloningModels, refreshModels } from '$stores/models';
  import {
    createVoiceProfile,
    listVoices,
    deleteVoiceProfile,
    updateVoice,
    getVoice,
    transcribeVoice,
    updateVoiceTranscript,
    getVoiceAudioUrl,
    type VoiceProfile,
  } from '$api/voices';
  import { generateTTS, getAudioUrl, pollJob } from '$api/tts';
  import { addToast } from '$lib/stores/toasts';

  // Form state
  let selectedModel = $state('');
  let voiceName = $state('');
  let referenceFile: File | null = $state(null);
  let referenceAudioPreview = $state('');
  let uploading = $state(false);
  let uploadError = $state('');
  let isDragging = $state(false);
  let fileInputEl: HTMLInputElement;

  // Inline rename state
  let editingVoiceId = $state<string | null>(null);
  let editingName = $state('');

  // Saved voices
  let clonedVoices: VoiceProfile[] = $state([]);
  let loadingVoices = $state(false);
  let loadVoicesError = $state('');

  // Just-created profile (for the inline transcript editor)
  let createdVoice: VoiceProfile | null = $state(null);
  // Transcript-edit state for the just-created voice
  let transcriptDraft = $state('');
  let transcriptSaving = $state(false);
  let transcriptError = $state('');
  // Polling tracking — only one in flight at a time. The interval is created
  // inside an $effect so its cleanup runs on unmount or when we replace the
  // active voice id.
  let pollingVoiceId = $state<string | null>(null);
  let pollingStartedAt = $state<number>(0);

  // Preview generation
  let previewText = $state('Hello, this is a test of my cloned voice.');
  let previewAudioUrl = $state('');
  let previewVoiceId: string | null = $state(null);
  let generatingPreview = $state(false);
  let previewError = $state('');

  // Derived helpers
  let canCreate = $derived(
    !!selectedModel && !!voiceName.trim() && !!referenceFile && !uploading
  );

  let fileInfo = $derived.by(() => {
    if (!referenceFile) return null;
    const sizeMB = (referenceFile.size / (1024 * 1024)).toFixed(2);
    const ext = referenceFile.name.split('.').pop()?.toUpperCase() ?? 'Unknown';
    return { name: referenceFile.name, sizeMB, ext };
  });

  // Reload voices when selected model changes
  $effect(() => {
    if (selectedModel) {
      loadVoices();
    }
  });

  // Polling effect: while pollingVoiceId is set, GET /voices/{id} every 1 s
  // and stop as soon as status leaves "pending" (or 30 s elapse).
  $effect(() => {
    const id = pollingVoiceId;
    if (!id) return;
    const startedAt = pollingStartedAt;
    let cancelled = false;
    const handle = setInterval(async () => {
      if (cancelled) return;
      try {
        const fresh = await getVoice(id);
        if (cancelled) return;
        // Update the just-created card and the saved-voices list.
        if (createdVoice && createdVoice.id === id) {
          createdVoice = fresh;
          if (fresh.reference_text_status !== 'pending') {
            transcriptDraft = fresh.reference_text ?? '';
          }
        }
        clonedVoices = clonedVoices.map((v) => (v.id === id ? fresh : v));
        if (fresh.reference_text_status !== 'pending') {
          pollingVoiceId = null;
        } else if (Date.now() - startedAt > 30_000) {
          pollingVoiceId = null;
        }
      } catch {
        // Transient error — keep polling until the timeout elapses.
        if (Date.now() - startedAt > 30_000) {
          pollingVoiceId = null;
        }
      }
    }, 1000);
    return () => {
      cancelled = true;
      clearInterval(handle);
    };
  });

  // Debounced PATCH for transcript edits.
  let transcriptDebounceHandle: ReturnType<typeof setTimeout> | null = null;
  $effect(() => {
    return () => {
      if (transcriptDebounceHandle !== null) clearTimeout(transcriptDebounceHandle);
    };
  });

  // Strip control chars (≤0x1F) except \n, \t, \r — guards against pasted
  // garbage from word processors.
  function sanitizeTranscript(value: string): string {
    let out = '';
    for (const ch of value) {
      const code = ch.charCodeAt(0);
      if (code <= 0x1f && ch !== '\n' && ch !== '\t' && ch !== '\r') continue;
      out += ch;
    }
    return out;
  }

  function handleTranscriptInput(e: Event): void {
    if (!createdVoice) return;
    const raw = (e.currentTarget as HTMLTextAreaElement).value;
    const sanitized = sanitizeTranscript(raw);
    if (sanitized !== raw) {
      // Keep the textarea visually in sync with what we'll send.
      (e.currentTarget as HTMLTextAreaElement).value = sanitized;
    }
    transcriptDraft = sanitized;
    transcriptError = '';

    if (transcriptDebounceHandle !== null) clearTimeout(transcriptDebounceHandle);
    const voiceId = createdVoice.id;
    transcriptDebounceHandle = setTimeout(async () => {
      transcriptSaving = true;
      try {
        const updated = await updateVoiceTranscript(voiceId, transcriptDraft);
        if (createdVoice && createdVoice.id === voiceId) {
          createdVoice = updated;
        }
        clonedVoices = clonedVoices.map((v) => (v.id === voiceId ? updated : v));
      } catch (err) {
        transcriptError = err instanceof Error ? err.message : 'Failed to save transcript';
      } finally {
        transcriptSaving = false;
      }
    }, 500);
  }

  async function handleRetranscribe(): Promise<void> {
    if (!createdVoice) return;
    const voiceId = createdVoice.id;
    transcriptError = '';
    try {
      const updated = await transcribeVoice(voiceId);
      createdVoice = updated;
      clonedVoices = clonedVoices.map((v) => (v.id === voiceId ? updated : v));
      transcriptDraft = '';
      pollingVoiceId = voiceId;
      pollingStartedAt = Date.now();
      addToast('info', 'Re-transcribing reference audio…');
    } catch (err) {
      transcriptError = err instanceof Error ? err.message : 'Failed to re-transcribe';
    }
  }

  onMount(async () => {
    await refreshModels();
    if (voiceCloningModels().length > 0 && !selectedModel) {
      selectedModel = voiceCloningModels()[0].id;
    }
    await loadVoices();
  });

  async function loadVoices(): Promise<void> {
    loadingVoices = true;
    loadVoicesError = '';
    try {
      const result = await listVoices(selectedModel || undefined);
      clonedVoices = result.voices;
    } catch (err) {
      loadVoicesError = err instanceof Error ? err.message : 'Failed to load voices';
    } finally {
      loadingVoices = false;
    }
  }

  function handleFile(file: File | null | undefined): void {
    if (!file) return;
    uploadError = '';
    if (file.size > 50 * 1024 * 1024) {
      uploadError = 'File too large. Maximum size is 50 MB.';
      referenceFile = null;
      referenceAudioPreview = '';
      return;
    }
    referenceFile = file;
    referenceAudioPreview = URL.createObjectURL(file);
  }

  function handleFileChange(e: Event): void {
    const input = e.currentTarget as HTMLInputElement;
    handleFile(input.files?.[0]);
  }

  function startEdit(voice: VoiceProfile): void {
    editingVoiceId = voice.id;
    editingName = voice.name;
  }

  async function saveEdit(voiceId: string): Promise<void> {
    try {
      const updated = await updateVoice(voiceId, { name: editingName });
      clonedVoices = clonedVoices.map((v) => (v.id === voiceId ? updated : v));
      if (createdVoice && createdVoice.id === voiceId) createdVoice = updated;
      editingVoiceId = null;
      addToast('success', 'Voice renamed');
    } catch {
      addToast('error', 'Failed to rename voice');
    }
  }

  async function handleCreate(): Promise<void> {
    if (!canCreate) return;
    uploading = true;
    uploadError = '';
    try {
      const profile = await createVoiceProfile(voiceName.trim(), selectedModel, referenceFile!);
      clonedVoices = [profile, ...clonedVoices];
      createdVoice = profile;
      transcriptDraft = profile.reference_text ?? '';
      transcriptError = '';
      // Start polling for the auto-transcript only if the server hasn't
      // already settled (e.g. user supplied a manual transcript via API).
      if (profile.reference_text_status === 'pending') {
        pollingVoiceId = profile.id;
        pollingStartedAt = Date.now();
      }
      // Reset form
      voiceName = '';
      referenceFile = null;
      referenceAudioPreview = '';
      addToast('success', `Voice "${profile.name}" created`);
    } catch (err) {
      uploadError = err instanceof Error ? err.message : 'Upload failed. Please try again.';
      addToast('error', uploadError);
    } finally {
      uploading = false;
    }
  }

  async function handleDelete(voiceId: string): Promise<void> {
    if (!confirm('Delete this voice profile? This cannot be undone.')) return;
    try {
      await deleteVoiceProfile(voiceId);
      const deleted = clonedVoices.find((v) => v.id === voiceId);
      clonedVoices = clonedVoices.filter((v) => v.id !== voiceId);
      if (createdVoice && createdVoice.id === voiceId) {
        createdVoice = null;
        pollingVoiceId = null;
      }
      // Clear preview if the deleted voice was being previewed
      if (previewVoiceId === voiceId) {
        previewAudioUrl = '';
        previewVoiceId = null;
      }
      addToast('info', `Voice "${deleted?.name ?? voiceId}" deleted`);
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to delete voice profile';
      uploadError = msg;
      addToast('error', msg);
    }
  }

  async function handlePreview(voice: VoiceProfile): Promise<void> {
    if (generatingPreview) return;
    if (!previewText.trim()) {
      previewError = 'Enter some preview text first.';
      return;
    }
    generatingPreview = true;
    previewVoiceId = voice.id;
    previewAudioUrl = '';
    previewError = '';
    try {
      const resp = await generateTTS({
        model_id: voice.model_id,
        text: previewText.trim(),
        voice_id: voice.id,
      });
      const finalJob = await pollJob(resp.job_id, () => {});
      if (finalJob.status === 'complete') {
        previewAudioUrl = getAudioUrl(finalJob.id);
      } else {
        previewError = finalJob.error_message ?? 'Preview generation failed';
      }
    } catch (err) {
      previewError = err instanceof Error ? err.message : 'Preview generation failed';
    } finally {
      generatingPreview = false;
    }
  }

  function formatDate(iso: string): string {
    return new Date(iso).toLocaleDateString(undefined, {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    });
  }

  // Badge styling for transcript state.
  function transcriptBadgeClass(status: VoiceProfile['reference_text_status']): string {
    switch (status) {
      case 'ready':
        return 'bg-green-100 text-green-700 dark:bg-green-500/15 dark:text-green-300';
      case 'pending':
        return 'bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300';
      case 'failed':
        return 'bg-red-100 text-red-700 dark:bg-red-500/15 dark:text-red-300';
      case 'manual':
        return 'bg-blue-100 text-blue-700 dark:bg-blue-500/15 dark:text-blue-300';
      default:
        return 'bg-gray-100 text-gray-600 dark:bg-gray-500/15 dark:text-gray-300';
    }
  }

  function transcriptBadgeLabel(status: VoiceProfile['reference_text_status']): string {
    switch (status) {
      case 'ready':
        return '✓ Transcribed';
      case 'pending':
        return 'Transcribing…';
      case 'failed':
        return '⚠ Needs transcript';
      case 'manual':
        return '✎ Edited';
      default:
        return status;
    }
  }
</script>

<svelte:head>
  <title>Voice Cloning | OpenSpeakers</title>
</svelte:head>

<div class="p-6 max-w-3xl mx-auto space-y-6">
  <!-- Page header -->
  <div class="page-header">
    <h1 class="page-title">Voice Cloning</h1>
    <p class="page-description">
      Upload reference audio to create a reusable cloned voice profile.
    </p>
  </div>

  <!-- Info banner -->
  <div
    class="flex items-start gap-3 p-4 rounded-xl border
           bg-sky-50 border-sky-200 text-sky-800
           dark:bg-sky-500/10 dark:border-sky-500/20 dark:text-sky-300"
  >
    <svg
      class="w-5 h-5 flex-shrink-0 mt-0.5 text-sky-500 dark:text-sky-400"
      fill="none"
      stroke="currentColor"
      viewBox="0 0 24 24"
    >
      <path
        stroke-linecap="round"
        stroke-linejoin="round"
        stroke-width="2"
        d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
      />
    </svg>
    <div class="text-sm leading-relaxed">
      <p class="font-medium">Voice cloning requires a compatible model</p>
      <p class="mt-1 text-sky-700 dark:text-sky-400/80">
        Currently supported: <strong>Fish Audio S2-Pro</strong>, <strong>VibeVoice 1.5B</strong>,
        <strong>Qwen3 TTS</strong>, <strong>F5-TTS</strong>, <strong>Chatterbox</strong>,
        <strong>CosyVoice 2.0</strong>, and <strong>Dia 1.6B</strong>.
        Upload <strong>5-30 seconds</strong> of clean speech for best results. Avoid background noise or music.
      </p>
    </div>
  </div>

  <!-- Create new voice -->
  <div class="card p-5 space-y-4">
    <h2 class="section-title">Clone a New Voice</h2>

    <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
      <div>
        <label class="label" for="voice-name">Voice name</label>
        <input
          id="voice-name"
          type="text"
          bind:value={voiceName}
          placeholder="e.g. My Voice"
          class="input"
          disabled={uploading}
          maxlength={100}
        />
      </div>
      <div>
        <!-- svelte-ignore a11y_label_has_associated_control -->
        <label class="label">Model</label>
        <ModelSelector
          models={voiceCloningModels()}
          bind:value={selectedModel}
          disabled={uploading}
        />
      </div>
    </div>

    <!-- File upload — drag-and-drop zone -->
    <div>
      <!-- svelte-ignore a11y_label_has_associated_control -->
      <label class="label">
        Reference audio
        <span class="label-hint">(WAV / MP3 / FLAC / M4A / OGG, 5-30 sec recommended)</span>
      </label>
      <div
        class="border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-all duration-200"
        class:border-primary-400={isDragging}
        class:bg-primary-900={isDragging}
        class:border-gray-600={!isDragging}
        role="button"
        tabindex="0"
        aria-label="Upload reference audio file"
        ondragover={(e) => { e.preventDefault(); isDragging = true; }}
        ondragleave={() => { isDragging = false; }}
        ondrop={(e) => { e.preventDefault(); isDragging = false; handleFile(e.dataTransfer?.files[0]); }}
        onclick={() => fileInputEl.click()}
        onkeydown={(e) => (e.key === 'Enter' || e.key === ' ') && fileInputEl.click()}
      >
        <input
          bind:this={fileInputEl}
          type="file"
          class="hidden"
          accept=".wav,.mp3,.flac,.ogg,.m4a,.aac,audio/wav,audio/mpeg,audio/flac,audio/ogg,audio/mp4,audio/x-m4a"
          disabled={uploading}
          onchange={handleFileChange}
        />
        {#if referenceFile}
          <p class="font-medium text-white">{referenceFile.name}</p>
          <p class="text-sm text-gray-400">{(referenceFile.size / 1024 / 1024).toFixed(2)} MB</p>
          <p class="text-xs text-gray-500 mt-1">Click or drop to replace</p>
        {:else}
          <div class="text-gray-400">
            <svg class="w-10 h-10 mx-auto mb-3 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
            </svg>
            <p class="text-base">Drop audio file here or click to browse</p>
            <p class="text-xs mt-1 text-gray-500">WAV, MP3, FLAC, OGG, M4A · Max 50 MB</p>
          </div>
        {/if}
      </div>
    </div>

    <!-- File info -->
    {#if fileInfo}
      <div
        class="flex items-center gap-3 p-3 rounded-lg text-sm
               bg-gray-50 dark:bg-white/[0.04]
               border border-gray-200 dark:border-[#2a2a2f]"
      >
        <svg
          class="w-5 h-5 flex-shrink-0 text-gray-400"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            stroke-linecap="round"
            stroke-linejoin="round"
            stroke-width="2"
            d="M9 19V6l12-3v13M9 19c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zm12-3c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zM9 10l12-3"
          />
        </svg>
        <div class="flex-1 min-w-0">
          <p class="font-medium text-gray-700 dark:text-gray-300 truncate">{fileInfo.name}</p>
          <p class="text-xs text-gray-400">{fileInfo.ext} &middot; {fileInfo.sizeMB} MB</p>
        </div>
      </div>
    {/if}

    <!-- Audio preview -->
    {#if referenceAudioPreview}
      <div>
        <p class="label">Preview reference audio</p>
        <AudioPlayer src={referenceAudioPreview} />
      </div>
    {/if}

    <!-- Upload error -->
    {#if uploadError}
      <ErrorBanner message={uploadError} onDismiss={() => (uploadError = '')} />
    {/if}

    <!-- Create button -->
    <button onclick={handleCreate} disabled={!canCreate} class="btn-primary w-full sm:w-auto">
      {#if uploading}
        <svg class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
          <circle
            class="opacity-25"
            cx="12"
            cy="12"
            r="10"
            stroke="currentColor"
            stroke-width="4"
          />
          <path
            class="opacity-75"
            fill="currentColor"
            d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
          />
        </svg>
        Creating voice...
      {:else}
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path
            stroke-linecap="round"
            stroke-linejoin="round"
            stroke-width="2"
            d="M12 4v16m8-8H4"
          />
        </svg>
        Create Voice Profile
      {/if}
    </button>
  </div>

  <!-- Just-created voice + transcript editor -->
  {#if createdVoice}
    <div class="card p-5 space-y-3">
      <div class="flex items-center justify-between gap-2 flex-wrap">
        <h2 class="section-title">Voice profile created</h2>
        <span
          class="text-xs px-2 py-0.5 rounded-full font-medium {transcriptBadgeClass(createdVoice.reference_text_status)}"
        >
          {transcriptBadgeLabel(createdVoice.reference_text_status)}
        </span>
      </div>

      <p class="text-sm text-gray-600 dark:text-gray-400">
        <span class="font-medium text-gray-800 dark:text-gray-200">{createdVoice.name}</span>
        &middot; <span class="font-mono text-xs">{createdVoice.model_id}</span>
      </p>

      {#if createdVoice.reference_text_status === 'pending'}
        <div class="flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400" aria-live="polite">
          <div class="spinner-sm"></div>
          <span>Transcribing reference…</span>
        </div>
      {:else}
        {#if createdVoice.reference_text_status === 'failed'}
          <ErrorBanner
            message="We couldn't auto-transcribe — please type what's spoken in the reference audio."
            onDismiss={() => {}}
          />
        {/if}

        <div>
          <div class="flex items-center justify-between gap-2 flex-wrap">
            <label class="label" for="reference-text-{createdVoice.id}">
              Reference transcript (auto-detected)
              {#if createdVoice.reference_text_status === 'manual'}
                <span class="label-hint">— Manually entered</span>
              {/if}
            </label>
            {#if transcriptSaving}
              <span class="text-xs text-gray-400 dark:text-gray-500">Saving…</span>
            {/if}
          </div>
          <textarea
            id="reference-text-{createdVoice.id}"
            class="input resize-none"
            rows={4}
            maxlength={4000}
            value={transcriptDraft}
            oninput={handleTranscriptInput}
            aria-describedby="ref-text-hint-{createdVoice.id}"
            aria-invalid={createdVoice.reference_text_status === 'failed' || !!transcriptError}
            placeholder={createdVoice.reference_text_status === 'failed'
              ? 'Type what is spoken in the reference audio'
              : 'Auto-detected transcript will appear here'}
          ></textarea>
          <p id="ref-text-hint-{createdVoice.id}" class="text-xs text-gray-500 dark:text-gray-400 mt-1">
            We transcribed your reference audio automatically. Edit if you spot errors. Detected language:
            <code class="font-mono">{createdVoice.reference_language ?? '?'}</code>
          </p>
          {#if transcriptError}
            <p class="text-xs text-red-500 dark:text-red-400 mt-1" role="alert">{transcriptError}</p>
          {/if}
        </div>

        <div class="flex flex-wrap gap-2">
          <button
            type="button"
            class="btn-secondary text-xs px-3 py-1.5"
            onclick={handleRetranscribe}
          >
            Re-transcribe
          </button>
          <button
            type="button"
            class="btn-secondary text-xs px-3 py-1.5"
            onclick={() => (createdVoice = null)}
          >
            Done
          </button>
        </div>
      {/if}
    </div>
  {/if}

  <!-- Saved voices -->
  <div class="card p-5 space-y-4">
    <div class="flex items-center justify-between">
      <h2 class="section-title">Saved Voices</h2>
      {#if clonedVoices.length > 0}
        <span class="text-xs text-gray-400">
          {clonedVoices.length} voice{clonedVoices.length === 1 ? '' : 's'}
        </span>
      {/if}
    </div>

    {#if loadingVoices}
      <div class="flex items-center gap-3 py-6 justify-center">
        <div class="spinner-sm"></div>
        <span class="text-sm text-gray-400">Loading voices...</span>
      </div>
    {:else if loadVoicesError}
      <ErrorBanner message={loadVoicesError} onRetry={loadVoices} />
    {:else if clonedVoices.length === 0}
      <div class="text-center py-8">
        <svg
          class="w-10 h-10 mx-auto text-gray-300 dark:text-gray-600 mb-3"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            stroke-linecap="round"
            stroke-linejoin="round"
            stroke-width="1.5"
            d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z"
          />
        </svg>
        <p class="text-sm text-gray-500 dark:text-gray-400">
          No cloned voices yet. Upload reference audio above to create one.
        </p>
      </div>
    {:else}
      <!-- Preview text input -->
      <div>
        <label class="label" for="preview-text">Preview text</label>
        <input
          id="preview-text"
          type="text"
          bind:value={previewText}
          class="input"
          placeholder="Text to preview with each voice"
          maxlength={500}
        />
      </div>

      {#if previewError}
        <ErrorBanner message={previewError} onDismiss={() => (previewError = '')} />
      {/if}

      <ul class="divide-y divide-gray-100 dark:divide-gray-700/50">
        {#each clonedVoices as voice (voice.id)}
          <li class="py-4 flex items-start gap-3">
            <!-- Voice icon -->
            <div
              class="mt-0.5 flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center
                     bg-teal-100 dark:bg-teal-500/15"
            >
              <svg
                class="w-4 h-4 text-teal-600 dark:text-teal-400"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  stroke-linecap="round"
                  stroke-linejoin="round"
                  stroke-width="2"
                  d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z"
                />
              </svg>
            </div>

            <div class="flex-1 min-w-0">
              <div class="flex items-center gap-2 flex-wrap">
                {#if editingVoiceId === voice.id}
                  <!-- svelte-ignore a11y_autofocus -->
                  <input
                    type="text"
                    bind:value={editingName}
                    class="input text-sm py-0.5 px-2 w-40"
                    onblur={() => saveEdit(voice.id)}
                    onkeydown={(e) => {
                      if (e.key === 'Enter') saveEdit(voice.id);
                      if (e.key === 'Escape') editingVoiceId = null;
                    }}
                    autofocus
                  />
                {:else}
                  <button
                    type="button"
                    class="font-medium text-sm text-gray-900 dark:text-gray-100 truncate text-left hover:text-primary-400 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 rounded"
                    title="Click to rename"
                    onclick={() => startEdit(voice)}
                  >{voice.name}</button>
                  <button
                    onclick={() => startEdit(voice)}
                    class="text-gray-500 hover:text-primary-400 text-xs transition-colors"
                    aria-label="Rename voice"
                    title="Rename"
                  >✏</button>
                {/if}
                <span class="badge-available">{voice.model_id}</span>
                <span
                  class="text-xs px-2 py-0.5 rounded-full font-medium {transcriptBadgeClass(voice.reference_text_status)}"
                  title="Transcript status"
                >
                  {transcriptBadgeLabel(voice.reference_text_status)}
                </span>
              </div>
              <p class="text-xs text-gray-400 mt-0.5">{formatDate(voice.created_at)}</p>

              <!-- Reference audio waveform preview -->
              <div class="mt-2">
                <WaveformPreview src={getVoiceAudioUrl(voice.id)} height={40} />
              </div>

              <!-- Preview player -->
              {#if voice.id === previewVoiceId && previewAudioUrl}
                <div class="mt-2">
                  <AudioPlayer src={previewAudioUrl} />
                </div>
              {/if}

              <!-- Generating indicator -->
              {#if generatingPreview && previewVoiceId === voice.id}
                <div class="flex items-center gap-2 mt-2">
                  <div class="spinner-sm"></div>
                  <span class="text-xs text-gray-400">Generating preview...</span>
                </div>
              {/if}
            </div>

            <div class="flex gap-2 flex-shrink-0">
              <button
                onclick={() => handlePreview(voice)}
                disabled={generatingPreview}
                class="btn-secondary text-xs px-3 py-1.5"
              >
                {#if generatingPreview && previewVoiceId === voice.id}
                  Generating...
                {:else}
                  Preview
                {/if}
              </button>
              <button
                onclick={() => handleDelete(voice.id)}
                disabled={uploading}
                class="btn-danger text-xs px-3 py-1.5"
              >
                Delete
              </button>
            </div>
          </li>
        {/each}
      </ul>
    {/if}
  </div>
</div>
