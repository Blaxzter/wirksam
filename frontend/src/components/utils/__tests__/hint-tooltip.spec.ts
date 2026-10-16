// @vitest-environment jsdom
import { mount } from '@vue/test-utils'
import { defineComponent, h, nextTick, ref } from 'vue'

import { describe, expect, it } from 'vitest'

import { TooltipProvider } from '@/components/ui/tooltip'

import HintTooltip from '@/components/utils/HintTooltip.vue'

// An open tooltip measures itself; jsdom has no ResizeObserver.
globalThis.ResizeObserver ??= class {
  observe() {}
  unobserve() {}
  disconnect() {}
} as unknown as typeof ResizeObserver

const tooltip = () => document.querySelector('[data-slot="tooltip-content"]')

/**
 * HintTooltip must work with and without an app-level provider (the prerender
 * and unit tests have none), and switch off without remounting its child.
 */

function mountHint(label: string | null, withProvider: boolean) {
  const hint = () => h(HintTooltip, { label }, () => h('button', { 'aria-label': 'Delete' }, 'x'))
  const Host = defineComponent({
    render: () => (withProvider ? h(TooltipProvider, null, hint) : hint()),
  })
  return mount(Host, { attachTo: document.body })
}

describe('HintTooltip', () => {
  it('turns the child into a tooltip trigger without a provider around it', () => {
    const wrapper = mountHint('Delete all', false)
    const button = wrapper.get('button')
    expect(button.attributes('data-state')).toBe('closed')
    expect(button.attributes('title')).toBeUndefined()
    wrapper.unmount()
  })

  it('uses the surrounding provider when there is one', () => {
    const wrapper = mountHint('Delete all', true)
    expect(wrapper.get('button').attributes('data-state')).toBe('closed')
    wrapper.unmount()
  })

  it('shows nothing when the label is empty', async () => {
    const wrapper = mountHint(null, false)
    const button = wrapper.get('button')
    expect(button.attributes('aria-label')).toBe('Delete')
    button.element.focus()
    await nextTick()
    expect(tooltip()).toBeNull()
    wrapper.unmount()
  })

  it('opens on focus, and keeps the same child (and focus) when it is switched off', async () => {
    const off = ref(false)
    const label = ref<string | null>('Undo')
    const Host = defineComponent({
      render: () =>
        h(HintTooltip, { label: label.value, disabled: off.value }, () =>
          h('button', { 'aria-label': 'Undo' }, 'u'),
        ),
    })
    const wrapper = mount(Host, { attachTo: document.body })
    const button = wrapper.get('button').element as HTMLButtonElement
    button.focus()
    await nextTick()
    expect(tooltip()?.textContent).toContain('Undo')

    // E.g. undo with nothing left to undo: the hint goes, the button stays.
    off.value = true
    await nextTick()
    expect(wrapper.get('button').element).toBe(button)
    expect(document.activeElement).toBe(button)
    expect(tooltip()).toBeNull()

    off.value = false
    label.value = null
    await nextTick()
    expect(wrapper.get('button').element).toBe(button)
    expect(document.activeElement).toBe(button)
    wrapper.unmount()
  })
})
