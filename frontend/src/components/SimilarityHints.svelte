<!--
  SimilarityHints.svelte — actionable advice when speaker-similarity is
  low. Renders a small amber info banner (informational, not alarming).
  Hidden entirely when score >= 0.5.
-->
<script lang="ts">
  interface Props {
    score: number;
    modelId: string;
  }

  let { score, modelId }: Props = $props();

  // Models that share the generic "noisy reference / studio recording" hint.
  const STUDIO_HINT_MODELS = new Set([
    'f5-tts',
    'chatterbox',
    'cosyvoice-2',
    'vibevoice-1.5b',
    'qwen3-tts',
    'fish-speech-s2',
  ]);

  function perModelVariant(id: string): string | null {
    if (id === 'dia-1b') {
      return (
        'Dia 1.6B is dialogue-focused and has a known cloning ceiling of around 0.35. ' +
        'Try F5-TTS or Chatterbox for tighter voice matches.'
      );
    }
    if (STUDIO_HINT_MODELS.has(id)) {
      return (
        'If the score stays low, your reference might have background noise, music, or ' +
        'multiple speakers. A 15-30 second mono studio recording typically scores 0.6-0.8.'
      );
    }
    return null;
  }

  const hints = $derived.by<string[]>(() => {
    if (score >= 0.5) return [];
    const out: string[] = [];
    if (score < 0.3) {
      out.push('Try uploading a longer reference clip (15-30 s of clean speech).');
      out.push('Check the auto-detected transcript on the voice profile for typos.');
    }
    const variant = perModelVariant(modelId);
    if (variant) out.push(variant);
    return out;
  });

  const visible = $derived(hints.length > 0);
</script>

{#if visible}
  <div
    role="status"
    class="flex items-start gap-3 p-3 rounded-lg
           bg-amber-50 dark:bg-amber-500/10
           border border-amber-200 dark:border-amber-500/30
           text-amber-800 dark:text-amber-200 text-sm"
  >
    <svg
      class="w-5 h-5 flex-shrink-0 text-amber-600 dark:text-amber-400 mt-0.5"
      fill="none"
      stroke="currentColor"
      viewBox="0 0 24 24"
      aria-hidden="true"
    >
      <path
        stroke-linecap="round"
        stroke-linejoin="round"
        stroke-width="2"
        d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
      />
    </svg>
    <div class="flex-1 min-w-0">
      <p class="font-medium mb-1">Tips to improve voice match</p>
      <ul class="list-disc pl-4 space-y-0.5 text-xs">
        {#each hints as hint}
          <li class="break-words">{hint}</li>
        {/each}
      </ul>
    </div>
  </div>
{/if}
