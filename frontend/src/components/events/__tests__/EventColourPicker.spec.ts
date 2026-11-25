// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'

import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import EventColourPicker from '@/components/events/EventColourPicker.vue'

import i18n from '@/locales/i18n'

/**
 * One of an event's colours: default, a preset, or an own colour, which shows
 * what it became in light and dark mode before and after it is picked.
 */

type Props = InstanceType<typeof EventColourPicker>['$props']

function mountPicker(props: Props) {
  return mount(EventColourPicker, {
    props,
    global: { plugins: [i18n] },
    attachTo: document.body,
  })
}

beforeEach(() => {
  i18n.global.locale.value = 'en'
})

afterEach(() => {
  document.body.innerHTML = ''
})

const picked = (w: ReturnType<typeof mountPicker>) =>
  (w.emitted('update:modelValue') ?? []).map(([value]) => value)

describe('EventColourPicker: presets', () => {
  it('names itself for a screen reader, and keeps ids apart with a prefix', () => {
    const w = mountPicker({ kind: 'secondary', modelValue: null, idPrefix: 'play' })
    const group = w.get('[role="radiogroup"]')
    expect(group.attributes('aria-labelledby')).toBe('play-colour-secondary-label')
    expect(w.get('#play-colour-secondary-label').text()).toBe('Second colour')
  })

  it('hands on a preset, and null for the default', async () => {
    const w = mountPicker({ kind: 'primary', modelValue: 'red' })
    await w.get('[data-testid="event-primary-teal"]').trigger('click')
    await w.get('[data-testid="event-primary-none"]').trigger('click')
    expect(picked(w)).toEqual(['teal', null])
  })

  it('shows the chosen main colour on the base tone that follows it', () => {
    const swatch = (primary: string | null) =>
      mountPicker({ kind: 'base', modelValue: null, primary })
        .get('[data-testid="event-base-primary"] [data-event-base]')
        .attributes('data-event-primary')
    expect(swatch('violet')).toBe('violet')
    expect(swatch('#1e6bb8')).toBe('#1e6bb8')
    expect(swatch(null)).toBeUndefined()
  })
})

describe('EventColourPicker: an own colour', () => {
  it('opens the colour field without changing anything until a colour is picked', async () => {
    const w = mountPicker({ kind: 'primary', modelValue: 'blue' })
    expect(w.find('[data-testid="event-primary-own-panel"]').exists()).toBe(false)
    await w.get('[data-testid="event-primary-own"]').trigger('click')
    expect(w.find('[data-testid="event-primary-own-panel"]').exists()).toBe(true)
    expect(w.get('[data-testid="event-primary-own"]').attributes('aria-checked')).toBe('true')
    expect(picked(w)).toEqual([])
  })

  it('previews while the colour field moves and hands on the colour when it closes', async () => {
    const w = mountPicker({ kind: 'primary', modelValue: null })
    await w.get('[data-testid="event-primary-own"]').trigger('click')
    const field = w.get('[data-testid="event-primary-own-input"]')
    // Dragging in the colour field: `input` only.
    ;(field.element as HTMLInputElement).value = '#ffd54f'
    await field.trigger('input')
    expect(picked(w)).toEqual([])
    expect(
      (w.get('[data-testid="event-primary-own-code"]').element as HTMLInputElement).value,
    ).toBe('#ffd54f')
    await field.trigger('change')
    expect(picked(w)).toEqual(['#ffd54f'])
  })

  it('takes a typed code, with or without the hash, and says when it is not one', async () => {
    const w = mountPicker({ kind: 'secondary', modelValue: null })
    await w.get('[data-testid="event-secondary-own"]').trigger('click')
    const code = w.get('[data-testid="event-secondary-own-code"]')

    await code.setValue('nope')
    await code.trigger('keydown', { key: 'Enter' })
    expect(w.get('[role="alert"]').text()).toBe('Enter a colour code like #1e6bb8.')
    expect(picked(w)).toEqual([])

    await code.setValue('2E7D32')
    await code.trigger('blur')
    expect(picked(w)).toEqual(['#2e7d32'])
    expect(w.find('[role="alert"]').exists()).toBe(false)
  })

  it('does not hand on the colour it already has', async () => {
    const w = mountPicker({ kind: 'primary', modelValue: '#1e6bb8' })
    await w.get('[data-testid="event-primary-own-code"]').trigger('blur')
    expect(picked(w)).toEqual([])
  })

  it('says what a main colour became, and how well it reads, in light and dark mode', () => {
    const w = mountPicker({ kind: 'primary', modelValue: '#ffd54f' })
    const light = w.get('[data-testid="event-primary-own-light"]')
    const dark = w.get('[data-testid="event-primary-own-dark"]')
    expect(light.attributes('data-adjusted')).toBe('true')
    expect(light.text()).toMatch(
      /^Light mode: made darker so text stays readable: [\d.]+:1 instead of 1\.\d:1$/,
    )
    expect(dark.attributes('data-adjusted')).toBe('false')
    expect(dark.text()).toMatch(/^Dark mode: as picked, contrast [\d.]+:1$/)
  })

  it('says when a colour had to get lighter, in the page language', async () => {
    i18n.global.locale.value = 'de'
    const w = mountPicker({ kind: 'secondary', modelValue: '#1e3a8a' })
    await flushPromises()
    expect(w.get('[data-testid="event-secondary-own-light"]').text()).toMatch(
      /^Hell: heller gemacht, damit Schrift lesbar bleibt: \d+,\d:1 statt \d+,\d:1$/,
    )
  })

  it('tells a base tone it only lends its hue', () => {
    const w = mountPicker({ kind: 'base', modelValue: '#2e7d32' })
    expect(w.find('[data-testid="event-base-own-report"]').exists()).toBe(false)
    expect(w.get('[data-testid="event-base-own-panel"]').text()).toContain('Only its hue is used')
  })

  it('wears the own colour on its swatch, and closes again for a preset', async () => {
    const w = mountPicker({ kind: 'secondary', modelValue: '#ffcc00' })
    expect(
      w
        .get('[data-testid="event-secondary-own"] [data-event-secondary]')
        .attributes('data-event-secondary'),
    ).toBe('#ffcc00')
    await w.setProps({ modelValue: 'green' })
    expect(w.find('[data-testid="event-secondary-own-panel"]').exists()).toBe(false)
    await w.setProps({ modelValue: '#2E7D32' })
    expect(
      (w.get('[data-testid="event-secondary-own-code"]').element as HTMLInputElement).value,
    ).toBe('#2e7d32')
  })

  it('shows a base tone in an own colour on its swatch', () => {
    const w = mountPicker({ kind: 'base', modelValue: '#2e7d32' })
    expect(
      w.get('[data-testid="event-base-own"] [data-event-base]').attributes('data-event-base'),
    ).toBe('#2e7d32')
  })
})
