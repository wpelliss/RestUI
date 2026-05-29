<script lang="ts">
  /**
   * FilterPanel.svelte — Panneau de filtres extracté
   *
   * Composant dédié aux filtres, utilisable indépendamment de DataTable
   * si besoin de composition future. En pratique, DataTable.svelte
   * intègre ses filtres en inline — ce fichier sert de composant alternatif
   * autonome pour les cas où les filtres sont rendus séparément du tableau
   * (ex : sidebar de filtres, drawer mobile).
   *
   * Props:
   *   columns       — colonnes filtrables [{ key, label }]
   *   activeFilters — état courant des filtres actifs (lecture)
   *   onApply       — callback(filters: Record<string, string>) → déclenche fetch
   *   onClear       — callback() → réinitialise tous les filtres
   *   loading       — désactive les boutons pendant le chargement
   */

  interface FilterColumn {
    key: string;
    label: string;
  }

  interface Props {
    columns:       FilterColumn[];
    activeFilters: Record<string, string>;
    onApply:       (filters: Record<string, string>) => void;
    onClear:       () => void;
    loading?:      boolean;
  }

  let {
    columns,
    activeFilters,
    onApply,
    onClear,
    loading = false,
  }: Props = $props();

  // Copie locale pour les inputs (non encore soumis)
  let pending = $state<Record<string, string>>({ ...activeFilters });

  // Sync si activeFilters change depuis le parent (ex : clear depuis DataTable)
  $effect(() => {
    pending = { ...activeFilters };
  });

  let filterCount = $derived(Object.values(activeFilters).filter(Boolean).length);

  function submit() {
    onApply({ ...pending });
  }

  function handleKeydown(e: KeyboardEvent) {
    if (e.key === 'Enter') submit();
  }

  function clearOne(key: string) {
    pending = { ...pending, [key]: '' };
    const next = { ...activeFilters };
    delete next[key];
    onApply(next);
  }

  function clearAll() {
    pending = {};
    onClear();
  }
</script>

<div class="bg-white rounded-xl border border-slate-200 shadow-sm p-5">

  <!-- Barre d'inputs filtres -->
  <div class="flex flex-wrap gap-3 items-end">
    {#each columns as col}
      <div class="flex flex-col gap-1 min-w-[140px]">
        <label
          for="fp-filter-{col.key}"
          class="text-xs font-semibold text-slate-500 uppercase tracking-wider"
        >
          {col.label}
        </label>
        <div class="relative">
          <input
            id="fp-filter-{col.key}"
            type="text"
            value={pending[col.key] ?? ''}
            oninput={(e) => {
              const val = (e.target as HTMLInputElement).value;
              pending = { ...pending, [col.key]: val };
            }}
            onkeydown={handleKeydown}
            placeholder="Filtrer…"
            class="
              w-full px-3 py-2 pr-7 text-sm rounded-lg border border-slate-200
              focus:outline-none focus:ring-2 focus:ring-blue-500/30 focus:border-blue-500
              placeholder-slate-300 text-slate-700 transition-colors duration-150
            "
          />
          {#if pending[col.key]}
            <button
              type="button"
              onclick={() => clearOne(col.key)}
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
      onclick={submit}
      disabled={loading}
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
        onclick={clearAll}
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
    <div class="flex flex-wrap gap-2 mt-3" aria-label="Filtres actifs" aria-live="polite">
      {#each Object.entries(activeFilters).filter(([, v]) => v) as [key, val]}
        <span class="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-blue-50 text-blue-700 text-xs font-medium">
          <span class="text-blue-500 font-semibold">{key}</span>
          <span>:</span>
          <span>{val}</span>
          <button
            type="button"
            onclick={() => clearOne(key)}
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
