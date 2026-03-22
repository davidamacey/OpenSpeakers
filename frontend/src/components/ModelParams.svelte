<!-- Per-model parameter controls -->
<script lang="ts">
  let {
    modelId = '',
    disabled = false,
    extras = $bindable({}),
  }: {
    modelId?: string;
    disabled?: boolean;
    extras?: Record<string, unknown>;
  } = $props();

  // VibeVoice 0.5B defaults
  let cfgScale = $state(1.5);
  let ddpmSteps = $state(5);
  // VibeVoice 1.5B defaults
  let cfgScale1p5b = $state(3.0);
  // Fish Speech defaults
  let temperature = $state(0.7);
  let topP = $state(0.8);
  let repPenalty = $state(1.1);
  // Qwen3 TTS
  let instruct = $state('');

  // Reset all params to defaults when model changes
  $effect(() => {
    const _m = modelId;
    cfgScale = 1.5;
    ddpmSteps = 5;
    cfgScale1p5b = 3.0;
    temperature = 0.7;
    topP = 0.8;
    repPenalty = 1.1;
    instruct = '';
  });

  // Sync extras from internal state
  $effect(() => {
    switch (modelId) {
      case 'vibevoice':
        extras = { cfg_scale: cfgScale, ddpm_steps: ddpmSteps };
        break;
      case 'vibevoice-1.5b':
        extras = { cfg_scale: cfgScale1p5b };
        break;
      case 'fish-speech-s2':
        extras = { temperature, top_p: topP, repetition_penalty: repPenalty };
        break;
      case 'qwen3-tts':
        extras = instruct ? { instruct } : {};
        break;
      default:
        extras = {};
    }
  });
</script>

