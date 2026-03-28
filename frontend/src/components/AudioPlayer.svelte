<script lang="ts">
  import type WaveSurferType from 'wavesurfer.js';
  import { onMount } from 'svelte';
  import { theme } from '$stores/theme';

  let {
    src = '',
    duration = null,
    disabled = false,
    autoplay = false,
  }: {
    src?: string;
    duration?: number | null;
    disabled?: boolean;
    autoplay?: boolean;
  } = $props();

  let container = $state<HTMLElement | undefined>(undefined);
  let ws: WaveSurferType | null = null;
  let WaveSurfer: typeof import('wavesurfer.js').default | null = null;
  let playing = $state(false);
  let currentTime = $state(0);
  let wsDuration = $state(0);
  let ready = $state(false);
  let loadError = $state(false);

  const waveColors = {
    dark: { wave: '#6366f1', progress: '#a5b4fc', cursor: '#e0e7ff' },
    light: { wave: '#4f46e5', progress: '#818cf8', cursor: '#3730a3' },
  };

  onMount(async () => {
    const module = await import('wavesurfer.js');
    WaveSurfer = module.default;
    if (src) initWaveSurfer();
  });

  // Cleanup wavesurfer on component teardown (Svelte 5 $effect cleanup pattern)
  $effect(() => {
    return () => {
      ws?.destroy();
      ws = null;
    };
  });

  function initWaveSurfer(): void {
    if (!container || !src || !WaveSurfer) return;
    ws?.destroy();
    ready = false;
    loadError = false;
    playing = false;
    currentTime = 0;
    wsDuration = 0;

    const colors = waveColors[theme()] ?? waveColors.dark;
    ws = WaveSurfer.create({
      container,
      waveColor: colors.wave,
      progressColor: colors.progress,
      cursorColor: colors.cursor,
      height: 64,
      normalize: true,
      backend: 'MediaElement',  // uses <audio> internally — more compatible than WebAudio
      url: src,
    });

    ws.on('ready', (d: number) => {
      wsDuration = d;
      ready = true;
      if (autoplay) ws?.play();
    });
    ws.on('timeupdate', (t: number) => { currentTime = t; });
    ws.on('play', () => { playing = true; });
    ws.on('pause', () => { playing = false; });
    ws.on('finish', () => { playing = false; currentTime = 0; });
    ws.on('error', (err: Error) => {
      console.error('WaveSurfer error:', err);
      loadError = true;
    });
  }

  // Re-init when src changes
  $effect(() => {
    const currentSrc = src;
    if (currentSrc && container) {
      initWaveSurfer();
    }
  });

  // Update waveform colors when theme changes
  $effect(() => {
    const colors = waveColors[theme()] ?? waveColors.dark;
    ws?.setOptions({
      waveColor: colors.wave,
      progressColor: colors.progress,
      cursorColor: colors.cursor,
    });
  });

  function toggle(): void {
    if (!ws || !src || disabled) return;
    ws.playPause();
  }

  function seek(seconds: number): void {
    if (!ws || wsDuration === 0) return;
    const newTime = Math.max(0, Math.min(wsDuration, currentTime + seconds));
    ws.seekTo(newTime / wsDuration);
  }

  function seekToStart(): void { ws?.seekTo(0); }
  function seekToEnd(): void { ws?.seekTo(1); }

  function handleKeydown(e: KeyboardEvent): void {
    if (e.key === 'ArrowLeft') { e.preventDefault(); seek(-5); }
    else if (e.key === 'ArrowRight') { e.preventDefault(); seek(5); }
    else if (e.key === 'Home') { e.preventDefault(); seekToStart(); }
    else if (e.key === 'End') { e.preventDefault(); seekToEnd(); }
    else if (e.key === ' ' || e.key === 'Enter') { e.preventDefault(); toggle(); }
  }

  function formatTime(s: number): string {
    const m = Math.floor(s / 60);
    const sec = Math.floor(s % 60);
    return `${m}:${sec.toString().padStart(2, '0')}`;
  }

  let displayDuration = $derived(duration ?? wsDuration);
</script>

<div class="space-y-2">
  {#if src}
    <!-- WaveSurfer container — primary keyboard target -->
    {#if !loadError}
      <div
        bind:this={container}
        class="w-full rounded-lg overflow-hidden cursor-pointer
               {!ready ? 'opacity-50' : ''}"
        role="application"
        aria-label="Audio waveform. Space to play/pause, arrow keys to seek ±5s"
        onkeydown={handleKeydown}
        tabindex={0}
      ></div>
    {/if}

    <div class="flex items-center gap-3">
      <!-- Play/Pause button -->
      <button
        onclick={toggle}
        disabled={disabled || (!ready && !loadError)}
        class="flex-shrink-0 w-9 h-9 flex items-center justify-center rounded-full
               bg-primary-600 hover:bg-primary-700 disabled:opacity-50 disabled:cursor-not-allowed
               text-white transition-colors"
        aria-label={playing ? 'Pause' : 'Play'}
      >
        {#if playing}
          <!-- Pause icon -->
          <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
            <path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zM7 8a1 1 0 012 0v4a1 1 0 11-2 0V8zm5-1a1 1 0 00-1 1v4a1 1 0 102 0V8a1 1 0 00-1-1z" clip-rule="evenodd" />
          </svg>
        {:else}
          <!-- Play icon -->
          <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
            <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM9.555 7.168A1 1 0 008 8v4a1 1 0 001.555.832l3-2a1 1 0 000-1.664l-3-2z" clip-rule="evenodd" />
          </svg>
        {/if}
      </button>

      <!-- Keyboard seek hint / status -->
      <div class="flex-1 text-xs text-gray-500 dark:text-gray-500">
        {#if loadError}
          <audio controls src={src} class="h-8 w-full max-w-xs"></audio>
        {:else if !ready && src}
          <span class="text-xs text-gray-400 dark:text-gray-600">Loading waveform...</span>
        {:else}
          <span class="text-xs text-gray-500 dark:text-gray-600">Click waveform to seek · ←/→ ±5s · Space to play</span>
        {/if}
      </div>

      <!-- Time -->
      <span class="text-xs text-gray-500 dark:text-gray-400 tabular-nums flex-shrink-0 w-16 text-right">
        {formatTime(currentTime)} / {formatTime(displayDuration)}
      </span>

      <!-- Download -->
      <a
        href={src}
        download="tts_output"
        class="flex-shrink-0 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition-colors"
        aria-label="Download audio"
      >
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
            d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
        </svg>
      </a>
    </div>
  {:else}
    <!-- Placeholder state -->
    <div class="flex items-center gap-3 opacity-40">
      <div class="flex-shrink-0 w-9 h-9 rounded-full bg-gray-300 dark:bg-gray-600"></div>
      <div class="flex-1 h-16 bg-gray-200 dark:bg-gray-700 rounded-lg"></div>
      <span class="text-xs text-gray-400 w-16 text-right">0:00 / 0:00</span>
    </div>
  {/if}
</div>
