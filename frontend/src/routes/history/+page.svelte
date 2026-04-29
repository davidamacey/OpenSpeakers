<!-- Job History Page -->
<script lang="ts">
  import { untrack } from 'svelte';
  import { listJobs, getAudioUrl, cancelJob, type JobStatus } from '$api/tts';
  import { models } from '$stores/models';
  import AudioPlayer from '$components/AudioPlayer.svelte';
  import { addToast } from '$lib/stores/toasts';

  interface Job {
    id: string;
    model_id: string;
    text: string;
    status: string;
    duration_seconds: number | null;
    processing_time_ms: number | null;
    created_at: string;
    completed_at: string | null;
    output_path: string | null;
    speaker_similarity?: number | null;
  }

  type SortKey = 'created_at' | 'similarity';
  type SortDir = 'asc' | 'desc';

  let jobs = $state<Job[]>([]);
  let total = $state(0);
  let page = $state(1);
  const PAGE_SIZE = 20;
  let loading = $state(false);
  let statusFilter = $state('all');
  let modelFilter = $state('all');
  let searchQuery = $state('');
  let searchTimeout: ReturnType<typeof setTimeout>;
  let expandedJobId = $state<string | null>(null);
  // Client-side sort applied to the current page of results.
  let sortKey = $state<SortKey>('created_at');
  let sortDir = $state<SortDir>('desc');

  const STATUS_OPTIONS = [
    { value: 'all', label: 'All' },
    { value: 'complete', label: 'Complete' },
    { value: 'running', label: 'Running' },
    { value: 'pending', label: 'Pending' },
    { value: 'failed', label: 'Failed' },
    { value: 'cancelled', label: 'Cancelled' },
  ];

  const STATUS_COLORS: Record<string, string> = {
    complete: 'bg-green-900/50 text-green-300 border-green-700',
    running: 'bg-blue-900/50 text-blue-300 border-blue-700',
    pending: 'bg-yellow-900/50 text-yellow-300 border-yellow-700',
    failed: 'bg-red-900/50 text-red-300 border-red-700',
    cancelled: 'bg-gray-700/50 text-gray-400 border-gray-600',
  };

  async function load() {
    loading = true;
    try {
      const params: NonNullable<Parameters<typeof listJobs>[0]> = {
        page,
        page_size: PAGE_SIZE,
      };
      if (statusFilter !== 'all') params.status = statusFilter as JobStatus;
      if (modelFilter !== 'all') params.model_id = modelFilter;
      if (searchQuery) params.search = searchQuery;

      const res = await listJobs(params);
      jobs = res.jobs as Job[];
      total = res.total;
    } catch (err) {
      console.error('Failed to load job history:', err);
      addToast('error', 'Failed to load job history');
    } finally {
      loading = false;
    }
  }

  function onSearchInput() {
    clearTimeout(searchTimeout);
    // searchQuery isn't in $effect deps (debounced), so call load() directly
    searchTimeout = setTimeout(() => { page = 1; load(); }, 300);
  }

  // $effect runs after initial render AND whenever page/statusFilter/modelFilter change.
  // This replaces onMount for initial load and removes the need to call load() explicitly
  // from filter/pagination handlers.
  $effect(() => {
    // Explicitly track only these — untrack prevents searchQuery inside load() from
    // becoming a dep (it has its own 300ms debounce via onSearchInput).
    const _p = page;
    const _s = statusFilter;
    const _m = modelFilter;
    untrack(() => load());
  });

  const totalPages = $derived(Math.ceil(total / PAGE_SIZE));

  function formatDate(dateStr: string): string {
    return new Date(dateStr).toLocaleString();
  }

  function formatDuration(s: number | null): string {
    if (!s) return '—';
    return `${s.toFixed(1)}s`;
  }

  function formatGenTime(ms: number | null): string {
    if (!ms) return '—';
    return ms < 1000 ? `${ms}ms` : `${(ms / 1000).toFixed(1)}s`;
  }

  function truncateText(text: string, max = 80): string {
    return text.length > max ? text.slice(0, max) + '…' : text;
  }

  function similarityClass(score: number | null | undefined): string {
    if (score == null) return 'text-gray-500';
    if (score >= 0.5) return 'text-green-400';
    if (score >= 0.3) return 'text-amber-400';
    return 'text-red-400';
  }

  function toggleSort(key: SortKey): void {
    if (sortKey === key) {
      sortDir = sortDir === 'asc' ? 'desc' : 'asc';
    } else {
      sortKey = key;
      sortDir = key === 'similarity' ? 'desc' : 'desc';
    }
  }

  // Client-side sort for the visible page. Server already returns
  // newest-first; this re-sorts only the current page when the user picks a
  // different column.
  const sortedJobs = $derived.by(() => {
    const arr = [...jobs];
    arr.sort((a, b) => {
      let cmp = 0;
      if (sortKey === 'similarity') {
        const av = a.speaker_similarity ?? -Infinity;
        const bv = b.speaker_similarity ?? -Infinity;
        cmp = av - bv;
      } else {
        cmp = new Date(a.created_at).getTime() - new Date(b.created_at).getTime();
      }
      return sortDir === 'asc' ? cmp : -cmp;
    });
    return arr;
  });
