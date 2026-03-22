<!-- About Page -->
<script lang="ts">
  interface ModelCard {
    name: string;
    org: string;
    description: string;
    features: string[];
    vram: string;
    cloning: boolean;
    cloningLabel: string;
    comingSoon: boolean;
    hfLink: string;
    githubLink?: string;
  }

  const models: ModelCard[] = [
    {
      name: 'VibeVoice Realtime 0.5B',
      org: 'Microsoft',
      description: 'Real-time streaming TTS with low latency and high quality.',
      features: [
        '12 built-in voices across 4 languages',
        'Real-time streaming synthesis',
        'End-to-end speech LM with diffusion TTS head',
      ],
      vram: '~4.5 GB',
      cloning: false,
      cloningLabel: 'Pre-made voices only',
      comingSoon: false,
      hfLink: 'https://huggingface.co/microsoft/VibeVoice-Realtime-0.5B',
    },
    {
      name: 'VibeVoice TTS 1.5B',
      org: 'Microsoft (community fork)',
      description: 'Zero-shot voice cloning with multi-speaker, long-form TTS support.',
      features: [
        'Zero-shot voice cloning from 5-30s reference audio',
        'Multi-speaker conversations',
        'Long-form generation up to ~90 minutes',
      ],
      vram: '~12 GB',
      cloning: true,
      cloningLabel: 'Zero-shot cloning',
      comingSoon: false,
      hfLink: 'https://huggingface.co/microsoft/VibeVoice-1.5B',
      githubLink: 'https://github.com/davidamacey/VibeVoice',
    },
    {
      name: 'Fish Audio S2-Pro',
      org: 'Fish Audio',
      description: 'Zero-shot voice cloning with emotion tags and 80+ language support.',
      features: [
        'Zero-shot voice cloning from 3-10s reference audio',
        '80+ languages with emotion tag control',
        'DualAR architecture with DAC codec',
      ],
      vram: '~22 GB',
      cloning: true,
      cloningLabel: 'Zero-shot cloning',
      comingSoon: false,
      hfLink: 'https://huggingface.co/fishaudio/s2-pro',
    },
    {
      name: 'Kokoro 82M',
      org: 'hexgrad',
      description: 'Ultra-lightweight TTS with 50+ preset voices and fast inference.',
      features: [
        '50+ high-quality preset voices',
        'Ultra-fast inference (<1s cached)',
        'Minimal resource footprint',
      ],
      vram: '<1 GB',
      cloning: false,
      cloningLabel: 'Preset voices only',
      comingSoon: false,
      hfLink: 'https://huggingface.co/hexgrad/Kokoro-82M',
    },
    {
      name: 'Qwen3 TTS 1.7B',
      org: 'Alibaba',
      description: 'Large multilingual model with instruction-based style control.',
      features: [
        'Instruction-based style control',
        'Multilingual support',
        'Voice cloning capability',
      ],
      vram: '~10 GB',
      cloning: true,
      cloningLabel: 'Voice cloning',
      comingSoon: false,
      hfLink: 'https://huggingface.co/Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice',
    },
  ];
</script>

<svelte:head>
  <title>About | OpenSpeakers</title>
</svelte:head>

