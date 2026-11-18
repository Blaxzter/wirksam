// @vitest-environment jsdom
import { mount } from '@vue/test-utils'

import { beforeEach, describe, expect, it, vi } from 'vitest'

import PublicListPreview from '@/components/guest/PublicListPreview.vue'

import type { PublicSharedList } from '@/client/types.gen'
import i18n from '@/locales/i18n'

/**
 * The organisers' picture of a list's public page: the same content, nothing
 * to press, and no heading that would join the management page's outline.
 */

vi.mock('@/stores/auth', () => ({ useAuthStore: () => ({ profile: null }) }))

function publicList(overrides: Partial<PublicSharedList> = {}): PublicSharedList {
  return {
    code: 'abc123',
    title: 'Helpers wanted',
    intro: 'Come along',
    status: 'live',
    event: {
      name: 'Summer fair',
      start_date: '2026-11-20',
      end_date: '2026-11-20',
      timezone: 'Europe/Berlin',
    },
    ask_email: 'required',
    ask_phone: 'off',
    show_names: 'none',
    max_per_person: null,
    retention_days: 30,
    days: [
      {
        date: '2026-11-20',
        shifts: [
          {
            id: 'shift-1',
            task_id: 'task-1',
            task_name: 'Bar',
            start_time: '10:00:00',
            end_time: '12:00:00',
            capacity: 2,
            free: 1,
            full: false,
          },
        ],
      },
    ],
    ...overrides,
  }
}

const mountPreview = (list: PublicSharedList) =>
  mount(PublicListPreview, { props: { list }, global: { plugins: [i18n] } })

beforeEach(() => {
  i18n.global.locale.value = 'en'
})

describe('PublicListPreview', () => {
  it('shows the list as helpers see it, with nothing to press', () => {
    const wrapper = mountPreview(publicList())
    expect(wrapper.text()).toContain('Helpers wanted')
    expect(wrapper.text()).toContain('1 free')
    expect(wrapper.text()).toContain(`/l/abc123`)
    expect(wrapper.find('[data-testid="public-list-preview-hint"]').exists()).toBe(true)
    expect(wrapper.find('button').exists()).toBe(false)
  })

  it('adds no heading to the page it sits in', () => {
    const wrapper = mountPreview(publicList())
    expect(wrapper.findAll('h1, h2, h3, h4')).toHaveLength(0)
    expect(wrapper.find('[data-testid="page-heading"]').exists()).toBe(false)
  })

  it.each([
    ['paused', 'public-list-preview-paused'],
    ['closed', 'public-list-preview-closed'],
  ] as const)('shows what helpers see of a %s list', (status, testid) => {
    const wrapper = mountPreview(publicList({ status, days: [] }))
    expect(wrapper.find(`[data-testid="${testid}"]`).exists()).toBe(true)
    expect(wrapper.find('[data-testid="public-shift-list"]').exists()).toBe(false)
  })

  it('says when no shift is left', () => {
    const wrapper = mountPreview(publicList({ days: [] }))
    expect(wrapper.text()).toContain('There are no shifts left on this list.')
  })
})
