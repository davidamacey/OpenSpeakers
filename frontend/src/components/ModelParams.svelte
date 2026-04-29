<!-- Per-model parameter controls -->
<script lang="ts">
  import type { ModelInfo } from '$api/models';

  let {
    modelId = '',
    disabled = false,
    extras = $bindable({}),
    model = undefined,
    onInsertTag = undefined,
  }: {
    modelId?: string;
    disabled?: boolean;
    extras?: Record<string, unknown>;
    model?: ModelInfo;
    onInsertTag?: (tag: string) => void;
  } = $props();

  // VibeVoice 0.5B defaults
  let cfgScale = $state(1.5);
  let ddpmSteps = $state(5);
  // VibeVoice 1.5B defaults
  let cfgScale1p5b = $state(3.0);
  let ddpmSteps1p5b = $state(20);
  let speakerId = $state(0);
  // Fish Speech defaults
  let temperature = $state(0.7);
  let topP = $state(0.8);
  let repPenalty = $state(1.1);
  // Qwen3 TTS
  let instruct = $state('');
  // Chatterbox defaults
  let exaggeration = $state(0.5);
  let cfgWeight = $state(0.5);
  let chatterboxTemperature = $state(0.8);
  let chatterboxTopP = $state(1.0);
  let chatterboxMinP = $state(0.05);
  let chatterboxRepPenalty = $state(1.2);
  // Orpheus defaults
  let orpheusTemperature = $state(0.6);
  let orpheusTopP = $state(0.95);
  // F5-TTS defaults
  let f5RefText = $state('');
  let f5NfeStep = $state(32);
  let f5CfgStrength = $state(2.0);
  let f5SwaySamplingCoef = $state(-1.0);
  let f5TargetRms = $state(0.1);
  let f5RemoveSilence = $state(false);
  // Dia 1.6B defaults
  let diaCfgScale = $state(4.0);
  let diaTemperature = $state(1.8);
  let diaTopP = $state(0.9);
  let diaCfgFilterTopK = $state(50);
  // CosyVoice 2.0 defaults
  let cosyRefText = $state('');
  let cosyInstruct = $state('');
  // Optional per-job seed (string so empty == no seed). Persists across model
  // switches deliberately — users testing reproducibility usually want to
  // keep the same seed.
  let seed = $state('');

  // Reset all params to defaults when model changes. Seed is preserved.
  $effect(() => {
    const _m = modelId;
    cfgScale = 1.5;
    ddpmSteps = 5;
    cfgScale1p5b = 3.0;
    ddpmSteps1p5b = 20;
    speakerId = 0;
    temperature = 0.7;
    topP = 0.8;
    repPenalty = 1.1;
    instruct = '';
    exaggeration = 0.5;
    cfgWeight = 0.5;
    chatterboxTemperature = 0.8;
    chatterboxTopP = 1.0;
    chatterboxMinP = 0.05;
    chatterboxRepPenalty = 1.2;
    orpheusTemperature = 0.6;
    orpheusTopP = 0.95;
    f5RefText = '';
    f5NfeStep = 32;
    f5CfgStrength = 2.0;
    f5SwaySamplingCoef = -1.0;
    f5TargetRms = 0.1;
    f5RemoveSilence = false;
    diaCfgScale = 4.0;
    diaTemperature = 1.8;
    diaTopP = 0.9;
    diaCfgFilterTopK = 50;
    cosyRefText = '';
    cosyInstruct = '';
  });

  // Inject seed only when non-empty. Parsed lazily so an in-progress edit
  // ("12") doesn't pollute the request as NaN.
  function withSeed(base: Record<string, unknown>): Record<string, unknown> {
    const trimmed = seed.trim();
    if (!trimmed) return base;
    const parsed = Number(trimmed);
    if (!Number.isFinite(parsed)) return base;
    return { ...base, seed: Math.trunc(parsed) };
  }

  // Sync extras from internal state
  $effect(() => {
    switch (modelId) {
      case 'vibevoice':
        extras = withSeed({ cfg_scale: cfgScale, ddpm_steps: ddpmSteps });
        break;
      case 'vibevoice-1.5b':
        extras = withSeed({
          cfg_scale: cfgScale1p5b,
          ddpm_steps: ddpmSteps1p5b,
          speaker_id: speakerId,
        });
        break;
      case 'fish-speech-s2':
        extras = withSeed({
          temperature,
          top_p: topP,
          repetition_penalty: repPenalty,
        });
        break;
      case 'qwen3-tts':
        extras = withSeed(instruct ? { instruct } : {});
        break;
      case 'chatterbox':
        extras = withSeed({
          exaggeration,
          cfg_weight: cfgWeight,
          temperature: chatterboxTemperature,
          top_p: chatterboxTopP,
          min_p: chatterboxMinP,
          repetition_penalty: chatterboxRepPenalty,
        });
        break;
      case 'orpheus-3b':
        extras = withSeed({ temperature: orpheusTemperature, top_p: orpheusTopP });
        break;
      case 'f5-tts':
        extras = withSeed({
          ...(f5RefText ? { ref_text: f5RefText } : {}),
          nfe_step: f5NfeStep,
          cfg_strength: f5CfgStrength,
          sway_sampling_coef: f5SwaySamplingCoef,
          target_rms: f5TargetRms,
          remove_silence: f5RemoveSilence,
        });
        break;
      case 'dia-1b':
        extras = withSeed({
          cfg_scale: diaCfgScale,
          temperature: diaTemperature,
          top_p: diaTopP,
          cfg_filter_top_k: diaCfgFilterTopK,
        });
        break;
      case 'cosyvoice-2':
        extras = withSeed({
          ...(cosyRefText ? { ref_text: cosyRefText } : {}),
          ...(cosyInstruct ? { instruct: cosyInstruct } : {}),
        });
        break;
      default:
        extras = withSeed({});
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
  <div class="grid grid-cols-2 gap-4">
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
        min="0.1"
        max="10.0"
        step="0.1"
        bind:value={cfgScale1p5b}
        {disabled}
        class="w-full"
      />
      <p class="text-xs text-gray-400 dark:text-gray-500 mt-1">
        How closely the output follows the voice reference
      </p>
    </div>

    <div>
      <label class="label" for="ddpm-steps-1p5b">
        Quality Steps: {ddpmSteps1p5b}
        {#if ddpmSteps1p5b === 20}<span class="label-hint">(default)</span>{/if}
        <span
          class="label-hint cursor-help"
          title="More steps refine the audio further. 10-15 for previews, 20 default, 30-50 for final output."
        >&#9432;</span>
      </label>
      <input
        id="ddpm-steps-1p5b"
        type="range"
        min="1"
        max="50"
        step="1"
        bind:value={ddpmSteps1p5b}
        {disabled}
        class="w-full"
      />
      <p class="text-xs text-gray-400 dark:text-gray-500 mt-1">
        More steps = better quality, slower generation
      </p>
    </div>
  </div>

  <!-- Speaker ID selector -->
  <div class="mt-3">
    <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1" for="speaker-id">
      Speaker ID
      <span class="text-xs text-gray-500 ml-1">(multi-speaker)</span>
    </label>
    <select
      id="speaker-id"
      bind:value={speakerId}
      {disabled}
      class="input"
    >
      <option value={0}>Speaker 0 (default)</option>
      <option value={1}>Speaker 1</option>
    </select>
    <p class="text-xs text-gray-500 dark:text-gray-500 mt-1">
      Prefix text with "Speaker 0: " or "Speaker 1: " to assign dialogue to different speakers.
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
        max="1.5"
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
        step="0.01"
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
        Anti-Repetition: {repPenalty.toFixed(2)}
        {#if repPenalty === 1.1}<span class="label-hint">(default)</span>{/if}
        <span
          class="label-hint cursor-help"
          title="Increase to 1.2-1.5 if output sounds repetitive."
        >&#9432;</span>
      </label>
      <input
        id="fish-rep-penalty"
        type="range"
        min="1.0"
        max="1.5"
        step="0.01"
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

  <!-- Emotion tag quick-insert (Fish S2-Pro) -->
  <div class="mt-3">
    <p class="text-xs text-gray-400 dark:text-gray-400 mb-1">Emotion tags (click to insert into text):</p>
    <div class="flex flex-wrap gap-1">
      {#each ['[whisper]', '[excited]', '[angry]', '[sad]', '[laughs]', '[sighs]', '[breathes heavily]'] as tag}
        <button
          type="button"
          class="text-xs px-2 py-0.5 rounded bg-gray-700 hover:bg-primary-600 transition-colors font-mono cursor-pointer"
          onclick={() => onInsertTag?.(tag)}
        >{tag}</button>
      {/each}
    </div>
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

    <!-- Example prompts quick-fill -->
    <select
      class="input mt-2 text-sm"
      onchange={(e) => {
        if (e.currentTarget.value) {
          instruct = e.currentTarget.value;
          e.currentTarget.value = '';
        }
      }}
    >
      <option value="">— Insert example style —</option>
      <option value="Speak in a warm, friendly tone">Warm and friendly</option>
      <option value="Speak excitedly with high energy">Excited</option>
      <option value="Speak slowly and clearly, with careful enunciation">Slow and clear</option>
      <option value="Speak softly and gently, almost whispering">Gentle whisper</option>
      <option value="Speak with a serious, authoritative tone">Authoritative</option>
    </select>
  </div>
{/if}

<!-- Chatterbox -->
{#if modelId === 'chatterbox'}
  <div class="grid grid-cols-2 gap-4">
    <!-- Exaggeration -->
    <div>
      <label class="label" for="chatterbox-exaggeration">
        Exaggeration: {exaggeration.toFixed(2)}
        {#if exaggeration === 0.5}<span class="label-hint">(default)</span>{/if}
        <span
          class="label-hint cursor-help"
          title="Controls emotion exaggeration. Lower = neutral, Higher = more expressive."
        >&#9432;</span>
      </label>
      <input
        id="chatterbox-exaggeration"
        type="range"
        min="0.0"
        max="1.0"
        step="0.05"
        bind:value={exaggeration}
        {disabled}
        class="w-full"
      />
      <p class="text-xs text-gray-400 dark:text-gray-500 mt-1">
        Emotion exaggeration level
      </p>
    </div>

    <!-- CFG Weight -->
    <div>
      <label class="label" for="chatterbox-cfg">
        CFG Weight: {cfgWeight.toFixed(2)}
        {#if cfgWeight === 0.5}<span class="label-hint">(default)</span>{/if}
        <span
          class="label-hint cursor-help"
          title="Controls pacing and adherence. Lower = more natural pacing, Higher = more controlled."
        >&#9432;</span>
      </label>
      <input
        id="chatterbox-cfg"
        type="range"
        min="0.0"
        max="1.0"
        step="0.05"
        bind:value={cfgWeight}
        {disabled}
        class="w-full"
      />
      <p class="text-xs text-gray-400 dark:text-gray-500 mt-1">
        Pacing / style control
      </p>
    </div>

    <!-- Temperature -->
    <div>
      <label class="label" for="chatterbox-temperature">
        Temperature: {chatterboxTemperature.toFixed(2)}
        {#if chatterboxTemperature === 0.8}<span class="label-hint">(default)</span>{/if}
        <span
          class="label-hint cursor-help"
          title="Sampling temperature. Lower = more deterministic, higher = more varied."
        >&#9432;</span>
      </label>
      <input
        id="chatterbox-temperature"
        type="range"
        min="0.1"
        max="1.5"
        step="0.05"
        bind:value={chatterboxTemperature}
        {disabled}
        class="w-full"
      />
      <p class="text-xs text-gray-400 dark:text-gray-500 mt-1">Speech variation</p>
    </div>

    <!-- Top-p -->
    <div>
      <label class="label" for="chatterbox-top-p">
        Top-p: {chatterboxTopP.toFixed(2)}
        {#if chatterboxTopP === 1.0}<span class="label-hint">(default)</span>{/if}
        <span
          class="label-hint cursor-help"
          title="Nucleus sampling. Higher = wider token pool."
        >&#9432;</span>
      </label>
      <input
        id="chatterbox-top-p"
        type="range"
        min="0.1"
        max="1.0"
        step="0.05"
        bind:value={chatterboxTopP}
        {disabled}
        class="w-full"
      />
      <p class="text-xs text-gray-400 dark:text-gray-500 mt-1">Token diversity</p>
    </div>

    <!-- Min-p -->
    <div>
      <label class="label" for="chatterbox-min-p">
        Min-p: {chatterboxMinP.toFixed(2)}
        {#if chatterboxMinP === 0.05}<span class="label-hint">(default)</span>{/if}
        <span
          class="label-hint cursor-help"
          title="Filters out low-probability tokens below this threshold."
        >&#9432;</span>
      </label>
      <input
        id="chatterbox-min-p"
        type="range"
        min="0.0"
        max="0.5"
        step="0.01"
        bind:value={chatterboxMinP}
        {disabled}
        class="w-full"
      />
      <p class="text-xs text-gray-400 dark:text-gray-500 mt-1">Minimum-probability cutoff</p>
    </div>

    <!-- Repetition penalty -->
    <div>
      <label class="label" for="chatterbox-rep-penalty">
        Anti-Repetition: {chatterboxRepPenalty.toFixed(2)}
        {#if chatterboxRepPenalty === 1.2}<span class="label-hint">(default)</span>{/if}
        <span
          class="label-hint cursor-help"
          title="Increase if the voice loops or stutters."
        >&#9432;</span>
      </label>
      <input
        id="chatterbox-rep-penalty"
        type="range"
        min="1.0"
        max="2.0"
        step="0.05"
        bind:value={chatterboxRepPenalty}
        {disabled}
        class="w-full"
      />
      <p class="text-xs text-gray-400 dark:text-gray-500 mt-1">Discourage repeated tokens</p>
    </div>
  </div>

  <!-- Emotion tag helpers for Chatterbox -->
  <div class="mt-3">
    <p class="text-xs text-gray-400 dark:text-gray-400 mb-1">Paralinguistic tags (click to insert into text):</p>
    <div class="flex flex-wrap gap-1">
      {#each ['[laugh]', '[cough]', '[sigh]', '[gasp]'] as tag}
        <button
          type="button"
          class="text-xs px-2 py-0.5 rounded bg-gray-700 hover:bg-primary-600 transition-colors font-mono cursor-pointer"
          onclick={() => onInsertTag?.(tag)}
        >{tag}</button>
      {/each}
    </div>
  </div>
{/if}

<!-- F5-TTS -->
{#if modelId === 'f5-tts'}
  <div class="space-y-3">
    <div>
      <label class="label" for="f5-ref-text">
        Reference Transcript
        <span
          class="label-hint cursor-help"
          title="Optional: provide the text spoken in the reference audio file. Improves cloning accuracy. Leave empty to use the voice profile's stored transcript."
        >&#9432;</span>
      </label>
      <input
        id="f5-ref-text"
        type="text"
        bind:value={f5RefText}
        {disabled}
        maxlength={300}
        placeholder="Optional: override the voice profile's transcript for this run"
        class="input"
      />
      <p class="text-xs text-gray-400 dark:text-gray-500 mt-1">
        Leave empty to use the voice profile's auto-detected transcript.
      </p>
    </div>

    <div class="grid grid-cols-2 gap-4">
      <div>
        <label class="label" for="f5-nfe-step">
          Quality Steps: {f5NfeStep}
          {#if f5NfeStep === 32}<span class="label-hint">(default)</span>{/if}
          <span
            class="label-hint cursor-help"
            title="Number of denoising iterations. More = higher quality, slower."
          >&#9432;</span>
        </label>
        <input
          id="f5-nfe-step"
          type="range"
          min="8"
          max="64"
          step="1"
          bind:value={f5NfeStep}
          {disabled}
          class="w-full"
        />
      </div>

      <div>
        <label class="label" for="f5-cfg-strength">
          CFG Strength: {f5CfgStrength.toFixed(1)}
          {#if f5CfgStrength === 2.0}<span class="label-hint">(default)</span>{/if}
          <span
            class="label-hint cursor-help"
            title="How closely the output follows the reference voice."
          >&#9432;</span>
        </label>
        <input
          id="f5-cfg-strength"
          type="range"
          min="0.5"
          max="4.0"
          step="0.1"
          bind:value={f5CfgStrength}
          {disabled}
          class="w-full"
        />
      </div>

      <div>
        <label class="label" for="f5-sway">
          Sway Sampling: {f5SwaySamplingCoef.toFixed(1)}
          {#if f5SwaySamplingCoef === -1.0}<span class="label-hint">(default)</span>{/if}
          <span
            class="label-hint cursor-help"
            title="Upstream tuning knob — leave at default unless you know what you're doing."
          >&#9432;</span>
        </label>
        <input
          id="f5-sway"
          type="range"
          min="-1.0"
          max="1.0"
          step="0.1"
          bind:value={f5SwaySamplingCoef}
          {disabled}
          class="w-full"
        />
      </div>

      <div>
        <label class="label" for="f5-target-rms">
          Target Loudness: {f5TargetRms.toFixed(2)}
          {#if f5TargetRms === 0.1}<span class="label-hint">(default)</span>{/if}
          <span
            class="label-hint cursor-help"
            title="Target RMS for output normalization."
          >&#9432;</span>
        </label>
        <input
          id="f5-target-rms"
          type="range"
          min="0.05"
          max="0.3"
          step="0.01"
          bind:value={f5TargetRms}
          {disabled}
          class="w-full"
        />
      </div>
    </div>

    <label class="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300 cursor-pointer select-none">
      <input
        type="checkbox"
        bind:checked={f5RemoveSilence}
        {disabled}
        class="accent-primary-500"
      />
      Remove silence from output
    </label>
  </div>
{/if}

<!-- Orpheus 3B -->
{#if modelId === 'orpheus-3b'}
  <div class="grid grid-cols-2 gap-4">
    <!-- Temperature -->
    <div>
      <label class="label" for="orpheus-temperature">
        Temperature: {orpheusTemperature.toFixed(2)}
        {#if orpheusTemperature === 0.6}<span class="label-hint">(default)</span>{/if}
        <span
          class="label-hint cursor-help"
          title="Controls randomness and expressiveness. 0.6 is a good balance."
        >&#9432;</span>
      </label>
      <input
        id="orpheus-temperature"
        type="range"
        min="0.0"
        max="1.0"
        step="0.05"
        bind:value={orpheusTemperature}
        {disabled}
        class="w-full"
      />
      <p class="text-xs text-gray-400 dark:text-gray-500 mt-1">
        Speech variation and expressiveness
      </p>
    </div>

    <!-- Top-p -->
    <div>
      <label class="label" for="orpheus-top-p">
        Top-p: {orpheusTopP.toFixed(2)}
        {#if orpheusTopP === 0.95}<span class="label-hint">(default)</span>{/if}
        <span
          class="label-hint cursor-help"
          title="Nucleus sampling parameter. Higher = more diverse outputs."
        >&#9432;</span>
      </label>
      <input
        id="orpheus-top-p"
        type="range"
        min="0.0"
        max="1.0"
        step="0.05"
        bind:value={orpheusTopP}
        {disabled}
        class="w-full"
      />
      <p class="text-xs text-gray-400 dark:text-gray-500 mt-1">
        Token selection diversity
      </p>
    </div>
  </div>

  <!-- Emotion tag helpers for Orpheus -->
  <div class="mt-3">
    <p class="text-xs text-gray-400 dark:text-gray-400 mb-1">Emotion tags (click to insert into text):</p>
    <div class="flex flex-wrap gap-1">
      {#each ['<laugh>', '<chuckle>', '<sigh>', '<cough>', '<sniffle>', '<groan>', '<yawn>', '<gasp>'] as tag}
        <button
          type="button"
          class="text-xs px-2 py-0.5 rounded bg-gray-700 hover:bg-primary-600 transition-colors font-mono cursor-pointer"
          onclick={() => onInsertTag?.(tag)}
        >{tag}</button>
      {/each}
    </div>
  </div>
{/if}

<!-- Dia 1.6B -->
{#if modelId === 'dia-1b'}
  <div class="space-y-3">
    <div class="flex items-start gap-2 p-3 rounded-lg bg-blue-50 dark:bg-blue-500/10 border border-blue-200 dark:border-blue-500/20 text-xs text-blue-700 dark:text-blue-300">
      <svg class="w-3.5 h-3.5 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
      <div class="space-y-1">
        <p class="font-medium">Dialogue mode: Use [S1] and [S2] speaker tags</p>
        <p>Example: <code class="bg-blue-100 dark:bg-blue-900/40 px-1 rounded font-mono">[S1] Hello there! [S2] How are you? [S1] I'm doing great!</code></p>
        <p>Nonverbal sounds: <code class="bg-blue-100 dark:bg-blue-900/40 px-1 rounded font-mono">(laughs)</code> <code class="bg-blue-100 dark:bg-blue-900/40 px-1 rounded font-mono">(sighs)</code> <code class="bg-blue-100 dark:bg-blue-900/40 px-1 rounded font-mono">(coughs)</code> <code class="bg-blue-100 dark:bg-blue-900/40 px-1 rounded font-mono">(whispers)</code></p>
      </div>
    </div>

    <div class="grid grid-cols-2 gap-4">
      <div>
        <label class="label" for="dia-cfg-scale">
          CFG Scale: {diaCfgScale.toFixed(1)}
          {#if diaCfgScale === 4.0}<span class="label-hint">(default)</span>{/if}
        </label>
        <input
          id="dia-cfg-scale"
          type="range"
          min="1.0"
          max="10.0"
          step="0.1"
          bind:value={diaCfgScale}
          {disabled}
          class="w-full"
        />
      </div>

      <div>
        <label class="label" for="dia-temperature">
          Temperature: {diaTemperature.toFixed(2)}
          {#if diaTemperature === 1.8}<span class="label-hint">(default)</span>{/if}
        </label>
        <input
          id="dia-temperature"
          type="range"
          min="0.1"
          max="2.5"
          step="0.05"
          bind:value={diaTemperature}
          {disabled}
          class="w-full"
        />
      </div>

      <div>
        <label class="label" for="dia-top-p">
          Top-p: {diaTopP.toFixed(2)}
          {#if diaTopP === 0.9}<span class="label-hint">(default)</span>{/if}
        </label>
        <input
          id="dia-top-p"
          type="range"
          min="0.5"
          max="1.0"
          step="0.01"
          bind:value={diaTopP}
          {disabled}
          class="w-full"
        />
      </div>

      <div>
        <label class="label" for="dia-cfg-filter-top-k">
          CFG Filter Top-k: {diaCfgFilterTopK}
          {#if diaCfgFilterTopK === 50}<span class="label-hint">(default)</span>{/if}
        </label>
        <input
          id="dia-cfg-filter-top-k"
          type="range"
          min="10"
          max="200"
          step="1"
          bind:value={diaCfgFilterTopK}
          {disabled}
          class="w-full"
        />
      </div>
    </div>
  </div>

  <!-- Nonverbal sound chips for Dia -->
  <div class="mt-3">
    <p class="text-xs text-gray-400 dark:text-gray-400 mb-1">Nonverbal sounds (click to insert):</p>
    <div class="flex flex-wrap gap-1">
      {#each ['[S1] ', '[S2] ', '(laughs)', '(sighs)', '(coughs)', '(clears throat)', '(whispers)'] as tag}
        <button
          type="button"
          class="text-xs px-2 py-0.5 rounded bg-gray-700 hover:bg-primary-600 transition-colors font-mono cursor-pointer"
          onclick={() => onInsertTag?.(tag)}
        >{tag}</button>
      {/each}
    </div>
  </div>
{/if}

<!-- CosyVoice 2.0 -->
{#if modelId === 'cosyvoice-2'}
  <div class="space-y-3">
    <div class="flex items-start gap-2 p-3 rounded-lg bg-blue-50 dark:bg-blue-500/10 border border-blue-200 dark:border-blue-500/20 text-xs text-blue-700 dark:text-blue-300">
      <svg class="w-3.5 h-3.5 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
      <div class="space-y-0.5">
        <p><strong>No voice:</strong> cross-lingual synthesis with default speaker</p>
        <p><strong>Voice only:</strong> zero-shot cloning (add transcript below to improve quality)</p>
        <p><strong>Voice + Style:</strong> voice design mode — shape characteristics with the style field</p>
      </div>
    </div>

    <div>
      <label class="label" for="cosy-ref-text">
        Reference Transcript
        <span
          class="label-hint cursor-help"
          title="Transcript of what's spoken in the reference audio. Improves zero-shot cloning accuracy."
        >&#9432;</span>
      </label>
      <input
        id="cosy-ref-text"
        type="text"
        bind:value={cosyRefText}
        {disabled}
        maxlength={300}
        placeholder="Optional: transcript of the reference audio"
        class="input"
      />
    </div>

    <div>
      <label class="label" for="cosy-instruct">
        Speaking Style
        <span
          class="label-hint cursor-help"
          title="Natural language instruction to shape the voice. Requires a voice profile to be selected."
        >&#9432;</span>
      </label>
      <input
        id="cosy-instruct"
        type="text"
        bind:value={cosyInstruct}
        {disabled}
        maxlength={200}
        placeholder="e.g. 'speak softly and gently' or 'sound excited and energetic'"
        class="input"
      />
      <p class="text-xs text-gray-400 dark:text-gray-500 mt-1">
        Describe how the voice should sound — only used when a voice profile is selected
      </p>
      <select
        class="input mt-2 text-sm"
        onchange={(e) => {
          if (e.currentTarget.value) {
            cosyInstruct = e.currentTarget.value;
            e.currentTarget.value = '';
          }
        }}
      >
        <option value="">— Insert example style —</option>
        <option value="Speak in a warm, friendly tone">Warm and friendly</option>
        <option value="Speak softly and gently">Soft and gentle</option>
        <option value="Speak excitedly with high energy">Excited</option>
        <option value="Speak slowly and clearly">Slow and clear</option>
        <option value="Speak with a serious, authoritative tone">Authoritative</option>
      </select>
    </div>
  </div>
{/if}

<!-- Parler TTS -->
{#if modelId === 'parler-tts'}
  <div>
    <label class="label" for="parler-description">
      Voice Description
      <span
        class="label-hint cursor-help"
        title="Parler TTS generates a voice based on a text description — no reference audio needed."
      >&#9432;</span>
    </label>
    <textarea
      id="parler-description"
      bind:value={extras.description as string}
      {disabled}
      rows={3}
      maxlength={400}
      placeholder="Describe the speaker's voice, e.g. 'A female speaker with a slightly expressive voice delivers a clear, engaging speech at a moderate pace in a quiet room.'"
      class="input resize-none"
    ></textarea>
    <p class="text-xs text-gray-400 dark:text-gray-500 mt-1">
      Describe the speaker's voice — no reference audio needed
    </p>

    <!-- Example prompts quick-fill -->
    <select
      class="input mt-2 text-sm"
      onchange={(e) => {
        if (e.currentTarget.value) {
          extras = { ...extras, description: e.currentTarget.value };
          e.currentTarget.value = '';
        }
      }}
    >
      <option value="">— Insert example description —</option>
      <option value="A female speaker with a warm, expressive voice speaking clearly at a moderate pace in a quiet studio.">Warm female voice</option>
      <option value="A deep male voice, slightly gravelly, speaking slowly in a quiet studio.">Deep male voice</option>
      <option value="A young energetic female voice speaking fast with excitement.">Energetic female</option>
      <option value="An older male voice with a calm, authoritative tone reading at a measured pace.">Authoritative male</option>
      <option value="A child's voice speaking clearly and cheerfully at a moderate pace.">Child's voice</option>
    </select>
  </div>
{/if}

<!-- Universal: optional seed -->
{#if modelId && modelId !== 'kokoro'}
  <div class="mt-3">
    <label class="label" for="seed-input">
      Seed
      <span
        class="label-hint cursor-help"
        title="Optional integer for reproducible generation. Leave empty for random."
      >&#9432;</span>
    </label>
    <input
      id="seed-input"
      type="number"
      step="1"
      value={seed}
      oninput={(e) => (seed = (e.currentTarget as HTMLInputElement).value)}
      {disabled}
      placeholder="Leave empty for random"
      class="input w-full sm:w-48"
    />
    <p class="text-xs text-gray-400 dark:text-gray-500 mt-1">
      Same seed + same parameters = identical output (where supported).
    </p>
  </div>
{/if}
