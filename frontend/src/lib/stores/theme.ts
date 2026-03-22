import { writable } from 'svelte/store';

export type Theme = 'dark' | 'light';

const STORAGE_KEY = 'openspeakers-theme';

export const theme = writable<Theme>('dark');

export function initTheme(): void {
  const stored = localStorage.getItem(STORAGE_KEY) as Theme | null;
  const t = stored === 'light' ? 'light' : 'dark';
  theme.set(t);
  applyTheme(t);
}

export function toggleTheme(): void {
  theme.update((current) => {
    const next = current === 'dark' ? 'light' : 'dark';
    localStorage.setItem(STORAGE_KEY, next);
    applyTheme(next);
    return next;
  });
}

function applyTheme(t: Theme): void {
  if (t === 'dark') {
    document.documentElement.classList.add('dark');
  } else {
    document.documentElement.classList.remove('dark');
  }
}
