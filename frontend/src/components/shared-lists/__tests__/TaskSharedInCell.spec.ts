// @vitest-environment jsdom
import { mount } from '@vue/test-utils'

import { beforeEach, describe, expect, it } from 'vitest'

import TaskSharedInCell from '@/components/shared-lists/TaskSharedInCell.vue'

import type { SharedListTaskRow } from '@/client/types.gen'
import i18n from '@/locales/i18n'

import { taskRow } from './fixtures'

/**
 * Where a task's places are shared: a chip per list that opens it, the ended
 * ones counted, and the free places no open list offers, with "Share" when
 * they are on no list at all and the viewer may share the task.
 */

function mountCell(row: SharedListTaskRow) {
  return mount(TaskSharedInCell, { props: { row }, global: { plugins: [i18n] } })
}

beforeEach(() => {
  i18n.global.locale.value = 'en'
})

describe('TaskSharedInCell', () => {
  it('says a team task is shared through its team only', () => {
    const w = mountCell(taskRow('t', { team: { id: 'team', name: 'Sanitäter' }, stranded_free: 3 }))
    expect(w.text()).toBe('Team only')
    expect(w.find('[data-testid="task-stranded"]').exists()).toBe(false)
  })

  it('shows each list as a chip that opens it, named with its status', async () => {
    const w = mountCell(
      taskRow('t', {
        lists: [
          { id: 'l1', title: 'Eltern', effective_status: 'live' },
          { id: 'l2', title: 'Aushang', effective_status: 'paused' },
        ],
        ended_list_count: 2,
      }),
    )

    const chips = w.findAll('[data-testid="task-list-chip"]')
    expect(chips.map((chip) => chip.attributes('aria-label'))).toEqual([
      '“Eltern”, Open',
      '“Aushang”, Paused',
    ])
    expect(w.text()).toContain('· 2 ended')
    await chips[1].trigger('click')
    expect(w.emitted('open')).toEqual([['l2']])
  })

  it('says a task is on no list when nothing waits for one', () => {
    expect(mountCell(taskRow('t')).text()).toBe('On no list')
  })

  it('counts places on no open list and offers to share those on no list at all', async () => {
    const w = mountCell(taskRow('t', { stranded_free: 3, unlisted_free: 2 }))

    expect(w.get('[data-testid="task-stranded"]').text()).toBe('3 free places on no open list')
    expect(w.text()).not.toContain('On no list')
    await w.get('[data-testid="task-share"]').trigger('click')
    expect(w.emitted('share')).toEqual([['t']])
  })

  it('does not offer to share what a paused list already holds, or what the viewer may not share', () => {
    expect(
      mountCell(taskRow('t', { stranded_free: 1, unlisted_free: 0 }))
        .find('[data-testid="task-share"]')
        .exists(),
    ).toBe(false)
    expect(
      mountCell(taskRow('t', { stranded_free: 1, unlisted_free: 1, can_share: false }))
        .find('[data-testid="task-share"]')
        .exists(),
    ).toBe(false)
  })
})
