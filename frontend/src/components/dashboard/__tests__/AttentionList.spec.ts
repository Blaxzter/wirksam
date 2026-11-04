// @vitest-environment jsdom
import { RouterLinkStub, mount } from '@vue/test-utils'

import { beforeEach, describe, expect, it } from 'vitest'

import { teamsPageLocation } from '@/composables/useTeams'

import AttentionList from '@/components/dashboard/AttentionList.vue'

import { type AttentionItem, attentionItems } from '@/lib/dashboard'
import i18n from '@/locales/i18n'

/**
 * The organiser's list: nothing at all when nothing needs doing, otherwise one
 * link per count, most urgent first, with the count tinted by urgency.
 */

function mountList(items: AttentionItem[], eventId: string | null = 'e1') {
  return mount(AttentionList, {
    props: { items, eventId },
    global: { plugins: [i18n], stubs: { RouterLink: RouterLinkStub } },
  })
}

beforeEach(() => {
  i18n.global.locale.value = 'en'
})

describe('AttentionList', () => {
  it('renders nothing when there is nothing to report', () => {
    const w = mountList([])
    expect(w.find('[data-testid="dashboard-attention"]').exists()).toBe(false)
  })

  it('lists every count as a link, in order, with the count first', () => {
    const w = mountList(
      attentionItems({
        empty_shifts_soon: 2,
        short_shifts_soon: 1,
        pending_join_requests: 3,
        pending_team_requests: 1,
        draft_tasks: 140,
      }),
    )
    const rows = w.findAll('[data-testid^="attention-"]:not([data-testid="attention-count"])')
    expect(rows.map((r) => r.attributes('data-testid'))).toEqual([
      'attention-empty',
      'attention-short',
      'attention-requests',
      'attention-team-requests',
      'attention-drafts',
    ])
    // Whitespace collapsed, as a screen reader hears it.
    const said = rows.map((r) => r.text().replace(/\s+/g, ' '))
    expect(said).toEqual([
      '2 Shifts in the next 7 days have nobody on them',
      '1 Shift in the next 7 days is short of people',
      '3 People are waiting to join',
      '1 Team request is waiting for you',
      '99+ Jobs are still drafts',
    ])
  })

  it('tints the count by urgency', () => {
    const w = mountList(
      attentionItems({ empty_shifts_soon: 1, short_shifts_soon: 1, draft_tasks: 1 }),
    )
    const squares = w.findAll('[data-testid="attention-count"]')
    expect(squares[0].classes()).toContain('bg-destructive/10')
    expect(squares[1].classes()).toContain('bg-warning/10')
    expect(squares[2].classes()).toContain('bg-muted')
  })

  it('links each line to where it is dealt with', () => {
    const w = mountList(
      attentionItems({
        empty_shifts_soon: 1,
        short_shifts_soon: 1,
        pending_join_requests: 1,
        pending_team_requests: 1,
        draft_tasks: 1,
      }),
      'e7',
    )
    const to = (id: string) =>
      w
        .findAllComponents(RouterLinkStub)
        .find((c) => c.attributes('data-testid') === id)!
        .props('to')
    expect(to('attention-empty')).toEqual({ name: 'tasks', query: { hide_full: 'true' } })
    expect(to('attention-short')).toEqual({ name: 'tasks', query: { hide_full: 'true' } })
    expect(to('attention-requests')).toEqual({ name: 'my-events', query: { tab: 'requests' } })
    expect(to('attention-team-requests')).toEqual(teamsPageLocation('e7'))
    expect(to('attention-drafts')).toEqual({ name: 'tasks' })
  })
})
