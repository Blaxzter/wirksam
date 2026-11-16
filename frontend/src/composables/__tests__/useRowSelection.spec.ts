import { nextTick, ref } from 'vue'

import { describe, expect, it } from 'vitest'

import { useRowSelection } from '@/composables/useRowSelection'

interface Row {
  id: string
  ended?: boolean
}

function setup(initial: Row[]) {
  const rows = ref<Row[]>(initial)
  const tableKey = ref('page=1')
  const selection = useRowSelection({
    rows,
    rowId: (row) => row.id,
    isSelectable: (row) => !row.ended,
    clearOn: tableKey,
  })
  return { rows, tableKey, selection }
}

const PAGE: Row[] = [{ id: 'a' }, { id: 'b' }, { id: 'c', ended: true }]

describe('useRowSelection', () => {
  it('starts empty', () => {
    const { selection } = setup(PAGE)
    expect(selection.count.value).toBe(0)
    expect(selection.headerState.value).toBe(false)
    expect(selection.canSelect.value).toBe(true)
  })

  it('toggles a row, or sets it', () => {
    const { selection } = setup(PAGE)
    selection.toggle('a')
    expect(selection.isSelected('a')).toBe(true)
    selection.toggle('a', true)
    expect(selection.count.value).toBe(1)
    selection.toggle('a')
    expect(selection.isSelected('a')).toBe(false)
    selection.toggle('b', false)
    expect(selection.count.value).toBe(0)
  })

  it('keeps a row that cannot be selected out', () => {
    const { selection } = setup(PAGE)
    selection.toggle('c')
    selection.toggle('gone')
    expect(selection.count.value).toBe(0)
  })

  it('replaces the set on every change instead of mutating it', () => {
    const { selection } = setup(PAGE)
    const before = selection.selected.value
    selection.toggle('a')
    expect(selection.selected.value).not.toBe(before)
    expect(before.size).toBe(0)
  })

  it('shows some, all or none on the header checkbox, counting selectable rows only', () => {
    const { selection } = setup(PAGE)
    selection.toggle('a')
    expect(selection.headerState.value).toBe('indeterminate')
    selection.toggle('b')
    expect(selection.headerState.value).toBe(true)
  })

  it('fills from the header, and clears once everything is ticked', () => {
    const { selection } = setup(PAGE)
    selection.toggle('a')
    selection.toggleAll()
    expect(selection.selectedIds.value).toEqual(['a', 'b'])
    selection.toggleAll()
    expect(selection.count.value).toBe(0)
    selection.toggleAll(true)
    expect(selection.count.value).toBe(2)
    selection.toggleAll(false)
    expect(selection.count.value).toBe(0)
  })

  it('hands back the selected rows in the order of the table', () => {
    const { selection } = setup(PAGE)
    selection.toggle('b')
    selection.toggle('a')
    expect(selection.selectedRows.value.map((row) => row.id)).toEqual(['a', 'b'])
    expect(selection.selectedIds.value).toEqual(['a', 'b'])
  })

  it('clears itself when the page, sort, search or filter changes', async () => {
    const { selection, tableKey } = setup(PAGE)
    selection.toggleAll(true)
    tableKey.value = 'page=2'
    await nextTick()
    expect(selection.count.value).toBe(0)
  })

  it('drops rows that left the table or can no longer be selected', async () => {
    const { selection, rows } = setup(PAGE)
    selection.toggleAll(true)
    rows.value = [{ id: 'a', ended: true }, { id: 'c' }]
    await nextTick()
    expect(selection.count.value).toBe(0)
    selection.toggle('c')
    rows.value = [{ id: 'c' }, { id: 'd' }]
    await nextTick()
    expect(selection.selectedIds.value).toEqual(['c'])
  })

  it('cannot select anything on a page of ended rows', () => {
    const { selection } = setup([{ id: 'x', ended: true }])
    expect(selection.canSelect.value).toBe(false)
    selection.toggleAll()
    expect(selection.headerState.value).toBe(false)
  })

  it('treats every row as selectable unless told otherwise, and needs no clearOn', () => {
    const selection = useRowSelection({ rows: () => PAGE, rowId: (row) => row.id })
    selection.toggleAll()
    expect(selection.count.value).toBe(3)
    selection.clear()
    selection.clear()
    expect(selection.count.value).toBe(0)
  })
})
