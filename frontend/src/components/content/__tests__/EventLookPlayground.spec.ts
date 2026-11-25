// @vitest-environment jsdom
import { mount } from '@vue/test-utils'

import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import EventLookPlayground from '@/components/content/EventLookPlayground.vue'

import i18n from '@/locales/i18n'

/**
 * The feature page's example: the organisers' pickers and a page of the app
 * that wears what they pick, without dressing the page around it.
 */

function mountPlayground() {
  return mount(EventLookPlayground, { global: { plugins: [i18n] }, attachTo: document.body })
}

const preview = (w: ReturnType<typeof mountPlayground>) =>
  w.get('[data-testid="playground-preview"]')

beforeEach(() => {
  i18n.global.locale.value = 'en'
  document.documentElement.className = ''
})

afterEach(() => {
  document.body.innerHTML = ''
  document.documentElement.className = ''
  localStorage.clear()
})

describe('EventLookPlayground', () => {
  it('starts in a look of its own, on the example only', () => {
    const w = mountPlayground()
    const page = preview(w)
    expect(page.classes()).toContain('event-scope')
    expect(page.attributes()).toMatchObject({
      'data-event-primary': 'blue',
      'data-event-secondary': 'yellow',
      'data-event-base': 'primary',
    })
    expect(document.documentElement.dataset.eventPrimary).toBeUndefined()
    expect(page.text()).toContain('Your next shift')
  })

  it('wears a picked preset and an own colour', async () => {
    const w = mountPlayground()
    await w.get('[data-testid="event-primary-teal"]').trigger('click')
    expect(preview(w).attributes('data-event-primary')).toBe('teal')

    await w.get('[data-testid="event-secondary-own"]').trigger('click')
    const field = w.get('[data-testid="event-secondary-own-input"]')
    await field.setValue('#ffcc00')
    await field.trigger('change')
    expect(preview(w).attributes('data-event-secondary')).toBe('#ffcc00')
  })

  it('drops a base tone that follows a main colour it does not have', async () => {
    const w = mountPlayground()
    await w.get('[data-testid="event-primary-none"]').trigger('click')
    expect(preview(w).attributes('data-event-base')).toBeUndefined()
    await w.get('[data-testid="event-base-rose"]').trigger('click')
    expect(preview(w).attributes('data-event-base')).toBe('rose')
  })

  it('switches the page between light and dark', async () => {
    const w = mountPlayground()
    await w.get('[data-testid="playground-dark"]').trigger('click')
    expect(document.documentElement.classList.contains('dark')).toBe(true)
    expect(w.get('[data-testid="playground-dark"]').attributes('aria-pressed')).toBe('true')
    await w.get('[data-testid="playground-light"]').trigger('click')
    expect(document.documentElement.classList.contains('dark')).toBe(false)
  })
})
