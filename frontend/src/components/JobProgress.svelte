<!-- Real-time job progress using WebSocket.
     Shows spinner -> model loading bar -> generation bar -> complete.
     Never shows a blank "waiting" state to the user. -->
<script lang="ts">
  import { JobProgressSocket, type ProgressEvent, type ProgressStep } from '$lib/api/ws';
  import type { TTSJob } from '$api/tts';

  let {
    job = null,
    onComplete = (_audioUrl: string, _duration: number) => {},
    onError = (_message: string) => {}
  }: {
    job?: TTSJob | null;
    onComplete?: (audioUrl: string, duration: number) => void;
    onError?: (message: string) => void;
  } = $props();

  let step: ProgressStep = $state('queued');
  let percent = $state(0);
  let etaSeconds: number | null = $state(null);
  let detail = $state('Job queued, waiting for worker...');
  let socket: JobProgressSocket | null = $state(null);

  $effect(() => {
    if (job && job.status !== 'complete' && job.status !== 'failed') {
      startSocket(job.id);
    }

    return () => {
      socket?.disconnect();
    };
  });

  function startSocket(jobId: string): void {
    socket?.disconnect();
    step = 'queued';
    percent = 0;
    detail = 'Job queued, waiting for worker...';

    socket = new JobProgressSocket(jobId, handleProgress);
    socket.connect();
  }

  function handleProgress(event: ProgressEvent): void {
    if (event.type === 'progress') {
      step = event.step ?? 'generating';
      percent = event.percent ?? percent;
      etaSeconds = event.eta_seconds ?? null;
      detail = stepLabel(step, percent);
    } else if (event.type === 'status') {
      detail = event.detail ?? stepLabel(step, percent);
    } else if (event.type === 'complete') {
      step = 'complete';
      percent = 100;
      detail = 'Generation complete!';
      const audioUrl = event.audio_url ?? `/api/tts/jobs/${job?.id}/audio`;
      onComplete(audioUrl, event.duration ?? 0);
    } else if (event.type === 'error') {
      step = 'error';
      detail = event.message ?? 'Generation failed';
      onError(detail);
    }
  }

  function stepLabel(s: ProgressStep, pct: number): string {
    if (s === 'queued') return 'Job queued, waiting for worker...';
    if (s === 'model_loading') return `Loading model... ${pct}%`;
    if (s === 'generating') return `Generating audio... ${pct}%`;
    if (s === 'complete') return 'Generation complete!';
    if (s === 'error') return 'Generation failed';
    return 'Processing...';
  }

  function barColor(s: ProgressStep): string {
    if (s === 'error') return 'bg-red-500';
    if (s === 'complete') return 'bg-green-500';
    return 'bg-primary-500';
  }
</script>

{#if job && job.status !== 'complete' && job.status !== 'failed'}
  <div class="space-y-2">
    <!-- Status line -->
    <div class="flex items-center gap-2 text-sm">
      {#if step !== 'complete' && step !== 'error'}
        <svg class="w-4 h-4 animate-spin text-primary-500 flex-shrink-0" fill="none" viewBox="0 0 24 24">
          <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/>
          <path class="opacity-75" fill="currentColor"
            d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>
        </svg>
      {/if}
      <span class="text-gray-600 dark:text-gray-300">{detail}</span>
      {#if etaSeconds !== null && etaSeconds > 0}
        <span class="text-gray-400 text-xs">~{etaSeconds}s</span>
      {/if}
    </div>

    <!-- Progress bar -->
    <div class="h-1.5 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
      <div
        class="h-full rounded-full transition-all duration-300 {barColor(step)}"
        style="width: {step === 'queued' ? 3 : percent}%"
      ></div>
    </div>

    <!-- Step indicators -->
    <div class="flex gap-4 text-xs text-gray-400">
      <span class:text-primary-500={step === 'queued'}>Queued</span>
      <span>-></span>
      <span class:text-primary-500={step === 'model_loading'}>Loading model</span>
      <span>-></span>
      <span class:text-primary-500={step === 'generating'}>Generating</span>
      <span>-></span>
      <span class:text-green-500={step === 'complete'}>Done</span>
    </div>
  </div>
{/if}
