import { type ComputedRef, type WritableComputedRef, computed, shallowRef, watch } from 'vue'

import { type LocationQuery, type LocationQueryRaw, useRoute, useRouter } from 'vue-router'

export type SortDir = 'asc' | 'desc'

/** The longest search the list endpoints accept (`q`, `max_length=100`). */
export const MAX_SEARCH_LENGTH = 100

export interface TableQueryOptions<S extends string, F extends string> {
  /**
   * Put in front of this table's query keys (`signups` → `signups_page`), so
   * two tables on one page keep apart. Without one the keys are `page`,
   * `sort`, `dir`, `q` and `filter`.
   */
  prefix?: string
  /** The columns the server can sort by. */
  sortKeys: readonly S[]
  defaultSort: S
  /**
   * The direction each key starts in when it is chosen, which is also the
   * server's default for it; `asc` unless listed.
   */
  sortDirs?: Partial<Record<S, SortDir>>
  /** The filter chips' values. Leave out for a table without chips. */
  filters?: readonly F[]
  /** Required with `filters`: the chip that is on when the URL names none. */
  defaultFilter?: F
  /** Rows per page; 20 unless given. */
  pageSize?: number
}

/** What the list endpoints take, ready to pass as `query`. */
export interface TableParams<S extends string, F extends string> {
  status_filter?: F
  q?: string
  sort_by: S
  sort_dir: SortDir
  skip: number
  limit: number
}

interface TableState<S extends string, F extends string> {
  page: number
  sort: S
  dir: SortDir
  q: string
  filter: F | undefined
}

export interface TableQuery<S extends string, F extends string> {
  /** 1-based. Setting it keeps everything else. */
  page: WritableComputedRef<number>
  sort: ComputedRef<S>
  dir: ComputedRef<SortDir>
  /** Trimmed. Setting it goes back to page 1. */
  q: WritableComputedRef<string>
  /** Setting it goes back to page 1. `undefined` for a table without filters. */
  filter: WritableComputedRef<F | undefined>
  /**
   * Sort by `key`. Without `dir`, the same key again flips the direction and
   * another key starts in its own default. Goes back to page 1.
   */
  setSort: (key: S, dir?: SortDir) => void
  /** The request for the current state. */
  params: ComputedRef<TableParams<S, F>>
  /**
   * Changes whenever the page, sort, search or filter does, and only then;
   * the thing to hand `useRowSelection` as `clearOn`.
   */
  key: ComputedRef<string>
  pageSize: number
  /**
   * After a load: when `total` rows no longer reach the current page (the
   * last rows were just ended or removed), step back to the last page that
   * has any.
   */
  clampTo: (total: number) => void
  /** Back to the defaults, which takes this table's keys off the URL. */
  reset: () => void
}

const DIRS: readonly SortDir[] = ['asc', 'desc']

function single(value: LocationQuery[string] | undefined): string | undefined {
  const first = Array.isArray(value) ? value[0] : value
  return typeof first === 'string' ? first : undefined
}

function oneOf<T extends string>(value: string | undefined, allowed: readonly T[]): T | undefined {
  return allowed.find((item) => item === value)
}

/**
 * A server-paginated table's page, sort, search and filter, kept in the URL
 * query (with `router.replace`, so they survive a reload and a shared link but
 * do not fill the history), and turned into the list endpoints' params.
 *
 * A change of filter, search or sort goes back to page 1. Values the URL
 * carries that the table does not know fall back to the defaults, and defaults
 * are left out of the URL. Query keys of anything else on the page are kept.
 *
 * ```ts
 * const table = useTableQuery<ListSort, ListFilter>({
 *   sortKeys: ['status', 'title', 'created_at'],
 *   defaultSort: 'status',
 *   sortDirs: { created_at: 'desc' },
 *   filters: ['active', 'todo', 'ended'],
 *   defaultFilter: 'active',
 * })
 * watch(table.params, (query) => load(query), { immediate: true })
 * ```
 */
