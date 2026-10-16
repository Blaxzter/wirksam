// @vitest-environment jsdom
import { mount } from '@vue/test-utils'
import { defineComponent, h, nextTick, ref } from 'vue'

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import VenuePinHint from '@/components/venue-map/VenuePinHint.vue'

// The open tooltip measures itself; jsdom has no ResizeObserver.
globalThis.ResizeObserver ??= class {
  observe() {}
  unobserve() {}
  disconnect() {}
} as unknown as typeof ResizeObserver

/**
 * The pins' hover hint: one shared tooltip pointed at whichever pin carries
 * `data-hint` under the pointer or keyboard focus.
 */

function pointer(
  type: string,
  init: { pointerType?: string; buttons?: number; relatedTarget?: Element | null } = {},
) {
  const event = new MouseEvent(type, {
    bubbles: true,
    buttons: init.buttons ?? 0,
    relatedTarget: init.relatedTarget ?? null,
  })
  Object.defineProperty(event, 'pointerType', { value: init.pointerType ?? 'mouse' })
  return event
}

function mountMap() {
  const Host = defineComponent({
    setup() {
      const svg = ref<SVGSVGElement | null>(null)
      return () =>
        h('div', [
          h('svg', { ref: svg }, [
            h('g', { 'data-hint': 'Bar · 5/8', 'data-testid': 'pin-a', tabindex: 0 }, [
              h('circle', { r: 4, 'data-testid': 'pin-a-body' }),
            ]),
            h('g', { 'data-hint': 'Toilets', 'data-testid': 'pin-b', tabindex: 0 }),
            h('rect', { 'data-testid': 'ground' }),
          ]),
          h(VenuePinHint, { container: svg.value }),
        ])
    },
  })
  return mount(Host, { attachTo: document.body })
}

const hint = () => document.querySelector('[data-testid="map-pin-hint"]')

describe('VenuePinHint', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => vi.useRealTimers())

  it('shows the pin hint after a short hover and hides it when the pointer leaves', async () => {
    const wrapper = mountMap()
    await nextTick()
    const body = wrapper.get('[data-testid="pin-a-body"]').element
    body.dispatchEvent(pointer('pointerover'))
    await nextTick()
    expect(hint()).toBeNull()

    vi.advanceTimersByTime(300)
    await nextTick()
    expect(hint()?.textContent).toContain('Bar · 5/8')

    // Moving inside the same pin keeps it.
    body.dispatchEvent(
      pointer('pointerout', { relatedTarget: wrapper.get('[data-testid="pin-a"]').element }),
    )
    await nextTick()
    expect(hint()).not.toBeNull()

    body.dispatchEvent(
      pointer('pointerout', { relatedTarget: wrapper.get('[data-testid="ground"]').element }),
    )
    await nextTick()
    expect(hint()).toBeNull()
    wrapper.unmount()
  })

  it('moves straight to the next pin and goes away over bare ground', async () => {
    const wrapper = mountMap()
    await nextTick()
    wrapper.get('[data-testid="pin-a"]').element.dispatchEvent(pointer('pointerover'))
    vi.advanceTimersByTime(300)
    await nextTick()
    wrapper.get('[data-testid="pin-b"]').element.dispatchEvent(pointer('pointerover'))
    await nextTick()
    expect(hint()?.textContent).toContain('Toilets')

    wrapper.get('[data-testid="ground"]').element.dispatchEvent(pointer('pointerover'))
    await nextTick()
    expect(hint()).toBeNull()
    wrapper.unmount()
  })

  it('never shows on touch or while a button is held, and closes on pointer down', async () => {
    const wrapper = mountMap()
    await nextTick()
    const pin = wrapper.get('[data-testid="pin-a"]').element
    pin.dispatchEvent(pointer('pointerover', { pointerType: 'touch' }))
    pin.dispatchEvent(pointer('pointerover', { buttons: 1 }))
    vi.advanceTimersByTime(300)
    await nextTick()
    expect(hint()).toBeNull()

    pin.dispatchEvent(pointer('pointerover'))
    vi.advanceTimersByTime(300)
    await nextTick()
    expect(hint()).not.toBeNull()
    pin.dispatchEvent(pointer('pointerdown'))
    await nextTick()
    expect(hint()).toBeNull()
    wrapper.unmount()
  })

  it('shows at once for keyboard focus and hides on blur', async () => {
    const wrapper = mountMap()
    await nextTick()
    const pin = wrapper.get('[data-testid="pin-b"]').element as SVGGElement
    const focusVisible = vi.spyOn(pin, 'matches').mockImplementation(() => true)
    pin.dispatchEvent(new FocusEvent('focusin', { bubbles: true }))
    await nextTick()
    expect(hint()?.textContent).toContain('Toilets')
    expect(focusVisible).toHaveBeenCalledWith(':focus-visible')

    pin.dispatchEvent(new FocusEvent('focusout', { bubbles: true }))
    await nextTick()
    expect(hint()).toBeNull()

    // A mouse click focuses the pin too, without a hint.
    focusVisible.mockImplementation(() => false)
    pin.dispatchEvent(new FocusEvent('focusin', { bubbles: true }))
    await nextTick()
    expect(hint()).toBeNull()
    wrapper.unmount()
  })
})
