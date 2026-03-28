<script lang="ts">
  import { onMount, tick } from 'svelte';
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

  // Native <audio> element — always works, drives all playback state
  let audioEl = $state<HTMLAudioElement | undefined>(undefined);
  // WaveSurfer container div
  let waveContainer = $state<HTMLElement | undefined>(undefined);

  let playing = $state(false);
  let currentTime = $state(0);
  let audioDuration = $state(0);

  // WaveSurfer instance — visual waveform only; playhead synced manually via seekTo()
  let ws: import('wavesurfer.js').default | null = null;
  let wsReady = $state(false);

  // Sky-blue palette to match app primary color (not purple)
  const waveColors = {
    dark:  { wave: '#0369a1', progress: '#38bdf8', cursor: '#7dd3fc' },
    light: { wave: '#7dd3fc', progress: '#0284c7', cursor: '#0369a1' },
  };

  onMount(() => {
    // Use IIFE so the cleanup function is returned synchronously while init is async
    (async () => {
      await tick(); // ensure bind:this bindings are resolved before accessing audioEl
      if (autoplay && audioEl && src) audioEl.play().catch(() => {});
      await loadWaveSurfer();
    })();
    return () => { ws?.destroy(); ws = null; };
  });

  async function loadWaveSurfer(): Promise<void> {
    if (!src || !waveContainer) return;
    try {
      const { default: WaveSurfer } = await import('wavesurfer.js');
      if (!waveContainer) return; // unmounted during async
      ws?.destroy();
      wsReady = false;
      const colors = waveColors[theme()] ?? waveColors.dark;
      ws = WaveSurfer.create({
        container: waveContainer,
        waveColor: colors.wave,
        progressColor: colors.progress,
        cursorColor: colors.cursor,
        height: 64,
        normalize: true,
        interact: true,
        url: src,
        // Note: no `media` option — WaveSurfer manages its own audio for peak decoding.
        // Playhead is synced manually via seekTo() in ontimeupdate on the native <audio>.
      });
      ws.on('ready', () => { wsReady = true; });
      // User clicked waveform to seek — apply to native audio element
      ws.on('interaction', (newTime: number) => {
        if (audioEl) audioEl.currentTime = newTime;
      });
      ws.on('error', (err: Error) => { console.warn('WaveSurfer:', err.message); });
    } catch (err) {
      console.warn('WaveSurfer failed to load:', err);
    }
  }

  // Reinitialize WaveSurfer when src changes after initial mount
  let mounted = false;
  $effect(() => {
    const _ = src; // track src reactively
    if (!mounted) { mounted = true; return; } // skip first run — onMount handles it
    wsReady = false;
    ws?.destroy();
    ws = null;
    audioDuration = 0;
    currentTime = 0;
    playing = false;
    // Delay so audioEl.src updates first
    setTimeout(() => loadWaveSurfer(), 0);
  });

  // Update waveform colors when theme changes
  $effect(() => {
    const colors = waveColors[theme()] ?? waveColors.dark;
    ws?.setOptions({ waveColor: colors.wave, progressColor: colors.progress, cursorColor: colors.cursor });
  });

  function toggle(): void {
    if (!audioEl || !src || disabled) return;
    if (playing) audioEl.pause();
    else audioEl.play().catch(() => {});
  }

  function seek(seconds: number): void {
    if (!audioEl || audioDuration === 0) return;
    audioEl.currentTime = Math.max(0, Math.min(audioDuration, audioEl.currentTime + seconds));
  }

  function handleKeydown(e: KeyboardEvent): void {
    if (e.key === 'ArrowLeft') { e.preventDefault(); seek(-5); }
    else if (e.key === 'ArrowRight') { e.preventDefault(); seek(5); }
    else if (e.key === 'Home') { e.preventDefault(); if (audioEl) audioEl.currentTime = 0; }
    else if (e.key === 'End') { e.preventDefault(); if (audioEl) audioEl.currentTime = audioDuration; }
    else if (e.key === ' ' || e.key === 'Enter') { e.preventDefault(); toggle(); }
  }

  function formatTime(s: number): string {
    const m = Math.floor(s / 60);
    const sec = Math.floor(s % 60);
    return `${m}:${sec.toString().padStart(2, '0')}`;
  }

  let displayDuration = $derived(duration ?? audioDuration);
