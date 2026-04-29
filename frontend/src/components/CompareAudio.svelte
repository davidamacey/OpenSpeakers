<!--
  CompareAudio.svelte — two compact audio players side-by-side plus a
  "Play both" button that plays them sequentially with a 0.5 s pause.
  Each player retains its own play button so users can replay individually.
  Clicking "Play both" while a sequence is running stops it and restarts.
-->
<script lang="ts">
  interface Props {
    referenceUrl: string;
    generatedUrl: string;
    referenceLabel?: string;
    generatedLabel?: string;
  }

  let {
    referenceUrl,
    generatedUrl,
    referenceLabel = 'Reference',
    generatedLabel = 'Generated',
  }: Props = $props();

  let refAudio = $state<HTMLAudioElement | undefined>(undefined);
  let genAudio = $state<HTMLAudioElement | undefined>(undefined);
  let refPlaying = $state(false);
  let genPlaying = $state(false);
  let sequenceActive = $state(false);
  let pauseTimer: ReturnType<typeof setTimeout> | null = null;

  // The "current" sequence id lets queued callbacks abort cleanly when the
  // user kicks off a new sequence while the previous one is still running.
  let sequenceId = 0;

  function clearPauseTimer(): void {
    if (pauseTimer != null) {
      clearTimeout(pauseTimer);
      pauseTimer = null;
    }
  }

  function stopAll(): void {
    clearPauseTimer();
    sequenceActive = false;
    sequenceId += 1;
    if (refAudio) {
      refAudio.pause();
      try { refAudio.currentTime = 0; } catch { /* not seekable yet */ }
    }
    if (genAudio) {
      genAudio.pause();
      try { genAudio.currentTime = 0; } catch { /* not seekable yet */ }
    }
  }

  function playSingle(which: 'ref' | 'gen'): void {
    // If a sequence is active, cancel it first — single-button playback
    // takes priority and shouldn't clash with the queued chain.
    if (sequenceActive) {
      stopAll();
    }
    const target = which === 'ref' ? refAudio : genAudio;
    const other = which === 'ref' ? genAudio : refAudio;
    if (!target) return;
    if (other) {
      other.pause();
      try { other.currentTime = 0; } catch { /* ignore */ }
    }
    if (target.paused) {
      target.currentTime = 0;
      target.play().catch(() => { /* autoplay policy / decode error */ });
    } else {
      target.pause();
    }
  }

  async function playBoth(): Promise<void> {
    // Reset any in-flight playback first.
    stopAll();
    if (!refAudio || !genAudio) return;

    sequenceId += 1;
    const mySeq = sequenceId;
    sequenceActive = true;

    const playRef = (): Promise<void> =>
      new Promise<void>((resolve) => {
        if (!refAudio || mySeq !== sequenceId) {
          resolve();
          return;
        }
        const onEnd = () => {
          refAudio?.removeEventListener('ended', onEnd);
          resolve();
        };
        refAudio.addEventListener('ended', onEnd);
        refAudio.currentTime = 0;
        refAudio.play().catch(() => {
          refAudio?.removeEventListener('ended', onEnd);
          resolve();
        });
      });

    const wait = (ms: number): Promise<void> =>
      new Promise<void>((resolve) => {
        pauseTimer = setTimeout(() => {
          pauseTimer = null;
          resolve();
        }, ms);
      });

    const playGen = (): Promise<void> =>
      new Promise<void>((resolve) => {
        if (!genAudio || mySeq !== sequenceId) {
          resolve();
          return;
        }
        const onEnd = () => {
          genAudio?.removeEventListener('ended', onEnd);
          resolve();
        };
        genAudio.addEventListener('ended', onEnd);
        genAudio.currentTime = 0;
        genAudio.play().catch(() => {
          genAudio?.removeEventListener('ended', onEnd);
          resolve();
        });
      });

    await playRef();
    if (mySeq !== sequenceId) return;
    await wait(500);
    if (mySeq !== sequenceId) return;
    await playGen();
    if (mySeq !== sequenceId) return;
    sequenceActive = false;
  }

  // Cleanup on unmount.
  $effect(() => () => stopAll());
</script>

<div class="space-y-2">
  <div class="flex flex-wrap items-center gap-2">
    <button
      type="button"
      onclick={playBoth}
      class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium
             bg-primary-600 hover:bg-primary-700 text-white transition-colors"
      aria-label="Play reference then generated"
    >
      <svg class="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 20 20" aria-hidden="true">
        <path d="M6 4l10 6-10 6V4z" />
      </svg>
      {sequenceActive ? 'Stop' : 'Play both'}
    </button>

    <button
      type="button"
      onclick={() => playSingle('ref')}
      class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs
             bg-gray-200 dark:bg-gray-700 hover:bg-gray-300 dark:hover:bg-gray-600
             text-gray-800 dark:text-gray-200 transition-colors"
      aria-label={`Play ${referenceLabel}`}
      aria-pressed={refPlaying}
    >
      <svg class="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 20 20" aria-hidden="true">
        {#if refPlaying}
          <path d="M5 4h3v12H5zM12 4h3v12h-3z" />
        {:else}
          <path d="M6 4l10 6-10 6V4z" />
        {/if}
      </svg>
      {referenceLabel}
    </button>

    <button
      type="button"
      onclick={() => playSingle('gen')}
      class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs
             bg-gray-200 dark:bg-gray-700 hover:bg-gray-300 dark:hover:bg-gray-600
             text-gray-800 dark:text-gray-200 transition-colors"
      aria-label={`Play ${generatedLabel}`}
      aria-pressed={genPlaying}
    >
      <svg class="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 20 20" aria-hidden="true">
        {#if genPlaying}
          <path d="M5 4h3v12H5zM12 4h3v12h-3z" />
        {:else}
          <path d="M6 4l10 6-10 6V4z" />
        {/if}
      </svg>
      {generatedLabel}
    </button>
  </div>

  <!-- Hidden audio elements driving the buttons. -->
  <audio
    bind:this={refAudio}
    src={referenceUrl}
    preload="metadata"
    onplay={() => (refPlaying = true)}
    onpause={() => (refPlaying = false)}
    onended={() => (refPlaying = false)}
    aria-label={`${referenceLabel} audio`}
  ></audio>
  <audio
    bind:this={genAudio}
    src={generatedUrl}
    preload="metadata"
    onplay={() => (genPlaying = true)}
    onpause={() => (genPlaying = false)}
    onended={() => (genPlaying = false)}
    aria-label={`${generatedLabel} audio`}
  ></audio>
</div>
