<!--
  SimilarityScale.svelte — labelled horizontal bar visualising the
  speechbrain ECAPA-TDNN cosine similarity between a reference voice
  and the generated audio.

  - 0.00–0.30  → "Different speaker" (red zone)
  - 0.30–0.50  → "Ambiguous"         (amber zone)
  - 0.50–1.00  → "Same speaker"      (green zone)
-->
<script lang="ts">
  interface Props {
    score: number;
    compact?: boolean;
  }

  let { score, compact = false }: Props = $props();

  // Clamp the marker into [0, 1] so a slightly-out-of-range value (negative
  // cosine, or numerical drift > 1) doesn't fly off the rail.
  const clampedScore = $derived(Math.max(0, Math.min(1, score)));
  const markerPct = $derived(clampedScore * 100);

  const tier = $derived(
    score >= 0.5 ? 'same' : score >= 0.3 ? 'ambiguous' : 'different'
  );
  const tierLabel = $derived(
    tier === 'same'
      ? 'same speaker range'
      : tier === 'ambiguous'
        ? 'ambiguous range'
        : 'different speaker range'
  );
  const numericTextClass = $derived(
    tier === 'same'
      ? 'text-green-700 dark:text-green-300'
      : tier === 'ambiguous'
        ? 'text-amber-700 dark:text-amber-300'
        : 'text-red-700 dark:text-red-300'
  );
</script>

<div
  class="flex items-center gap-3 {compact ? 'w-[120px]' : 'w-[280px]'}"
  role="meter"
  aria-valuemin={0}
  aria-valuemax={1}
  aria-valuenow={clampedScore}
  aria-label={`Voice match score: ${score.toFixed(2)}, ${tierLabel}`}
>
  <div class="flex-1">
    <!-- Bar -->
    <div class="relative h-2 rounded-full overflow-hidden ring-1 ring-gray-300 dark:ring-gray-700">
      <!-- Red zone 0–30% -->
      <div
        class="absolute inset-y-0 left-0 bg-red-300 dark:bg-red-500/40"
        style="width: 30%;"
      ></div>
      <!-- Amber zone 30–50% -->
      <div
        class="absolute inset-y-0 bg-amber-300 dark:bg-amber-500/40"
        style="left: 30%; width: 20%;"
      ></div>
      <!-- Green zone 50–100% -->
      <div
        class="absolute inset-y-0 bg-green-300 dark:bg-green-500/40"
        style="left: 50%; width: 50%;"
      ></div>
      <!-- Marker -->
      <div
        class="absolute top-[-2px] bottom-[-2px] w-[3px] rounded-sm bg-gray-900 dark:bg-white shadow"
        style={`left: calc(${markerPct}% - 1.5px);`}
        aria-hidden="true"
      ></div>
    </div>

    <!-- Region labels (hidden in compact mode to save space) -->
    {#if !compact}
      <div class="flex justify-between text-[10px] mt-1 text-gray-500 dark:text-gray-400 select-none">
        <span class="text-red-600 dark:text-red-400">Different</span>
        <span class="text-amber-600 dark:text-amber-400">Ambiguous</span>
        <span class="text-green-600 dark:text-green-400">Same</span>
      </div>
    {/if}
  </div>

  <!-- Numeric score -->
  <span
    class="text-sm font-semibold tabular-nums {numericTextClass}"
    title={`Cosine similarity (range -1 to 1; ≥0.5 typically same speaker). Tier: ${tierLabel}.`}
  >
    {score.toFixed(2)}
  </span>
</div>
