<!--
  ReferenceAudioRef.svelte — small inline reference-audio thumbnail.

  Given a voice profile UUID, fetches the profile metadata, shows
  "Cloned from {profile.name} ({duration}s reference)" with a play button
  that streams `/api/voices/{id}/audio`.

  The audio URL is reused on subsequent plays (no re-fetch).
  Duration is preferred from the backend's `reference_duration_seconds`
  field (when present) and falls back to the `<audio>` element's
  `loadedmetadata` event on the client.
-->
<script lang="ts">
  import { onMount } from 'svelte';
  import { getVoice, getVoiceAudioUrl, type VoiceProfile } from '$api/voices';

  interface Props {
    voiceId: string;
    referenceText?: string | null;
  }

  let { voiceId, referenceText = null }: Props = $props();

  let profile = $state<VoiceProfile | null>(null);
  let loadError = $state('');
  let audioEl = $state<HTMLAudioElement | undefined>(undefined);
  let audioSrc = $state('');
  let playing = $state(false);
  let clientDuration = $state<number | null>(null);

  // Combined duration: backend value (if available) wins over client-detected.
  // The backend field is optional — present only after an opt-in extension to
  // VoiceProfileResponse — so we tolerate it being undefined.
  const duration = $derived<number | null>(
    (profile as unknown as { reference_duration_seconds?: number | null } | null)
      ?.reference_duration_seconds ?? clientDuration ?? null
  );

  // Keep a destroyed flag to avoid mutating state after unmount.
  let destroyed = false;
  $effect(() => () => { destroyed = true; });

  onMount(() => {
    (async () => {
      try {
        const p = await getVoice(voiceId);
        if (destroyed) return;
        profile = p;
      } catch (err) {
        if (destroyed) return;
        loadError = err instanceof Error ? err.message : 'Failed to load voice profile';
      }
    })();
  });

  function togglePlay(): void {
    if (!audioEl) return;
    // Lazy-load the URL on first play so we don't spawn a connection for
    // users who never click the button.
    if (!audioSrc) {
      audioSrc = getVoiceAudioUrl(voiceId);
    }
    if (audioEl.paused) {
      audioEl.play().catch(() => {
        // Ignore play() rejections (browser autoplay policies, etc.).
      });
    } else {
      audioEl.pause();
    }
  }

  function onLoadedMeta(): void {
    if (!audioEl) return;
    if (Number.isFinite(audioEl.duration)) {
      clientDuration = audioEl.duration;
    }
  }
</script>

<div class="flex items-start gap-2 text-sm">
  <button
    type="button"
    onclick={togglePlay}
    disabled={!profile}
    class="flex-shrink-0 w-8 h-8 flex items-center justify-center rounded-full
           bg-primary-600 hover:bg-primary-700 disabled:opacity-40 disabled:cursor-not-allowed
           text-white transition-colors"
    aria-label={playing ? 'Pause reference audio' : 'Play reference audio'}
  >
    {#if playing}
      <svg class="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 20 20" aria-hidden="true">
        <path d="M5 4h3v12H5zM12 4h3v12h-3z" />
      </svg>
    {:else}
      <svg class="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 20 20" aria-hidden="true">
        <path d="M6 4l10 6-10 6V4z" />
      </svg>
    {/if}
  </button>

  <div class="flex-1 min-w-0">
    {#if loadError}
      <p class="text-xs text-red-600 dark:text-red-400 break-words">{loadError}</p>
    {:else if !profile}
      <p class="text-xs text-gray-400 dark:text-gray-600">Loading reference…</p>
    {:else}
      <p class="text-gray-700 dark:text-gray-300 truncate" title={profile.name}>
        Cloned from <span class="font-medium">{profile.name}</span>
        {#if duration != null}
          <span class="text-xs text-gray-500 dark:text-gray-400">({duration.toFixed(1)}s reference)</span>
        {/if}
      </p>
      {#if referenceText}
        <p
          class="text-xs text-gray-500 dark:text-gray-400 mt-0.5 italic line-clamp-2 break-words"
          title={referenceText}
        >
          “{referenceText}”
        </p>
      {/if}
    {/if}
  </div>

  <!-- Hidden HTMLAudioElement; the play button drives it. preload=metadata
       gives us duration without forcing a full byte download. -->
  <audio
    bind:this={audioEl}
    src={audioSrc}
    preload="metadata"
    onloadedmetadata={onLoadedMeta}
    onplay={() => (playing = true)}
    onpause={() => (playing = false)}
    onended={() => (playing = false)}
    aria-label="Reference audio for cloned voice"
  ></audio>
</div>
