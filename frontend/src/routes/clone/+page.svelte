<!-- Voice Cloning Page -->
<script lang="ts">
  import { onMount } from 'svelte';
  import ModelSelector from '$components/ModelSelector.svelte';
  import AudioPlayer from '$components/AudioPlayer.svelte';
  import ErrorBanner from '$components/ErrorBanner.svelte';
  import { voiceCloningModels, refreshModels } from '$stores/models';
  import {
    createVoiceProfile,
    listVoices,
    deleteVoiceProfile,
    type VoiceProfile,
  } from '$api/voices';
  import { generateTTS, getAudioUrl, pollJob } from '$api/tts';

  // Form state
  let selectedModel = $state('');
  let voiceName = $state('');
  let referenceFile: File | null = $state(null);
  let referenceAudioPreview = $state('');
  let uploading = $state(false);
  let uploadError = $state('');

  // Saved voices
  let clonedVoices: VoiceProfile[] = $state([]);
  let loadingVoices = $state(false);
  let loadVoicesError = $state('');

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

  onMount(async () => {
    await refreshModels();
    // Default to first cloning-capable model
    if ($voiceCloningModels.length > 0 && !selectedModel) {
      selectedModel = $voiceCloningModels[0].id;
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

  function handleFileChange(e: Event): void {
    const input = e.currentTarget as HTMLInputElement;
    const file = input.files?.[0] ?? null;
    referenceFile = file;
    uploadError = '';
    if (file) {
      // Validate file size (max 50 MB)
      if (file.size > 50 * 1024 * 1024) {
        uploadError = 'File too large. Maximum size is 50 MB.';
        referenceFile = null;
        referenceAudioPreview = '';
        return;
      }
      referenceAudioPreview = URL.createObjectURL(file);
    } else {
      referenceAudioPreview = '';
    }
  }

  async function handleCreate(): Promise<void> {
    if (!canCreate) return;
    uploading = true;
    uploadError = '';
    try {
      const profile = await createVoiceProfile(voiceName.trim(), selectedModel, referenceFile!);
      clonedVoices = [profile, ...clonedVoices];
      // Reset form
      voiceName = '';
      referenceFile = null;
      referenceAudioPreview = '';
    } catch (err) {
      uploadError = err instanceof Error ? err.message : 'Upload failed. Please try again.';
    } finally {
      uploading = false;
    }
  }

  async function handleDelete(voiceId: string): Promise<void> {
    if (!confirm('Delete this voice profile? This cannot be undone.')) return;
    try {
      await deleteVoiceProfile(voiceId);
      clonedVoices = clonedVoices.filter((v) => v.id !== voiceId);
      // Clear preview if the deleted voice was being previewed
      if (previewVoiceId === voiceId) {
        previewAudioUrl = '';
        previewVoiceId = null;
      }
    } catch (err) {
      uploadError = err instanceof Error ? err.message : 'Failed to delete voice profile';
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
</script>

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
        Currently supported: <strong>Fish Speech</strong>, <strong>VibeVoice 1.5B</strong>.
        Upload <strong>5-30 seconds</strong> of clean speech for best results. Avoid background
        noise or music.
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
        <label class="label">Model</label>
        <ModelSelector
          models={$voiceCloningModels}
          bind:value={selectedModel}
          disabled={uploading}
        />
      </div>
    </div>

    <!-- File upload -->
    <div>
      <label class="label" for="ref-audio">
        Reference audio
        <span class="label-hint">(WAV / MP3 / FLAC, 5-30 sec recommended)</span>
      </label>
      <input
        id="ref-audio"
        type="file"
        accept="audio/wav,audio/mpeg,audio/flac,audio/x-wav,audio/ogg"
        onchange={handleFileChange}
        disabled={uploading}
        class="block w-full text-sm text-gray-500 dark:text-gray-400
               file:mr-4 file:py-2 file:px-4
               file:rounded-lg file:border-0 file:font-medium
               file:bg-primary-50 file:text-primary-700
               dark:file:bg-primary-900/30 dark:file:text-primary-400
               hover:file:bg-primary-100 dark:hover:file:bg-primary-900/50
               file:cursor-pointer file:transition-colors"
      />
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
                     bg-purple-100 dark:bg-purple-500/15"
            >
              <svg
                class="w-4 h-4 text-purple-600 dark:text-purple-400"
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
                <p class="font-medium text-sm text-gray-900 dark:text-gray-100">{voice.name}</p>
                <span class="badge-available">{voice.model_id}</span>
              </div>
              <p class="text-xs text-gray-400 mt-0.5">{formatDate(voice.created_at)}</p>

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
