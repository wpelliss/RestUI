<script lang="ts">
  /**
   * DataTable.svelte — Island Svelte 5
   *
   * Props:
   *   initialData   — données pré-fetchées SSR (zéro flash au premier rendu)
   *   columns       — [{ key, label, filterable? }] — reconstruit par [endpoint].astro
   *   filters       — état initial des filtres depuis query params SSR
   *   endpointName  — nom de l'endpoint pour fetch /api/data?endpoint=<name>
   *   endpointLabel — label affiché dans le header de la card
   *   initialError  — message d'erreur SSR éventuel (données non chargées)
   *
   * États (machine à 5 états mutuellement exclusifs) :
   *   LOADING_INITIAL  — skeleton rows, headers visibles
   *   LOADING_REFRESH  — table existante + overlay spinner
   *   ERROR            — alerte rouge + bouton Réessayer
   *   EMPTY            — aucune donnée (API vide)
   *   NO_RESULTS       — filtres actifs, zéro match
   *   POPULATED        — table complète avec données
   *
   * URL-shareability :
   *   $effect → history.replaceState à chaque changement de filtre/tri/page.
   *   Params internes préfixés _ (_sort, _dir, _page) pour ne pas conflitter
   *   avec les clés de filtre.
   *
   * Filtrage client-side :
   *   Les données complètes sont chargées une fois, le filtrage est local.
   *   Sur changement de filtre → fetch vers /api/data (avec filtres backend)
   *   pour garder la cohérence avec la logique serveur (substring case-insensitive).
   */

  import { onMount } from 'svelte';

  // ---------------------------------------------------------------------------
  // Types
  // ---------------------------------------------------------------------------

  interface Column {
    key: string;
    label: string;
    filterable?: boolean;
  }

  type Row = Record<string, unknown>;

  // ---------------------------------------------------------------------------
  // Props (Svelte 5 runes)
  // ---------------------------------------------------------------------------

  interface Props {
    initialData:   Row[];
    columns:       Column[];
    filters:       Record<string, string>;
    endpointName:  string;
    endpointLabel: string;
    initialError?: string | null;
  }

  let {
    initialData,
    columns,
    filters: initialFilters,
    endpointName,
    endpointLabel,
    initialError = null,
  }: Props = $props();

  // ---------------------------------------------------------------------------
  // State
  // ---------------------------------------------------------------------------

  let data          = $state<Row[]>(initialData ?? []);
  let loadingInit   = $state(initialData.length === 0 && !initialError);
  let loadingRefresh= $state(false);
  let error         = $state<string | null>(initialError ?? null);

  let activeFilters = $state<Record<string, string>>({ ...initialFilters });

  // Valeurs dans les inputs (non encore soumises)
  let pendingFilters = $state<Record<string, string>>({ ...initialFilters });

  let sortKey   = $state('');
  let sortDir   = $state<'asc' | 'desc'>('asc');
  const PAGE_SIZE = 25;
  let currentPage = $state(0);

  // ---------------------------------------------------------------------------
  // Helpers
  // ---------------------------------------------------------------------------

  function getNestedValue(obj: Row, path: string): unknown {
    return path.split('.').reduce<unknown>((acc, key) => {
      if (acc !== null && acc !== undefined && typeof acc === 'object') {
        return (acc as Record<string, unknown>)[key];
      }
      return undefined;
    }, obj);
  }

  function displayValue(val: unknown): string {
    if (val === null || val === undefined) return '';
    if (typeof val === 'object') return JSON.stringify(val);
    return String(val);
  }

  // ---------------------------------------------------------------------------
  // Derived
  // ---------------------------------------------------------------------------

  let filtered = $derived.by(() => {
    return data.filter((row) =>
      Object.entries(activeFilters).every(([key, val]) => {
        if (!val) return true;
        const cellVal = displayValue(getNestedValue(row, key));
        return cellVal.toLowerCase().includes(val.toLowerCase());
      })
    );
  });

  let sorted = $derived.by(() => {
    if (!sortKey) return filtered;
    return [...filtered].sort((a, b) => {
      const av = displayValue(getNestedValue(a, sortKey));
      const bv = displayValue(getNestedValue(b, sortKey));
      const cmp = av < bv ? -1 : av > bv ? 1 : 0;
      return sortDir === 'asc' ? cmp : -cmp;
    });
  });

  let paginated   = $derived(sorted.slice(currentPage * PAGE_SIZE, (currentPage + 1) * PAGE_SIZE));
  let totalPages  = $derived(Math.ceil(filtered.length / PAGE_SIZE));
  let filterCount = $derived(Object.values(activeFilters).filter(Boolean).length);

  let filterableColumns = $derived(columns.filter((c) => c.filterable));

  // Machine à états — 5 états mutuellement exclusifs
  let uiState = $derived.by((): 'loading_initial' | 'loading_refresh' | 'error' | 'empty' | 'no_results' | 'populated' => {
    if (loadingInit)    return 'loading_initial';
    if (error)          return 'error';
    if (loadingRefresh) return 'loading_refresh'; // table visible sous overlay
    if (data.length === 0) return 'empty';
    if (filtered.length === 0) return 'no_results';
    return 'populated';
  });

  // ---------------------------------------------------------------------------
  // URL sync
  // ---------------------------------------------------------------------------

  $effect(() => {
    const params = new URLSearchParams();
    Object.entries(activeFilters).forEach(([k, v]) => { if (v) params.set(k, v); });
    if (sortKey) params.set('_sort', sortKey);
    if (sortDir !== 'asc') params.set('_dir', sortDir);
    if (currentPage !== 0) params.set('_page', String(currentPage));
    const newUrl = `${window.location.pathname}${params.toString() ? '?' + params.toString() : ''}`;
    window.history.replaceState({}, '', newUrl);
  });

  // Reset pagination sur changement de filtre/tri
  $effect(() => {
    void JSON.stringify(activeFilters);
    void sortKey;
    currentPage = 0;
  });

  // ---------------------------------------------------------------------------
  // Fetch
  // ---------------------------------------------------------------------------

  onMount(async () => {
    if (initialData && initialData.length > 0) {
      loadingInit = false;
      return;
    }
    if (initialError) {
      loadingInit = false;
      return;
    }
    await fetchData();
  });

  async function fetchData() {
    const isRefresh = data.length > 0;
    if (isRefresh) {
      loadingRefresh = true;
    } else {
      loadingInit = true;
    }
    error = null;

    try {
      const params = new URLSearchParams({ endpoint: endpointName });
      Object.entries(activeFilters).forEach(([k, v]) => { if (v) params.set(k, v); });

      const res = await fetch(`/api/data?${params.toString()}`);
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail ?? `Le backend a répondu ${res.status}`);
      }
      const json = await res.json();
      data = Array.isArray(json) ? json : (json.rows ?? []);
    } catch (err) {
      error = err instanceof Error ? err.message : 'Erreur inconnue';
      data = [];
    } finally {
      loadingInit    = false;
      loadingRefresh = false;
    }
  }

  // ---------------------------------------------------------------------------
  // Handlers
  // ---------------------------------------------------------------------------

  function submitFilters() {
    activeFilters = { ...pendingFilters };
    fetchData();
  }

  function handleFilterKeydown(e: KeyboardEvent) {
    if (e.key === 'Enter') submitFilters();
  }

  function clearOneFilter(key: string) {
    const next = { ...activeFilters };
    delete next[key];
    activeFilters = next;
    pendingFilters = { ...next };
    fetchData();
  }

  function clearAllFilters() {
    activeFilters  = {};
    pendingFilters = {};
    sortKey = '';
    sortDir = 'asc';
    currentPage = 0;
    fetchData();
  }

  function toggleSort(key: string) {
    if (sortKey === key) {
      sortDir = sortDir === 'asc' ? 'desc' : 'asc';
    } else {
      sortKey = key;
      sortDir = 'asc';
    }
  }

  function applyInlineFilter(key: string, value: string) {
    if (activeFilters[key] === value) return; // déjà actif — pas de double submit
    pendingFilters = { ...pendingFilters, [key]: value };
    activeFilters  = { ...activeFilters, [key]: value };
    fetchData();
  }

  // Largeurs aléatoires pour skeleton (calculées une seule fois à l'init)
  const skeletonWidths = Array.from({ length: 5 }, () =>
    columns.map(() => 60 + Math.floor(Math.random() * 80))
  );
