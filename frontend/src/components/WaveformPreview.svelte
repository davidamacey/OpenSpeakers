<script lang="ts">
  import type WaveSurferType from 'wavesurfer.js';
  import { onMount } from 'svelte';
  import { theme } from '$stores/theme';

  let { src, height = 48 }: { src: string; height?: number } = $props();

  let container = $state<HTMLElement | undefined>(undefined);
  let ws: WaveSurferType | null = null;

  onMount(async () => {
    const { default: WaveSurfer } = await import('wavesurfer.js');
    ws = WaveSurfer.create({
      container,
      waveColor: theme() === 'dark' ? '#4b5563' : '#9ca3af',
      progressColor: theme() === 'dark' ? '#6366f1' : '#4f46e5',
      height,
      normalize: true,
      interact: false,
      backend: 'MediaElement',  // more compatible than WebAudio; no full decode required
      url: src,
    });
  });

  // Cleanup wavesurfer on component teardown (Svelte 5 $effect cleanup pattern)
  $effect(() => {
    return () => {
      ws?.destroy();
      ws = null;
    };
  });

  $effect(() => {
    ws?.setOptions({
      waveColor: theme() === 'dark' ? '#4b5563' : '#9ca3af',
      progressColor: theme() === 'dark' ? '#6366f1' : '#4f46e5',
    });
  });
</script>

<div bind:this={container} class="w-full rounded overflow-hidden"></div>
