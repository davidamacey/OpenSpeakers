<script lang="ts">
  import '../app.css';
  import { onMount } from 'svelte';
  import { page } from '$app/stores';
  import { refreshModels } from '$stores/models';

  const navLinks = [
    { href: '/tts', label: 'TTS', icon: 'M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z' },
    { href: '/clone', label: 'Clone Voice', icon: 'M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z' },
    { href: '/compare', label: 'Compare', icon: 'M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z' },
    { href: '/settings', label: 'Settings', icon: 'M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z M15 12a3 3 0 11-6 0 3 3 0 016 0z' },
  ];

  $: currentPath = $page.url.pathname;

  onMount(() => {
    refreshModels();
  });
</script>

<div class="min-h-screen flex">
  <!-- Sidebar nav -->
  <nav class="w-56 flex-shrink-0 border-r border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 flex flex-col">
    <div class="p-4 border-b border-gray-200 dark:border-gray-700">
      <h1 class="font-bold text-lg text-primary-600 dark:text-primary-400">OpenSpeakers</h1>
      <p class="text-xs text-gray-400 mt-0.5">TTS &amp; Voice Cloning</p>
    </div>
    <ul class="flex-1 p-2 space-y-1">
      {#each navLinks as link}
        <li>
          <a
            href={link.href}
            class="flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors
                   {currentPath.startsWith(link.href)
                     ? 'bg-primary-50 dark:bg-primary-900/30 text-primary-700 dark:text-primary-400'
                     : 'text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700'}"
          >
            <svg class="w-4 h-4 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d={link.icon} />
            </svg>
            {link.label}
          </a>
        </li>
      {/each}
    </ul>
    <div class="p-4 border-t border-gray-200 dark:border-gray-700">
      <a
        href="/docs"
        target="_blank"
        rel="noopener"
        class="text-xs text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
      >
        API Docs ↗
      </a>
    </div>
  </nav>

  <!-- Main content -->
  <main class="flex-1 overflow-auto">
    <slot />
  </main>
</div>
