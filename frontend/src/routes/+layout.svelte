<script lang="ts">
  import '../app.css';
  import { onMount } from 'svelte';
  import { type Snippet } from 'svelte';
  import { page } from '$app/stores';
  import { refreshModels } from '$stores/models';
  import { initTheme } from '$stores/theme';
  import ThemeToggle from '$components/ThemeToggle.svelte';

  let { children }: { children: Snippet } = $props();

  const navLinks = [
    { href: '/tts', label: 'TTS', icon: 'M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z' },
    { href: '/clone', label: 'Clone Voice', icon: 'M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z' },
    { href: '/compare', label: 'Compare', icon: 'M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z' },
    { href: '/settings', label: 'Settings', icon: 'M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z M15 12a3 3 0 11-6 0 3 3 0 016 0z' },
    { href: '/about', label: 'About', icon: 'M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z' },
  ];

  let currentPath = $derived($page.url.pathname);

  onMount(() => {
    initTheme();
    refreshModels();
  });
</script>

<div class="min-h-screen flex">
  <!-- Sidebar nav -->
  <nav class="sidebar">
    <div class="sidebar-header">
      <h1 class="sidebar-title">OpenSpeakers</h1>
      <p class="sidebar-subtitle">TTS & Voice Cloning</p>
    </div>
    <ul class="flex-1 p-2 space-y-0.5">
      {#each navLinks as link}
        <li>
          <a
            href={link.href}
            class="nav-link {currentPath.startsWith(link.href) ? 'nav-link-active' : ''}"
          >
            <svg class="w-[18px] h-[18px] flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.75" d={link.icon} />
            </svg>
            {link.label}
          </a>
        </li>
      {/each}
    </ul>
    <div class="sidebar-footer">
      <div class="flex items-center justify-between">
        <a
          href="/docs"
          target="_blank"
          rel="noopener"
          class="text-xs text-gray-500 dark:text-gray-500 hover:text-gray-300 transition-colors"
        >
          API Docs ↗
        </a>
        <ThemeToggle />
      </div>
    </div>
  </nav>

  <!-- Main content -->
  <main class="flex-1 overflow-auto">
    {@render children()}
  </main>
</div>
