// @vitest-environment jsdom
import { mount } from '@vue/test-utils'
import { ref } from 'vue'

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { ListSort } from '@/stores/sharedLists'

import { useRowSelection } from '@/composables/useRowSelection'

import SharedListsTable from '@/components/shared-lists/SharedListsTable.vue'
import { isListSelectable } from '@/components/shared-lists/useSharedListActions'

import type { SharedListRow } from '@/client/types.gen'
import i18n from '@/locales/i18n'

import { listRow } from './fixtures'

/**
 * The lists as a table: sorting is the server's, so a header only says which
 * column was asked for; ended lists and lists the viewer only reads cannot be
 * ticked; a list with something to fix carries its strip, whose button says
 * what it does.
 */

vi.mock('@/stores/auth', () => ({ useAuthStore: () => ({ profile: { time_format: 'h24' } }) }))

const ROWS: SharedListRow[] = [
  listRow('live'),
  listRow('ended', { effective_status: 'ended', status: 'ended' }),
  listRow('viewer', { access: 'viewer' }),
  listRow('paused', {
    effective_status: 'paused',
    status: 'paused',
    issue: { kind: 'stranded', free: 3, task_names: ['Kuchen'] },
  }),
]

function mountTable(props: { sort?: ListSort; dir?: 'asc' | 'desc'; locked?: boolean } = {}) {
  const rows = ref(ROWS)
  const selection = useRowSelection({
    rows,
    rowId: (row) => row.id,
    isSelectable: isListSelectable,
  })
  const wrapper = mount(SharedListsTable, {
    props: {
      rows: rows.value,
      zone: 'Europe/Berlin',
      selection,
      sort: props.sort ?? 'status',
      dir: props.dir ?? 'asc',
      busyId: null,
      copiedId: null,
      locked: props.locked,
    },
    attachTo: document.body,
    global: { plugins: [i18n] },
  })
  return { wrapper, selection }
}

const rowOf = (w: ReturnType<typeof mountTable>['wrapper'], id: string) =>
  w.get(`[data-testid="shared-list-row-${id}"]`)

beforeEach(() => {
  i18n.global.locale.value = 'en'
})

afterEach(() => {
  document.body.innerHTML = ''
})

describe('SharedListsTable', () => {
  it('asks for a column when its header is clicked, and marks the sorted one', async () => {
    const { wrapper } = mountTable({ sort: 'signups', dir: 'desc' })

    const signups = wrapper.get('[data-testid="sort-signups"]').element.closest('th')!
    expect(signups.getAttribute('aria-sort')).toBe('descending')
    const title = wrapper.get('[data-testid="sort-title"]').element.closest('th')!
    expect(title.getAttribute('aria-sort')).toBe('none')

    await wrapper.get('[data-testid="sort-title"]').trigger('click')
    await wrapper.get('[data-testid="sort-free"]').trigger('click')
    expect(wrapper.emitted('sort')).toEqual([['title'], ['free']])
  })

  it('cannot tick an ended list, nor one the viewer only reads', () => {
    const { wrapper } = mountTable()
    const box = (id: string) =>
      rowOf(wrapper, id).get('[data-testid="shared-list-select"]').attributes('disabled')

    expect(box('live')).toBeUndefined()
    expect(box('paused')).toBeUndefined()
    expect(box('ended')).toBeDefined()
    expect(box('viewer')).toBeDefined()
  })

  it('ticks a row, and every row that can be ticked from the header', async () => {
    const { wrapper, selection } = mountTable()

    await rowOf(wrapper, 'live').get('[data-testid="shared-list-select"]').trigger('click')
    expect(selection.selectedIds.value).toEqual(['live'])

    await wrapper.get('[data-testid="shared-lists-select-all"]').trigger('click')
    expect(selection.selectedIds.value).toEqual(['live', 'paused'])
  })

  it('names each checkbox after its list', () => {
    const { wrapper } = mountTable()
    expect(
      rowOf(wrapper, 'live').get('[data-testid="shared-list-select"]').attributes('aria-label'),
    ).toBe('Select “List live”')
  })

  it('shows what a list needs under it and reports the fix', async () => {
    const { wrapper } = mountTable()

    const strip = wrapper.get('[data-testid="shared-list-issue"]')
    expect(strip.text()).toContain('3 free places in “Kuchen” are on no other open list.')
    await strip.get('[data-testid="shared-list-issue-fix"]').trigger('click')

    expect(wrapper.emitted('act')).toEqual([[ROWS[3], 'resume']])
  })

  it('offers pause for an open list and resume for a paused one', async () => {
    const { wrapper } = mountTable()

    await rowOf(wrapper, 'live').get('[data-testid="shared-list-pause"]').trigger('click')
    await rowOf(wrapper, 'paused').get('[data-testid="shared-list-resume"]').trigger('click')

    expect(wrapper.emitted('act')).toEqual([
      [ROWS[0], 'pause'],
      [ROWS[3], 'resume'],
    ])
    expect(rowOf(wrapper, 'ended').find('[data-testid="shared-list-pause"]').exists()).toBe(false)
  })

  it('lets a locked person in charge pause but not reopen', async () => {
    const { wrapper } = mountTable({ locked: true })

    expect(
      rowOf(wrapper, 'live').get('[data-testid="shared-list-pause"]').attributes('disabled'),
    ).toBeUndefined()
    // Not disabled, which would drop the focus of the pause button it replaces.
    const resume = rowOf(wrapper, 'paused').get('[data-testid="shared-list-resume"]')
    expect(resume.attributes('aria-disabled')).toBe('true')
    await resume.trigger('click')
    expect(wrapper.emitted('act')).toBeUndefined()
    expect(
      wrapper.get('[data-testid="shared-list-issue-fix"]').attributes('disabled'),
    ).toBeDefined()
  })

  it('copies the link of a list that has not ended, and opens the details', async () => {
    const { wrapper } = mountTable()

    await rowOf(wrapper, 'live').get('[data-testid="shared-list-copy"]').trigger('click')
    await rowOf(wrapper, 'live').get('[data-testid="shared-list-title"]').trigger('click')
    await rowOf(wrapper, 'live').get('[data-testid="shared-list-details"]').trigger('click')

    expect(wrapper.emitted('copy')).toEqual([[ROWS[0]]])
    expect(wrapper.emitted('open')).toEqual([[ROWS[0]], [ROWS[0]]])
    expect(
      rowOf(wrapper, 'ended').get('[data-testid="shared-list-copy"]').attributes('disabled'),
    ).toBeDefined()
  })
})