<div class="p-6 max-w-4xl mx-auto space-y-8">
  <!-- Header -->
  <div>
    <h1 class="page-title text-2xl">About OpenSpeakers</h1>
    <p class="page-description mt-2">
      A unified text-to-speech and voice cloning application powered by multiple open-source models
      with hot-swap GPU management.
    </p>
  </div>

  <!-- Overview -->
  <div class="card p-6 space-y-3">
    <h2 class="section-title">What is OpenSpeakers?</h2>
    <p class="text-sm text-gray-600 dark:text-gray-400 leading-relaxed">
      OpenSpeakers brings together the best open-source TTS models into a single application.
      Switch between models on-the-fly with automatic GPU memory management -- only one model
      occupies VRAM at a time, making it practical to run on a single GPU. Generate speech,
      clone voices, and compare outputs across models from one unified interface.
    </p>
  </div>

  <!-- Supported Models -->
  <div class="space-y-4">
    <h2 class="section-title">Supported Models</h2>
    <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
      {#each models as model}
        <div class="card p-5 space-y-3 flex flex-col {model.comingSoon ? 'opacity-70' : ''}">
          <div class="flex items-start justify-between gap-2">
            <div>
              <div class="flex items-center gap-2">
                <h3 class="font-semibold text-sm text-gray-900 dark:text-gray-100">{model.name}</h3>
                {#if model.comingSoon}
                  <span class="text-[10px] font-semibold uppercase tracking-wider px-1.5 py-0.5 rounded bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-400 border border-amber-200 dark:border-amber-500/20">
                    Coming soon
                  </span>
                {/if}
              </div>
              <p class="text-xs text-gray-500 dark:text-gray-500 mt-0.5">{model.org}</p>
            </div>
            <span class="text-xs font-mono text-gray-400 dark:text-gray-500 whitespace-nowrap mt-0.5">{model.vram}</span>
          </div>

          <p class="text-sm text-gray-600 dark:text-gray-400">{model.description}</p>

          <ul class="space-y-1 flex-1">
            {#each model.features as feature}
              <li class="flex items-start gap-2 text-xs text-gray-500 dark:text-gray-400">
                <svg class="w-3.5 h-3.5 text-primary-500 dark:text-primary-400 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
                </svg>
                {feature}
              </li>
            {/each}
          </ul>

          <!-- Cloning badge -->
          <div>
            {#if model.cloning}
              <span class="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full bg-purple-100 text-purple-700 dark:bg-purple-500/15 dark:text-purple-400 border border-purple-200 dark:border-purple-500/20 font-medium">
                <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                </svg>
                {model.cloningLabel}
              </span>
            {:else}
              <span class="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full bg-gray-100 text-gray-500 dark:bg-white/[0.06] dark:text-gray-500 border border-gray-200 dark:border-[#2a2a2f] font-medium">
                {model.cloningLabel}
              </span>
            {/if}
          </div>

          <!-- Links -->
          <div class="flex gap-2 pt-1">
            <a
              href={model.hfLink}
              target="_blank"
              rel="noopener noreferrer"
              class="btn-secondary text-xs px-3 py-1.5"
            >
              <svg class="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 24 24">
                <path d="M12 2C6.477 2 2 6.477 2 12s4.477 10 10 10 10-4.477 10-10S17.523 2 12 2zm-1 15h2v-2h-2v2zm0-4h2V7h-2v6z" />
              </svg>
              HuggingFace
            </a>
            {#if model.githubLink}
              <a
                href={model.githubLink}
                target="_blank"
                rel="noopener noreferrer"
                class="btn-secondary text-xs px-3 py-1.5"
              >
                <svg class="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 24 24">
                  <path d="M12 2C6.477 2 2 6.477 2 12c0 4.42 2.865 8.166 6.839 9.489.5.092.682-.217.682-.482 0-.237-.009-.866-.013-1.7-2.782.604-3.369-1.34-3.369-1.34-.454-1.156-1.11-1.463-1.11-1.463-.908-.62.069-.608.069-.608 1.003.07 1.531 1.03 1.531 1.03.892 1.529 2.341 1.087 2.91.831.092-.646.35-1.086.636-1.336-2.22-.253-4.555-1.11-4.555-4.943 0-1.091.39-1.984 1.029-2.683-.103-.253-.446-1.27.098-2.647 0 0 .84-.269 2.75 1.025A9.564 9.564 0 0112 6.844a9.59 9.59 0 012.504.337c1.909-1.294 2.747-1.025 2.747-1.025.546 1.377.203 2.394.1 2.647.64.699 1.028 1.592 1.028 2.683 0 3.842-2.339 4.687-4.566 4.935.359.309.678.919.678 1.852 0 1.336-.012 2.415-.012 2.743 0 .267.18.578.688.48C19.138 20.163 22 16.418 22 12c0-5.523-4.477-10-10-10z" />
                </svg>
                GitHub
              </a>
            {/if}
          </div>
        </div>
      {/each}
    </div>
  </div>

  <!-- Architecture -->
  <div class="card p-6 space-y-3">
    <h2 class="section-title">Architecture</h2>
    <p class="text-sm text-gray-600 dark:text-gray-400 leading-relaxed">
      OpenSpeakers uses a task-queue architecture designed for single-GPU environments.
      The backend API accepts requests and enqueues them, while a dedicated Celery worker
      handles model loading and inference -- ensuring only one model occupies GPU memory at a time.
    </p>
    <div class="grid grid-cols-2 sm:grid-cols-3 gap-3 mt-3">
      {#each [
        { name: 'FastAPI', role: 'Backend API' },
        { name: 'SvelteKit', role: 'Frontend' },
        { name: 'Celery', role: 'Task Queue' },
        { name: 'Redis', role: 'Message Broker' },
        { name: 'PostgreSQL', role: 'Database' },
        { name: 'Docker', role: 'Containerization' },
      ] as tech}
        <div class="rounded-lg border border-gray-200 dark:border-[#1e1e22] bg-gray-50 dark:bg-white/[0.02] px-3 py-2">
          <p class="text-sm font-medium text-gray-900 dark:text-gray-200">{tech.name}</p>
          <p class="text-xs text-gray-500 dark:text-gray-500">{tech.role}</p>
        </div>
      {/each}
    </div>
  </div>

  <!-- Links -->
  <div class="card p-6 space-y-3">
    <h2 class="section-title">Links</h2>
    <div class="flex flex-wrap gap-3">
      <a
        href="https://github.com/davidamacey/open_speakers"
        target="_blank"
        rel="noopener noreferrer"
        class="btn-secondary"
      >
        <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
          <path d="M12 2C6.477 2 2 6.477 2 12c0 4.42 2.865 8.166 6.839 9.489.5.092.682-.217.682-.482 0-.237-.009-.866-.013-1.7-2.782.604-3.369-1.34-3.369-1.34-.454-1.156-1.11-1.463-1.11-1.463-.908-.62.069-.608.069-.608 1.003.07 1.531 1.03 1.531 1.03.892 1.529 2.341 1.087 2.91.831.092-.646.35-1.086.636-1.336-2.22-.253-4.555-1.11-4.555-4.943 0-1.091.39-1.984 1.029-2.683-.103-.253-.446-1.27.098-2.647 0 0 .84-.269 2.75 1.025A9.564 9.564 0 0112 6.844a9.59 9.59 0 012.504.337c1.909-1.294 2.747-1.025 2.747-1.025.546 1.377.203 2.394.1 2.647.64.699 1.028 1.592 1.028 2.683 0 3.842-2.339 4.687-4.566 4.935.359.309.678.919.678 1.852 0 1.336-.012 2.415-.012 2.743 0 .267.18.578.688.48C19.138 20.163 22 16.418 22 12c0-5.523-4.477-10-10-10z" />
        </svg>
        OpenSpeakers on GitHub
      </a>
      <a
        href="https://github.com/davidamacey/VibeVoice"
        target="_blank"
        rel="noopener noreferrer"
        class="btn-secondary"
      >
        <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
          <path d="M12 2C6.477 2 2 6.477 2 12c0 4.42 2.865 8.166 6.839 9.489.5.092.682-.217.682-.482 0-.237-.009-.866-.013-1.7-2.782.604-3.369-1.34-3.369-1.34-.454-1.156-1.11-1.463-1.11-1.463-.908-.62.069-.608.069-.608 1.003.07 1.531 1.03 1.531 1.03.892 1.529 2.341 1.087 2.91.831.092-.646.35-1.086.636-1.336-2.22-.253-4.555-1.11-4.555-4.943 0-1.091.39-1.984 1.029-2.683-.103-.253-.446-1.27.098-2.647 0 0 .84-.269 2.75 1.025A9.564 9.564 0 0112 6.844a9.59 9.59 0 012.504.337c1.909-1.294 2.747-1.025 2.747-1.025.546 1.377.203 2.394.1 2.647.64.699 1.028 1.592 1.028 2.683 0 3.842-2.339 4.687-4.566 4.935.359.309.678.919.678 1.852 0 1.336-.012 2.415-.012 2.743 0 .267.18.578.688.48C19.138 20.163 22 16.418 22 12c0-5.523-4.477-10-10-10z" />
        </svg>
        VibeVoice Fork
      </a>
    </div>
  </div>
</div>