</script>

<div class="space-y-2">
  {#if src}
    <!-- Hidden native <audio> element — drives all playback state reliably -->
    <!-- svelte-ignore a11y_media_has_caption -->
    <audio
      bind:this={audioEl}
      {src}
      onloadedmetadata={() => { audioDuration = audioEl?.duration ?? 0; }}
      ontimeupdate={() => {
        currentTime = audioEl?.currentTime ?? 0;
        // Sync WaveSurfer playhead — seekTo(0–1 progress) updates the visual cursor
        if (ws && wsReady && audioDuration > 0) ws.seekTo(currentTime / audioDuration);
      }}
      onplay={() => { playing = true; }}
      onpause={() => { playing = false; }}
      onended={() => { playing = false; currentTime = 0; if (ws && wsReady) ws.seekTo(0); }}
      class="hidden"
    ></audio>

    <!-- Waveform area: overlay keeps loading state above WaveSurfer's canvas -->
    <div class="relative w-full">
      <!-- WaveSurfer renders into this div — always in DOM so it can measure width -->
      <!-- svelte-ignore a11y_no_noninteractive_element_interactions a11y_no_noninteractive_tabindex -->
      <div
        bind:this={waveContainer}
        class="w-full min-h-[64px] rounded-lg overflow-hidden cursor-pointer"
        role="application"
        tabindex={0}
        aria-label="Audio waveform — click to seek, ←/→ ±5s, Space to play/pause"
        onkeydown={handleKeydown}
      ></div>
      <!-- Loading overlay sits on top until WaveSurfer fires 'ready' -->
      {#if !wsReady}
        <div class="absolute inset-0 flex items-center px-4 rounded-lg bg-gray-800/40 pointer-events-none">
          <div class="w-full h-6 rounded bg-gray-700/50 animate-pulse"></div>
        </div>
      {/if}
    </div>

    <div class="flex items-center gap-3">
      <!-- Play/Pause -->
      <button
        onclick={toggle}
        {disabled}
        class="flex-shrink-0 w-9 h-9 flex items-center justify-center rounded-full
               bg-primary-600 hover:bg-primary-700 disabled:opacity-50 disabled:cursor-not-allowed
               text-white transition-colors"
        aria-label={playing ? 'Pause' : 'Play'}
      >
        {#if playing}
          <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
            <path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zM7 8a1 1 0 012 0v4a1 1 0 11-2 0V8zm5-1a1 1 0 00-1 1v4a1 1 0 102 0V8a1 1 0 00-1-1z" clip-rule="evenodd" />
          </svg>
        {:else}
          <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
            <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM9.555 7.168A1 1 0 008 8v4a1 1 0 001.555.832l3-2a1 1 0 000-1.664l-3-2z" clip-rule="evenodd" />
          </svg>
        {/if}
      </button>

      <!-- Hint -->
      <span class="flex-1 text-xs text-gray-500 dark:text-gray-400">
        {#if wsReady}Click waveform to seek · ←/→ ±5s{:else}Loading waveform…{/if}
      </span>

      <!-- Time -->
      <span class="text-xs text-gray-500 dark:text-gray-400 tabular-nums flex-shrink-0 w-16 text-right">
        {formatTime(currentTime)} / {formatTime(displayDuration)}
      </span>

      <!-- Download -->
      <a
        href={src}
        download="tts_output"
        class="flex-shrink-0 text-gray-400 hover:text-gray-300 transition-colors"
        aria-label="Download audio"
      >
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
            d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
        </svg>
      </a>
    </div>
  {:else}
    <!-- Placeholder -->
    <div class="flex items-center gap-3 opacity-40">
      <div class="flex-shrink-0 w-9 h-9 rounded-full bg-gray-300 dark:bg-gray-600"></div>
      <div class="flex-1 h-16 bg-gray-200 dark:bg-gray-700 rounded-lg"></div>
      <span class="text-xs text-gray-400 w-16 text-right">0:00 / 0:00</span>
    </div>
  {/if}
</div>