</script>

<!-- =========================================================================
     TEMPLATE
========================================================================== -->

<div class="space-y-4">

  <!-- === FILTRES — toujours visibles (Don't Make Me Think) === -->
  {#if filterableColumns.length > 0}
    <div class="bg-white rounded-xl border border-slate-200 shadow-sm p-5">

      <!-- Barre d'inputs -->
      <div class="flex flex-wrap gap-3 items-end">
        {#each filterableColumns as col}
          <div class="flex flex-col gap-1 min-w-[140px]">
            <label
              for="filter-{col.key}"
              class="text-xs font-semibold text-slate-500 uppercase tracking-wider"
            >
              {col.label}
            </label>
            <div class="relative">
              <input
                id="filter-{col.key}"
                type="text"
                value={pendingFilters[col.key] ?? ''}
                oninput={(e) => {
                  const val = (e.target as HTMLInputElement).value;
                  pendingFilters = { ...pendingFilters, [col.key]: val };
                }}
                onkeydown={handleFilterKeydown}
                placeholder="Filtrer…"
                class="
                  w-full px-3 py-2 pr-7 text-sm rounded-lg border border-slate-200
                  focus:outline-none focus:ring-2 focus:ring-blue-500/30 focus:border-blue-500
                  placeholder-slate-300 text-slate-700 transition-colors duration-150
                "
              />
              {#if pendingFilters[col.key]}
                <button
                  type="button"
                  onclick={() => {
                    pendingFilters = { ...pendingFilters, [col.key]: '' };
                    clearOneFilter(col.key);
                  }}
                  class="
                    absolute right-2 top-1/2 -translate-y-1/2
                    text-slate-300 hover:text-slate-500 transition-colors
                  "
                  aria-label="Effacer le filtre {col.label}"
                >
                  <!-- Heroicons: x-mark (mini) -->
                  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="w-3.5 h-3.5">
                    <path d="M6.28 5.22a.75.75 0 0 0-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 1 0 1.06 1.06L10 11.06l3.72 3.72a.75.75 0 1 0 1.06-1.06L11.06 10l3.72-3.72a.75.75 0 0 0-1.06-1.06L10 8.94 6.28 5.22Z" />
                  </svg>
                </button>
              {/if}
            </div>
          </div>
        {/each}

        <!-- Bouton Appliquer -->
        <button
          type="button"
          onclick={submitFilters}
          disabled={loadingRefresh || loadingInit}
          class="
            flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium
            bg-blue-600 text-white hover:bg-blue-700
            disabled:opacity-50 disabled:cursor-not-allowed
            transition-colors duration-150
          "
        >
          <!-- Heroicons: magnifying-glass (mini) -->
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="w-4 h-4">
            <path fill-rule="evenodd"
              d="M9 3.5a5.5 5.5 0 1 0 0 11 5.5 5.5 0 0 0 0-11ZM2 9a7 7 0 1 1 12.452 4.391l3.328 3.329a.75.75 0 1 1-1.06 1.06l-3.329-3.328A7 7 0 0 1 2 9Z"
              clip-rule="evenodd" />
          </svg>
          Appliquer
        </button>

        {#if filterCount > 0}
          <button
            type="button"
            onclick={clearAllFilters}
            class="flex items-center gap-1 text-xs text-slate-400 hover:text-slate-600 transition-colors"
          >
            <!-- Heroicons: x-mark (mini) -->
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="w-3.5 h-3.5">
              <path d="M6.28 5.22a.75.75 0 0 0-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 1 0 1.06 1.06L10 11.06l3.72 3.72a.75.75 0 1 0 1.06-1.06L11.06 10l3.72-3.72a.75.75 0 0 0-1.06-1.06L10 8.94 6.28 5.22Z" />
            </svg>
            Tout effacer
          </button>
        {/if}
      </div>

      <!-- Chips filtres actifs -->
      {#if filterCount > 0}
        <div class="flex flex-wrap gap-2 mt-3">
          {#each Object.entries(activeFilters).filter(([, v]) => v) as [key, val]}
            <span class="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-blue-50 text-blue-700 text-xs font-medium">
              <span class="text-blue-500 font-semibold">{key}</span>
              <span>:</span>
              <span>{val}</span>
              <button
                type="button"
                onclick={() => clearOneFilter(key)}
                class="ml-0.5 rounded-full hover:text-blue-900 transition-colors"
                aria-label="Retirer le filtre {key}"
              >
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="w-3 h-3">
                  <path d="M6.28 5.22a.75.75 0 0 0-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 1 0 1.06 1.06L10 11.06l3.72 3.72a.75.75 0 1 0 1.06-1.06L11.06 10l3.72-3.72a.75.75 0 0 0-1.06-1.06L10 8.94 6.28 5.22Z" />
                </svg>
              </button>
            </span>
          {/each}
        </div>
      {/if}

    </div>
  {/if}

  <!-- === CARD TABLE === -->
  <div class="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">

    <!-- Header card -->
    <div class="flex items-center justify-between gap-4 px-5 py-3.5 border-b border-slate-100">
      <h3 class="font-semibold text-slate-700 text-sm">{endpointLabel}</h3>
      <div class="flex items-center gap-3">
        {#if uiState === 'loading_refresh'}
          <span class="flex items-center gap-1.5 text-xs text-slate-400">
            <!-- Heroicons: arrow-path (mini) spinning -->
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor"
                 class="w-4 h-4 text-blue-600 animate-spin">
              <path fill-rule="evenodd"
                d="M15.312 11.424a5.5 5.5 0 0 1-9.201 2.466l-.312-.311h2.433a.75.75 0 0 0 0-1.5H3.989a.75.75 0 0 0-.75.75v4.242a.75.75 0 0 0 1.5 0v-2.43l.31.31a7 7 0 0 0 11.712-3.138.75.75 0 0 0-1.449-.39Zm1.23-3.723a.75.75 0 0 0 .219-.53V2.929a.75.75 0 0 0-1.5 0V5.36l-.31-.31A7 7 0 0 0 3.239 8.188a.75.75 0 1 0 1.448.389A5.5 5.5 0 0 1 13.89 6.11l.311.31h-2.432a.75.75 0 0 0 0 1.5h4.243a.75.75 0 0 0 .53-.219Z"
                clip-rule="evenodd" />
            </svg>
            Chargement…
          </span>
        {:else if uiState === 'populated' || uiState === 'no_results'}
          <span class="text-xs text-slate-400" aria-live="polite">
            {filtered.length} résultat{filtered.length > 1 ? 's' : ''}
            {#if data.length !== filtered.length}
              <span class="text-slate-300">(sur {data.length})</span>
            {/if}
          </span>
        {/if}

        <!-- Bouton rafraîchir -->
        <button
          type="button"
          onclick={fetchData}
          disabled={loadingInit || loadingRefresh}
          title="Rafraîchir les données"
          aria-label="Rafraîchir les données"
          class="
            w-7 h-7 rounded-lg border border-slate-200
            text-slate-400 hover:text-blue-600 hover:border-blue-300
            flex items-center justify-center
            transition-colors duration-150
            disabled:opacity-40 disabled:cursor-not-allowed
          "
        >
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="w-3.5 h-3.5">
            <path fill-rule="evenodd"
              d="M15.312 11.424a5.5 5.5 0 0 1-9.201 2.466l-.312-.311h2.433a.75.75 0 0 0 0-1.5H3.989a.75.75 0 0 0-.75.75v4.242a.75.75 0 0 0 1.5 0v-2.43l.31.31a7 7 0 0 0 11.712-3.138.75.75 0 0 0-1.449-.39Zm1.23-3.723a.75.75 0 0 0 .219-.53V2.929a.75.75 0 0 0-1.5 0V5.36l-.31-.31A7 7 0 0 0 3.239 8.188a.75.75 0 1 0 1.448.389A5.5 5.5 0 0 1 13.89 6.11l.311.31h-2.432a.75.75 0 0 0 0 1.5h4.243a.75.75 0 0 0 .53-.219Z"
              clip-rule="evenodd" />
          </svg>
        </button>
      </div>
    </div>

    <!-- ===== ÉTAT : LOADING_INITIAL (skeleton) ===== -->
    {#if uiState === 'loading_initial'}
      <div class="overflow-x-auto" aria-busy="true" aria-label="Chargement des données…">
        <table class="min-w-full divide-y divide-slate-100 text-sm" aria-hidden="true">
          <thead class="bg-slate-50">
            <tr>
              {#each columns as col}
                <th scope="col" class="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider whitespace-nowrap">
                  {col.label}
                </th>
              {/each}
            </tr>
          </thead>
          <tbody class="bg-white divide-y divide-slate-50">
            {#each skeletonWidths as widths, _i}
              <tr>
                {#each widths as w, _j}
                  <td class="px-4 py-3">
                    <div
                      class="h-3.5 rounded animate-pulse bg-gradient-to-r from-slate-200 via-slate-100 to-slate-200 bg-[length:400px_100%]"
                      style="width: {w}px;"
                    ></div>
                  </td>
                {/each}
              </tr>
            {/each}
          </tbody>
        </table>
      </div>

    <!-- ===== ÉTAT : ERROR ===== -->
    {:else if uiState === 'error'}
      <div class="flex flex-col items-center justify-center gap-3 px-6 py-12 text-center" role="alert">
        <!-- Heroicons: exclamation-triangle -->
        <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"
             stroke-width="1.5" stroke="currentColor" class="w-10 h-10 text-red-400">
          <path stroke-linecap="round" stroke-linejoin="round"
            d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126ZM12 15.75h.008v.008H12v-.008Z" />
        </svg>
        <div>
          <p class="font-semibold text-slate-700 text-sm">Impossible de charger les données</p>
          <p class="text-xs text-slate-500 mt-1 max-w-sm">{error}</p>
        </div>
        <button
          type="button"
          onclick={fetchData}
          class="mt-1 px-4 py-2 rounded-lg text-sm font-medium bg-blue-600 text-white hover:bg-blue-700 transition-colors"
        >
          Réessayer
        </button>
      </div>

    <!-- ===== ÉTATS : POPULATED ou LOADING_REFRESH (table visible) ===== -->
    {:else if uiState === 'populated' || uiState === 'loading_refresh' || uiState === 'no_results'}
      <div class="relative overflow-x-auto">

        <!-- Overlay loading refresh (données existantes restent visibles) -->
        {#if uiState === 'loading_refresh'}
          <div
            class="absolute inset-0 bg-slate-50/70 flex items-center justify-center z-10"
            aria-live="polite"
            aria-label="Actualisation…"
          >
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor"
                 class="w-8 h-8 text-blue-600 animate-spin">
              <path fill-rule="evenodd"
                d="M15.312 11.424a5.5 5.5 0 0 1-9.201 2.466l-.312-.311h2.433a.75.75 0 0 0 0-1.5H3.989a.75.75 0 0 0-.75.75v4.242a.75.75 0 0 0 1.5 0v-2.43l.31.31a7 7 0 0 0 11.712-3.138.75.75 0 0 0-1.449-.39Zm1.23-3.723a.75.75 0 0 0 .219-.53V2.929a.75.75 0 0 0-1.5 0V5.36l-.31-.31A7 7 0 0 0 3.239 8.188a.75.75 0 1 0 1.448.389A5.5 5.5 0 0 1 13.89 6.11l.311.31h-2.432a.75.75 0 0 0 0 1.5h4.243a.75.75 0 0 0 .53-.219Z"
                clip-rule="evenodd" />
            </svg>
          </div>
        {/if}

        <table class="min-w-full divide-y divide-slate-100 text-sm" aria-label={endpointLabel}>
          <thead class="bg-slate-50">
            <tr>
              {#each columns as col}
                <th
                  scope="col"
                  onclick={() => toggleSort(col.key)}
                  class="
                    px-4 py-3 text-left text-xs font-semibold
                    text-slate-500 uppercase tracking-wider
                    cursor-pointer select-none whitespace-nowrap
                    hover:bg-slate-100 transition-colors duration-100
                  "
                  aria-sort={sortKey === col.key ? (sortDir === 'asc' ? 'ascending' : 'descending') : 'none'}
                >
                  <span class="flex items-center gap-1.5">
                    {col.label}
                    {#if sortKey === col.key}
                      <!-- Heroicons: chevron-up/down (mini) -->
                      {#if sortDir === 'asc'}
                        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="w-3 h-3 text-blue-600">
                          <path fill-rule="evenodd" d="M10 17a.75.75 0 0 1-.75-.75V5.612L5.29 9.77a.75.75 0 0 1-1.08-1.04l5.25-5.5a.75.75 0 0 1 1.08 0l5.25 5.5a.75.75 0 1 1-1.08 1.04l-3.96-4.158V16.25A.75.75 0 0 1 10 17Z" clip-rule="evenodd"/>
                        </svg>
                      {:else}
                        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="w-3 h-3 text-blue-600">
                          <path fill-rule="evenodd" d="M10 3a.75.75 0 0 1 .75.75v10.638l3.96-4.158a.75.75 0 1 1 1.08 1.04l-5.25 5.5a.75.75 0 0 1-1.08 0l-5.25-5.5a.75.75 0 1 1 1.08-1.04l3.96 4.158V3.75A.75.75 0 0 1 10 3Z" clip-rule="evenodd"/>
                        </svg>
                      {/if}
                    {:else}
                      <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="w-3 h-3 text-slate-300">
                        <path fill-rule="evenodd" d="M2.24 6.8a.75.75 0 0 0 1.06-.04l1.95-2.1v8.59a.75.75 0 0 0 1.5 0V4.66l1.95 2.1a.75.75 0 1 0 1.1-1.02L7.35 3.16a.75.75 0 0 0-1.1 0L4.2 5.8a.75.75 0 0 0-.04 1.06Zm13.52-.04a.75.75 0 0 0-1.06.04l-1.95 2.1V4.66a.75.75 0 0 0-1.5 0v8.59l-1.95-2.1a.75.75 0 1 0-1.1 1.02l2.5 2.62a.75.75 0 0 0 1.1 0l2.5-2.62a.75.75 0 0 0 .04-1.06Z" clip-rule="evenodd"/>
                      </svg>
                    {/if}
                  </span>
                </th>
              {/each}
            </tr>
          </thead>

          <tbody class="bg-white divide-y divide-slate-50">
            {#if uiState === 'no_results'}
              <tr>
                <td colspan={columns.length} class="px-4 py-16 text-center">
                  <div class="flex flex-col items-center gap-3 text-slate-400">
                    <!-- Heroicons: magnifying-glass -->
                    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"
                         stroke-width="1.5" stroke="currentColor" class="w-8 h-8 opacity-50">
                      <path stroke-linecap="round" stroke-linejoin="round"
                        d="m21 21-5.197-5.197m0 0A7.5 7.5 0 1 0 5.196 15.803 7.5 7.5 0 0 0 15.803 15.803Z" />
                    </svg>
                    <p class="text-sm font-medium text-slate-500">Aucun résultat pour ces filtres</p>
                    <button
                      type="button"
                      onclick={clearAllFilters}
                      class="text-xs text-blue-600 hover:text-blue-700 hover:underline transition-colors"
                    >
                      Réinitialiser les filtres
                    </button>
                  </div>
                </td>
              </tr>
            {:else}
              {#each paginated as row, _i}
                <tr class="hover:bg-slate-50 transition-colors duration-100 group">
                  {#each columns as col}
                    {@const rawVal = getNestedValue(row, col.key)}
                    {@const val    = displayValue(rawVal)}
                    <td class="px-4 py-2.5 text-slate-700 whitespace-nowrap max-w-xs">
                      {#if col.filterable && val}
                        <div class="flex items-center gap-1.5 group/cell">
                          <!-- Bouton loupe — visible au hover de la ligne -->
                          <button
                            type="button"
                            onclick={() => applyInlineFilter(col.key, val)}
                            title="Filtrer par : {val}"
                            aria-label="Filtrer par {col.label} : {val}"
                            class="
                              opacity-0 group-hover:opacity-100 focus:opacity-100
                              flex-shrink-0 w-5 h-5 rounded
                              text-slate-300 hover:text-blue-600 hover:bg-blue-50
                              flex items-center justify-center
                              transition-all duration-100
                            "
                          >
                            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="w-3.5 h-3.5">
                              <path fill-rule="evenodd"
                                d="M9 3.5a5.5 5.5 0 1 0 0 11 5.5 5.5 0 0 0 0-11ZM2 9a7 7 0 1 1 12.452 4.391l3.328 3.329a.75.75 0 1 1-1.06 1.06l-3.329-3.328A7 7 0 0 1 2 9Z"
                                clip-rule="evenodd" />
                            </svg>
                          </button>
                          <span class="truncate" title={val}>{val}</span>
                        </div>
                      {:else}
                        <span class="truncate block" title={val}>{val || '—'}</span>
                      {/if}
                    </td>
                  {/each}
                </tr>
              {/each}
            {/if}
          </tbody>
        </table>
      </div>

      <!-- ===== ÉTAT : EMPTY (données vides, pas de filtres actifs) ===== -->

    {:else if uiState === 'empty'}
      <div class="flex flex-col items-center justify-center gap-3 py-16 text-slate-400" role="status">
        <!-- Heroicons: table-cells -->
        <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"
             stroke-width="1.5" stroke="currentColor" class="w-10 h-10 opacity-40">
          <path stroke-linecap="round" stroke-linejoin="round"
            d="M3.375 19.5h17.25m-17.25 0a1.125 1.125 0 0 1-1.125-1.125M3.375 19.5h1.5C5.496 19.5 6 18.996 6 18.375m-3.75 0V5.625m0 12.75v-1.5c0-.621.504-1.125 1.125-1.125m18.375 2.625V5.625m0 12.75c0 .621-.504 1.125-1.125 1.125m1.125-1.125v-1.5c0-.621-.504-1.125-1.125-1.125m0 3.75h-1.5A1.125 1.125 0 0 1 18 18.375M20.625 4.5H3.375m17.25 0c.621 0 1.125.504 1.125 1.125M20.625 4.5h-1.5C18.504 4.5 18 5.004 18 5.625m3.75 0v1.5c0 .621-.504 1.125-1.125 1.125M3.375 4.5c-.621 0-1.125.504-1.125 1.125M3.375 4.5h1.5C5.496 4.5 6 5.004 6 5.625m-3.75 0v1.5c0 .621.504 1.125 1.125 1.125m0 0h1.5" />
        </svg>
        <p class="text-sm font-medium text-slate-500">Aucune donnée disponible</p>
        <p class="text-xs text-slate-400">L'API a répondu mais ne contient aucun enregistrement.</p>
      </div>
    {/if}

    <!-- ===== PAGINATION ===== -->
    {#if uiState === 'populated' && totalPages > 1}
      <div class="flex items-center justify-between gap-4 px-5 py-3 border-t border-slate-100 bg-slate-50">
        <span class="text-xs text-slate-400">
          Page {currentPage + 1} / {totalPages}
          <span class="text-slate-300 ml-1">({filtered.length} résultats)</span>
        </span>
        <div class="flex items-center gap-1">
          <!-- Première page -->
          <button
            type="button"
            onclick={() => { currentPage = 0; }}
            disabled={currentPage === 0}
            aria-label="Première page"
            class="px-2 py-1 text-xs rounded border border-slate-200 disabled:opacity-30 hover:bg-white transition-colors"
          >
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="w-3 h-3">
              <path fill-rule="evenodd" d="M15.78 14.78a.75.75 0 0 1-1.06 0l-4.25-4.25a.75.75 0 0 1 0-1.06l4.25-4.25a.75.75 0 1 1 1.06 1.06L12.06 10l3.72 3.72a.75.75 0 0 1 0 1.06Zm-6 0a.75.75 0 0 1-1.06 0L4.47 10.53a.75.75 0 0 1 0-1.06l4.25-4.25a.75.75 0 1 1 1.06 1.06L6.06 10l3.72 3.72a.75.75 0 0 1 0 1.06Z" clip-rule="evenodd"/>
            </svg>
          </button>
          <!-- Page précédente -->
          <button
            type="button"
            onclick={() => { currentPage--; }}
            disabled={currentPage === 0}
            aria-label="Page précédente"
            class="px-2 py-1 text-xs rounded border border-slate-200 disabled:opacity-30 hover:bg-white transition-colors"
          >
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="w-3 h-3">
              <path fill-rule="evenodd" d="M11.78 5.22a.75.75 0 0 1 0 1.06L8.06 10l3.72 3.72a.75.75 0 1 1-1.06 1.06l-4.25-4.25a.75.75 0 0 1 0-1.06l4.25-4.25a.75.75 0 0 1 1.06 0Z" clip-rule="evenodd"/>
            </svg>
          </button>

          <!-- Pages autour de la courante -->
          {#each Array.from({ length: totalPages }, (_, i) => i).filter((p) => Math.abs(p - currentPage) <= 2) as p}
            <button
              type="button"
              onclick={() => { currentPage = p; }}
              aria-label="Page {p + 1}"
              aria-current={p === currentPage ? 'page' : undefined}
              class="
                w-7 h-7 text-xs rounded border transition-colors
                {p === currentPage
                  ? 'bg-blue-600 text-white border-blue-600 font-bold'
                  : 'border-slate-200 hover:bg-white text-slate-600'}
              "
            >
              {p + 1}
            </button>
          {/each}

          <!-- Page suivante -->
          <button
            type="button"
            onclick={() => { currentPage++; }}
            disabled={currentPage >= totalPages - 1}
            aria-label="Page suivante"
            class="px-2 py-1 text-xs rounded border border-slate-200 disabled:opacity-30 hover:bg-white transition-colors"
          >
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="w-3 h-3">
              <path fill-rule="evenodd" d="M8.22 5.22a.75.75 0 0 1 1.06 0l4.25 4.25a.75.75 0 0 1 0 1.06l-4.25 4.25a.75.75 0 0 1-1.06-1.06L11.94 10 8.22 6.28a.75.75 0 0 1 0-1.06Z" clip-rule="evenodd"/>
            </svg>
          </button>
          <!-- Dernière page -->
          <button
            type="button"
            onclick={() => { currentPage = totalPages - 1; }}
            disabled={currentPage >= totalPages - 1}
            aria-label="Dernière page"
            class="px-2 py-1 text-xs rounded border border-slate-200 disabled:opacity-30 hover:bg-white transition-colors"
          >
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="w-3 h-3">
              <path fill-rule="evenodd" d="M4.22 5.22a.75.75 0 0 1 1.06 0l4.25 4.25a.75.75 0 0 1 0 1.06L5.28 14.78a.75.75 0 0 1-1.06-1.06L8.94 10 5.22 6.28a.75.75 0 0 1-.04-1.06Zm6 0a.75.75 0 0 1 1.06 0l4.25 4.25a.75.75 0 0 1 0 1.06l-4.25 4.25a.75.75 0 1 1-1.06-1.06L13.94 10l-3.72-3.72a.75.75 0 0 1 0-1.06Z" clip-rule="evenodd"/>
            </svg>
          </button>
        </div>
      </div>
    {/if}

  </div>
</div>