{#if !modelId}
  <p class="text-xs text-gray-400 dark:text-gray-500 text-center py-2">
    Select a model above to see its settings.
  </p>
{/if}

<!-- Kokoro: no extra params (speed + language handled by parent) -->

<!-- VibeVoice 0.5B -->
{#if modelId === 'vibevoice'}
  <div class="grid grid-cols-2 gap-4">
    <!-- Voice Clarity -->
    <div>
      <label class="label" for="cfg-scale">
        Voice Clarity: {cfgScale.toFixed(1)}
        {#if cfgScale === 1.5}<span class="label-hint">(default)</span>{/if}
        <span
          class="label-hint cursor-help"
          title="Lower values sound more natural with slight variation. Higher values are more precise but can sound mechanical."
        >&#9432;</span>
      </label>
      <input
        id="cfg-scale"
        type="range"
        min="1.0"
        max="3.0"
        step="0.1"
        bind:value={cfgScale}
        {disabled}
        class="w-full"
      />
      <p class="text-xs text-gray-400 dark:text-gray-500 mt-1">
        How closely the voice follows the style preset
      </p>
    </div>

    <!-- Quality Steps -->
    <div>
      <label class="label" for="ddpm-steps">
        Quality Steps: {ddpmSteps}
        {#if ddpmSteps === 5}<span class="label-hint">(default)</span>{/if}
        <span
          class="label-hint cursor-help"
          title="Each step refines the audio. 3-4 for fast previews, 5 for balanced, 8-10 for final output."
        >&#9432;</span>
      </label>
      <input
        id="ddpm-steps"
        type="range"
        min="3"
        max="10"
        step="1"
        bind:value={ddpmSteps}
        {disabled}
        class="w-full"
      />
      <p class="text-xs text-gray-400 dark:text-gray-500 mt-1">
        More steps = better quality, slower generation
      </p>
    </div>
  </div>
{/if}

<!-- VibeVoice 1.5B -->
{#if modelId === 'vibevoice-1.5b'}
  <div>
    <label class="label" for="cfg-scale-1p5b">
      Voice Clarity: {cfgScale1p5b.toFixed(1)}
      {#if cfgScale1p5b === 3.0}<span class="label-hint">(default)</span>{/if}
      <span
        class="label-hint cursor-help"
        title="Lower = more creative variation. Higher = closer match to reference voice."
      >&#9432;</span>
    </label>
    <input
      id="cfg-scale-1p5b"
      type="range"
      min="1.0"
      max="5.0"
      step="0.1"
      bind:value={cfgScale1p5b}
      {disabled}
      class="w-full"
    />
    <p class="text-xs text-gray-400 dark:text-gray-500 mt-1">
      How closely the output follows the voice reference
    </p>
  </div>

  <div class="flex items-start gap-2 p-2.5 rounded-lg bg-blue-50 dark:bg-blue-500/10 border border-blue-200 dark:border-blue-500/20 text-xs text-blue-700 dark:text-blue-300 mt-2">
    <svg class="w-3.5 h-3.5 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
    </svg>
    <p>
      Tip: For multiple speakers, start each line with "Speaker 0:" or "Speaker 1:".
      Add [pause_0.5s] for pauses.
    </p>
  </div>
{/if}

<!-- Fish Speech S2-Pro -->
{#if modelId === 'fish-speech-s2'}
  <div class="grid grid-cols-3 gap-4">
    <!-- Expressiveness -->
    <div>
      <label class="label" for="fish-temperature">
        Expressiveness: {temperature.toFixed(2)}
        {#if temperature === 0.7}<span class="label-hint">(default)</span>{/if}
        <span
          class="label-hint cursor-help"
          title="Low (0.1-0.3): steady, consistent. Medium (0.5-0.7): natural. High (0.8-1.0): dramatic."
        >&#9432;</span>
      </label>
      <input
        id="fish-temperature"
        type="range"
        min="0.1"
        max="1.0"
        step="0.05"
        bind:value={temperature}
        {disabled}
        class="w-full"
      />
      <p class="text-xs text-gray-400 dark:text-gray-500 mt-1">
        How dynamic and varied the speech sounds
      </p>
    </div>

    <!-- Variation -->
    <div>
      <label class="label" for="fish-top-p">
        Variation: {topP.toFixed(2)}
        {#if topP === 0.8}<span class="label-hint">(default)</span>{/if}
        <span
          class="label-hint cursor-help"
          title="Lower = more predictable and consistent. Higher = more varied and natural-sounding."
        >&#9432;</span>
      </label>
      <input
        id="fish-top-p"
        type="range"
        min="0.5"
        max="1.0"
        step="0.05"
        bind:value={topP}
        {disabled}
        class="w-full"
      />
      <p class="text-xs text-gray-400 dark:text-gray-500 mt-1">
        Range of vocal patterns to use
      </p>
    </div>

    <!-- Anti-Repetition -->
    <div>
      <label class="label" for="fish-rep-penalty">
        Anti-Repetition: {repPenalty.toFixed(1)}
        {#if repPenalty === 1.1}<span class="label-hint">(default)</span>{/if}
        <span
          class="label-hint cursor-help"
          title="Increase to 1.3-1.5 if output sounds repetitive. Don't go above 1.8."
        >&#9432;</span>
      </label>
      <input
        id="fish-rep-penalty"
        type="range"
        min="0.9"
        max="2.0"
        step="0.1"
        bind:value={repPenalty}
        {disabled}
        class="w-full"
      />
      <p class="text-xs text-gray-400 dark:text-gray-500 mt-1">
        Prevents the voice from getting stuck in loops
      </p>
    </div>
  </div>

  <div class="flex items-start gap-2 p-2.5 rounded-lg bg-blue-50 dark:bg-blue-500/10 border border-blue-200 dark:border-blue-500/20 text-xs text-blue-700 dark:text-blue-300 mt-2">
    <svg class="w-3.5 h-3.5 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
    </svg>
    <p>
      Tip: Add emotion tags in your text: [happy], [sad], [angry], [whisper], [excited]
    </p>
  </div>
{/if}

<!-- Qwen3 TTS -->
{#if modelId === 'qwen3-tts'}
  <div>
    <label class="label" for="qwen3-instruct">
      Speaking Style
      <span
        class="label-hint cursor-help"
        title="You can describe any speaking style: speed, emotion, accent, formality. The model interprets natural language instructions."
      >&#9432;</span>
    </label>
    <input
      id="qwen3-instruct"
      type="text"
      bind:value={instruct}
      {disabled}
      maxlength={200}
      placeholder={'e.g. "speak cheerfully and with enthusiasm" or "read slowly as a bedtime story"'}
      class="input"
    />
    <p class="text-xs text-gray-400 dark:text-gray-500 mt-1">
      Describe how the voice should sound &mdash; leave empty for a natural tone
    </p>
  </div>
{/if}