</script>

<svelte:head><title>Job History — OpenSpeakers</title></svelte:head>

<div class="max-w-6xl mx-auto p-6">
  <h1 class="text-2xl font-bold text-white mb-6">Job History</h1>

  <!-- Filters -->
  <div class="flex flex-wrap gap-3 mb-6">
    <!-- Search input -->
    <input
      type="text"
      placeholder="Search text..."
      bind:value={searchQuery}
      oninput={onSearchInput}
      class="bg-gray-800 border border-gray-600 rounded-lg px-3 py-2 text-white text-sm placeholder-gray-500 focus:border-primary-500 focus:outline-none min-w-48"
    />

    <!-- Status filter chips -->
    <div class="flex flex-wrap gap-1">
      {#each STATUS_OPTIONS as opt}
        <button
          class="px-3 py-1.5 rounded-full text-xs font-medium transition-colors border"
          class:bg-primary-600={statusFilter === opt.value}
          class:border-primary-500={statusFilter === opt.value}
          class:text-white={statusFilter === opt.value}
          class:bg-gray-800={statusFilter !== opt.value}
          class:border-gray-600={statusFilter !== opt.value}
          class:text-gray-400={statusFilter !== opt.value}
          onclick={() => { statusFilter = opt.value; page = 1; }}
        >{opt.label}</button>
      {/each}
    </div>

    <!-- Model filter -->
    <select
      bind:value={modelFilter}
      onchange={() => { page = 1; }}
      class="bg-gray-800 border border-gray-600 rounded-lg px-3 py-2 text-white text-sm focus:border-primary-500 focus:outline-none"
    >
      <option value="all">All models</option>
      {#each models as m}
        <option value={m.id}>{m.name}</option>
      {/each}
    </select>

    <span class="text-gray-500 text-sm self-center">{total} jobs</span>
  </div>

  <!-- Sort toggle row -->
  {#if !loading && jobs.length > 0}
    <div class="flex items-center gap-3 mb-2 text-xs text-gray-400">
      <span>Sort:</span>
      <button
        type="button"
        class="px-2 py-1 rounded transition-colors {sortKey === 'created_at' ? 'bg-gray-700 text-white' : 'hover:bg-gray-800'}"
        onclick={() => toggleSort('created_at')}
      >
        Date {sortKey === 'created_at' ? (sortDir === 'asc' ? '▲' : '▼') : ''}
      </button>
      <button
        type="button"
        class="px-2 py-1 rounded transition-colors {sortKey === 'similarity' ? 'bg-gray-700 text-white' : 'hover:bg-gray-800'}"
        onclick={() => toggleSort('similarity')}
      >
        Match {sortKey === 'similarity' ? (sortDir === 'asc' ? '▲' : '▼') : ''}
      </button>
    </div>
  {/if}

  <!-- Job list -->
  {#if loading}
    <div class="flex justify-center py-12 text-gray-400">Loading…</div>
  {:else if jobs.length === 0}
    <div class="text-center py-12 text-gray-400">No jobs found</div>
  {:else}
    <div class="space-y-2">
      {#each sortedJobs as job (job.id)}
        <div class="bg-gray-800 rounded-xl border border-gray-700 overflow-hidden">
          <!-- Job row -->
          <div class="flex items-center gap-3 px-4 py-3">
            <!-- Model badge -->
            <span class="text-xs bg-gray-700 text-gray-300 px-2 py-0.5 rounded font-mono shrink-0">
              {job.model_id}
            </span>

            <!-- Text (clickable to expand) -->
            <button
              type="button"
              class="flex-1 min-w-0 text-left text-sm text-gray-300 truncate hover:text-white focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 rounded"
              onclick={() => expandedJobId = expandedJobId === job.id ? null : job.id}
              title={job.text}
              aria-expanded={expandedJobId === job.id}
            >{truncateText(job.text)}</button>

            <!-- Status badge -->
            <span class="text-xs px-2 py-0.5 rounded border shrink-0 {STATUS_COLORS[job.status] ?? 'bg-gray-700/50 text-gray-400 border-gray-600'}">
              {job.status}
            </span>

            <!-- Duration -->
            <span class="text-xs text-gray-500 shrink-0 w-12 text-right">{formatDuration(job.duration_seconds)}</span>

            <!-- Gen time -->
            <span class="text-xs text-gray-500 shrink-0 w-16 text-right">{formatGenTime(job.processing_time_ms)}</span>

            <!-- Speaker similarity -->
            <span
              class="text-xs shrink-0 w-12 text-right tabular-nums {similarityClass(job.speaker_similarity)}"
              title={job.speaker_similarity != null
                ? `Voice match: ${job.speaker_similarity.toFixed(2)}`
                : 'No similarity score (no voice profile or scoring not yet run)'}
            >
              {job.speaker_similarity != null ? job.speaker_similarity.toFixed(2) : '—'}
            </span>

            <!-- Date -->
            <span class="text-xs text-gray-500 shrink-0 hidden md:block">{formatDate(job.created_at)}</span>

            <!-- Actions -->
            <div class="flex gap-1 shrink-0">
              {#if job.status === 'complete' && job.id}
                <button
                  class="text-xs text-primary-400 hover:text-primary-300 px-2 py-1 rounded hover:bg-gray-700 transition-colors"
                  onclick={() => expandedJobId = expandedJobId === job.id ? null : job.id}
                  aria-label="Play audio"
                >▶</button>
                <a
                  href={getAudioUrl(job.id)}
                  download
                  class="text-xs text-gray-400 hover:text-white px-2 py-1 rounded hover:bg-gray-700 transition-colors"
                  aria-label="Download"
                >↓</a>
              {/if}
              {#if job.status === 'pending' || job.status === 'running'}
                <button
                  class="text-xs text-red-400 hover:text-red-300 px-2 py-1 rounded hover:bg-gray-700 transition-colors"
                  onclick={async () => {
                    try { await cancelJob(job.id); addToast('info', 'Job cancelled'); load(); }
                    catch { addToast('error', 'Failed to cancel'); }
                  }}
                  aria-label="Cancel job"
                >✕</button>
              {/if}
            </div>
          </div>

          <!-- Expanded audio player -->
          {#if expandedJobId === job.id && job.status === 'complete'}
            <div class="px-4 pb-4 border-t border-gray-700 pt-3">
              <p class="text-xs text-gray-500 mb-2 select-all break-all">{job.text}</p>
              <AudioPlayer src={getAudioUrl(job.id)} />
            </div>
          {/if}
        </div>
      {/each}
    </div>

    <!-- Pagination -->
    {#if totalPages > 1}
      <div class="flex items-center justify-center gap-4 mt-6">
        <button
          disabled={page <= 1}
          onclick={() => { page--; }}
          class="px-4 py-2 rounded-lg bg-gray-700 text-white disabled:opacity-40 disabled:cursor-not-allowed hover:bg-gray-600 transition-colors text-sm"
        >← Previous</button>
        <span class="text-gray-400 text-sm">Page {page} of {totalPages}</span>
        <button
          disabled={page >= totalPages}
          onclick={() => { page++; }}
          class="px-4 py-2 rounded-lg bg-gray-700 text-white disabled:opacity-40 disabled:cursor-not-allowed hover:bg-gray-600 transition-colors text-sm"
        >Next →</button>
      </div>
    {/if}
  {/if}
</div>