export function useTableQuery<S extends string, F extends string = never>(
  options: TableQueryOptions<S, F>,
): TableQuery<S, F> {
  const route = useRoute()
  const router = useRouter()
  const pageSize = options.pageSize ?? 20
  const keyOf = (name: string) => (options.prefix ? `${options.prefix}_${name}` : name)
  const keys = {
    page: keyOf('page'),
    sort: keyOf('sort'),
    dir: keyOf('dir'),
    q: keyOf('q'),
    filter: keyOf('filter'),
  }
  // The page this table belongs to. Once the router has moved on, the query
  // belongs to another page and is neither read nor written.
  const ownRoute = route.name

  const defaultDir = (sort: S): SortDir => options.sortDirs?.[sort] ?? 'asc'

  function defaults(): TableState<S, F> {
    return {
      page: 1,
      sort: options.defaultSort,
      dir: defaultDir(options.defaultSort),
      q: '',
      filter: options.filters ? options.defaultFilter : undefined,
    }
  }

  function read(query: LocationQuery): TableState<S, F> {
    const sort = oneOf(single(query[keys.sort]), options.sortKeys) ?? options.defaultSort
    const page = Number(single(query[keys.page]))
    return {
      page: Number.isInteger(page) && page > 1 ? page : 1,
      sort,
      dir: oneOf(single(query[keys.dir]), DIRS) ?? defaultDir(sort),
      q: (single(query[keys.q]) ?? '').trim().slice(0, MAX_SEARCH_LENGTH),
      filter: options.filters
        ? (oneOf(single(query[keys.filter]), options.filters) ?? options.defaultFilter)
        : undefined,
    }
  }

  /** This table's keys as the URL should carry them; a default is left out. */
  function written(state: TableState<S, F>): Record<string, string | undefined> {
    return {
      [keys.page]: state.page > 1 ? String(state.page) : undefined,
      [keys.sort]: state.sort !== options.defaultSort ? state.sort : undefined,
      [keys.dir]: state.dir !== defaultDir(state.sort) ? state.dir : undefined,
      [keys.q]: state.q || undefined,
      [keys.filter]:
        state.filter !== undefined && state.filter !== options.defaultFilter
          ? state.filter
          : undefined,
    }
  }

  const fingerprint = (state: TableState<S, F>) => JSON.stringify(written(state))

  // Replaced as a whole on every change, never mutated.
  const state = shallowRef<TableState<S, F>>(read(route.query))

  // Back and forward, or a link to the same page with another query (the
  // "show the tasks to do" button), change the URL underneath the table.
  watch(
    () => route.query,
    (query) => {
      if (route.name !== ownRoute) return
      const next = read(query)
      if (fingerprint(next) !== fingerprint(state.value)) state.value = next
    },
  )

  // One `replace` for several changes in the same tick.
  watch(
    () => state.value,
    (next) => {
      if (route.name !== ownRoute) return
      const wanted = written(next)
      const current = route.query
      if (Object.entries(wanted).every(([key, value]) => single(current[key]) === value)) return
      const query: LocationQueryRaw = { ...current }
      for (const [key, value] of Object.entries(wanted)) {
        if (value === undefined) delete query[key]
        else query[key] = value
      }
      void router.replace({ query, hash: route.hash })
    },
  )

  function commit(patch: Partial<TableState<S, F>>) {
    state.value = { ...state.value, ...patch }
  }

  const page = computed({
    get: () => state.value.page,
    set: (value: number) => {
      const next = Math.max(1, Math.floor(value))
      if (next !== state.value.page) commit({ page: next })
    },
  })

  const q = computed({
    get: () => state.value.q,
    set: (value: string) => {
      const next = value.trim().slice(0, MAX_SEARCH_LENGTH)
      if (next !== state.value.q) commit({ q: next, page: 1 })
    },
  })

  const filter = computed({
    get: () => state.value.filter,
    set: (value: F | undefined) => {
      if (!options.filters || value === undefined || !options.filters.includes(value)) return
      if (value !== state.value.filter) commit({ filter: value, page: 1 })
    },
  })

  function setSort(key: S, dir?: SortDir) {
    const current = state.value
    const nextDir =
      dir ?? (key === current.sort ? (current.dir === 'asc' ? 'desc' : 'asc') : defaultDir(key))
    if (key === current.sort && nextDir === current.dir) return
    commit({ sort: key, dir: nextDir, page: 1 })
  }

  function clampTo(total: number) {
    const last = Math.max(1, Math.ceil(total / pageSize))
    if (state.value.page > last) commit({ page: last })
  }

  function reset() {
    if (fingerprint(state.value) !== fingerprint(defaults())) state.value = defaults()
  }

  const params = computed<TableParams<S, F>>(() => {
    const { page, sort, dir, q, filter } = state.value
    return {
      ...(filter !== undefined ? { status_filter: filter } : {}),
      ...(q ? { q } : {}),
      sort_by: sort,
      sort_dir: dir,
      skip: (page - 1) * pageSize,
      limit: pageSize,
    }
  })

  return {
    page,
    sort: computed(() => state.value.sort),
    dir: computed(() => state.value.dir),
    q,
    filter,
    setSort,
    params,
    key: computed(() => fingerprint(state.value)),
    pageSize,
    clampTo,
    reset,
  }
}
