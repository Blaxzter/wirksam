// @vitest-environment jsdom
import { mount } from '@vue/test-utils'

import { beforeEach, describe, expect, it, vi } from 'vitest'

import SharedListIssueStrip from '@/components/shared-lists/SharedListIssueStrip.vue'

import type { SharedListIssue } from '@/client/types.gen'
import type { EffectiveStatus } from '@/lib/shared-lists'
import i18n from '@/locales/i18n'

/**
 * What a list needs, in words and one button: places nobody can reach while
 * it is paused (resume) or expired (reopen), or a list about to close with
 * places left (extend). A person in charge who may not reopen sees the
 * reason, not a button that would be refused.
 */

vi.mock('@/stores/auth', () => ({ useAuthStore: () => ({ profile: null }) }))

function mountStrip(
  issue: SharedListIssue,
  status: EffectiveStatus,
  extra: { locked?: boolean; busy?: boolean } = {},
) {
  return mount(SharedListIssueStrip, {
    props: { issue, title: 'Kuchenbuffet', status, ...extra },
    global: { plugins: [i18n] },
  })
}

const fixButton = (w: ReturnType<typeof mountStrip>) =>
  w.get('[data-testid="shared-list-issue-fix"]')

beforeEach(() => {
  i18n.global.locale.value = 'en'
})

describe('SharedListIssueStrip', () => {
  it('asks to resume a paused list whose places nobody else offers', async () => {
    const w = mountStrip({ kind: 'stranded', free: 1, task_names: ['Kuchen'] }, 'paused')

    expect(w.text()).toContain('One free place in “Kuchen” is on no other open list.')
    expect(fixButton(w).text()).toBe('Resume')
    expect(fixButton(w).attributes('aria-label')).toBe('Resume: Kuchenbuffet')
    await fixButton(w).trigger('click')
    expect(w.emitted('fix')).toEqual([['resume']])
  })

  it('asks to reopen an expired one, naming every task', () => {
    const w = mountStrip({ kind: 'stranded', free: 4, task_names: ['Kuchen', 'Kasse'] }, 'expired')
    expect(w.text()).toContain('4 free places in “Kuchen” and “Kasse” are on no other open list.')
    expect(fixButton(w).text()).toBe('Reopen')
  })

  it('offers to extend a list about to close', async () => {
    const w = mountStrip({ kind: 'expires_soon', free: 2, task_names: [], days_left: 1 }, 'live')

    expect(w.text()).toContain('Closes tomorrow with 2 places still free.')
    await fixButton(w).trigger('click')
    expect(w.emitted('fix')).toEqual([['extend']])
  })

  it('says "today" on its last day', () => {
    i18n.global.locale.value = 'de'
    const w = mountStrip({ kind: 'expires_soon', free: 1, task_names: [], days_left: 0 }, 'live')
    expect(w.text()).toContain('Läuft heute ab, ein Platz ist noch frei.')
  })

  it('cannot be fixed while busy or by someone locked out of reopening', async () => {
    const issue: SharedListIssue = { kind: 'stranded', free: 1, task_names: ['Kuchen'] }
    // Busy keeps the button focusable: it is the one that was just pressed.
    const busy = mountStrip(issue, 'paused', { busy: true })
    expect(fixButton(busy).attributes('aria-disabled')).toBe('true')
    expect(fixButton(busy).attributes('disabled')).toBeUndefined()
    await fixButton(busy).trigger('click')
    expect(busy.emitted('fix')).toBeUndefined()
    expect(
      fixButton(mountStrip(issue, 'paused', { locked: true })).attributes('disabled'),
    ).toBeDefined()
  })
})
