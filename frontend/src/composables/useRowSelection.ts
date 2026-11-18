import {
  type ComputedRef,
  type MaybeRefOrGetter,
  type WatchSource,
  computed,
  shallowRef,
  toValue,
  watch,
} from 'vue'

export interface RowSelectionOptions<T> {
  /** The rows on screen: the current page of a server-paginated table. */
  rows: MaybeRefOrGetter<readonly T[]>
  rowId: (row: T) => string
  /** A row that cannot be acted on (ended, or not the viewer's) has a disabled checkbox. */
  isSelectable?: (row: T) => boolean
  /**
   * Clear the selection whenever this changes: `useTableQuery().key`, which
   * changes with the page, sort, search and filter. A selection the viewer can
   * no longer see is one they could act on by mistake.
   */
  clearOn?: WatchSource<unknown>
}

export interface RowSelection<T> {
  selected: ComputedRef<ReadonlySet<string>>
  /** The ids in the order of `rows`, for a request body. */
  selectedIds: ComputedRef<string[]>
  selectedRows: ComputedRef<T[]>
  count: ComputedRef<number>
  /** Whether any row on screen can be selected; the header checkbox is disabled otherwise. */
  canSelect: ComputedRef<boolean>
  /** The header checkbox: all selectable rows on screen, some, or none. */
  headerState: ComputedRef<boolean | 'indeterminate'>
  isSelected: (id: string) => boolean
  /** Flip one row, or set it with `value`. A row that cannot be selected stays out. */
  toggle: (id: string, value?: boolean) => void
  /**
   * The header checkbox: select every selectable row on screen, or clear.
   * Without `value`, a full selection clears and anything less fills.
   */
  toggleAll: (value?: boolean) => void
  clear: () => void
}

/**
 * The rows ticked in a table, as an immutable set of ids.
 *
 * It holds only rows that are on screen: it clears when `clearOn` changes,
 * and a row that leaves `rows` or stops being selectable (a list that was just
 * ended) drops out. So an action on the selection never reaches a row the
 * viewer cannot see.
 */
export function useRowSelection<T>(options: RowSelectionOptions<T>): RowSelection<T> {
  const isSelectable = options.isSelectable ?? (() => true)
  const selected = shallowRef<ReadonlySet<string>>(new Set())

  const selectableIds = computed(() =>
    toValue(options.rows)
      .filter((row) => isSelectable(row))
      .map(options.rowId),
  )

  const selectedRows = computed(() =>
    toValue(options.rows).filter((row) => selected.value.has(options.rowId(row))),
  )

  const headerState = computed<boolean | 'indeterminate'>(() => {
    const ids = selectableIds.value
    const ticked = ids.filter((id) => selected.value.has(id)).length
    if (ticked === 0) return false
    return ticked === ids.length ? true : 'indeterminate'
  })

  function toggle(id: string, value?: boolean) {
    if (!selectableIds.value.includes(id)) return
    const on = value ?? !selected.value.has(id)
    if (on === selected.value.has(id)) return
    const next = new Set(selected.value)
    if (on) next.add(id)
    else next.delete(id)
    selected.value = next
  }

  function clear() {
    if (selected.value.size > 0) selected.value = new Set()
  }

  function toggleAll(value?: boolean) {
    const on = value ?? headerState.value !== true
    if (on) selected.value = new Set(selectableIds.value)
    else clear()
  }

  if (options.clearOn) watch(options.clearOn, clear)

  watch(selectableIds, (ids) => {
    const still = [...selected.value].filter((id) => ids.includes(id))
    if (still.length !== selected.value.size) selected.value = new Set(still)
  })

  return {
    selected: computed(() => selected.value),
    selectedIds: computed(() => selectedRows.value.map(options.rowId)),
    selectedRows,
    count: computed(() => selected.value.size),
    canSelect: computed(() => selectableIds.value.length > 0),
    headerState,
    isSelected: (id) => selected.value.has(id),
    toggle,
    toggleAll,
    clear,
  }
}
