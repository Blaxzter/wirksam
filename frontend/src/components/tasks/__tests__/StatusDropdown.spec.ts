// @vitest-environment jsdom
import { mount } from '@vue/test-utils'

import { beforeEach, describe, expect, it } from 'vitest'

import StatusDropdown from '@/components/tasks/StatusDropdown.vue'

import i18n from '@/locales/i18n'

/**
 * The status next to a title. As a pill (the task page) it is tinted by
 * status, and while it can be changed its button says so to a screen reader.
 */

function mountStatus(props: Record<string, unknown>) {
  return mount(StatusDropdown, {
    props: { i18nPrefix: 'duties.tasks.statuses', ...props },
    global: { plugins: [i18n] },
  })
}

beforeEach(() => {
  i18n.global.locale.value = 'en'
})

describe('StatusDropdown as a pill', () => {
  it('tints a published task green and a draft amber', () => {
    const published = mountStatus({ pill: true, status: 'published' })
    expect(published.text()).toBe('Published')
    expect(published.find('span > span').classes()).toContain('text-primary')

    const draft = mountStatus({ pill: true, status: 'draft' })
    expect(draft.text()).toBe('Draft')
    expect(draft.find('span > span').classes()).toContain('text-warning')

    const archived = mountStatus({ pill: true, status: 'archived' })
    expect(archived.find('span > span').classes()).toContain('text-muted-foreground')
  })

  it('is a button that names the status and the change when it can be changed', () => {
    const w = mountStatus({ pill: true, status: 'draft', editable: true })
    expect(w.find('button').attributes('aria-label')).toBe('Status: Draft. Change')
  })

  it('stays the plain badge without the pill', () => {
    const w = mountStatus({ status: 'published' })
    expect(w.find('[data-slot="badge"]').exists()).toBe(true)
  })
})
