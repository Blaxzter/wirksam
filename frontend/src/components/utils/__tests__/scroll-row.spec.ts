// @vitest-environment jsdom
import { mount } from '@vue/test-utils'
import { h } from 'vue'

import { describe, expect, it } from 'vitest'

import ScrollRow from '@/components/utils/ScrollRow.vue'

// reka's ScrollArea measures itself; jsdom has no ResizeObserver.
globalThis.ResizeObserver ??= class {
  observe() {}
  unobserve() {}
  disconnect() {}
} as unknown as typeof ResizeObserver

function mountRow() {
  return mount(ScrollRow, {
    attrs: { role: 'tablist', class: 'mt-2' },
    props: { contentClass: 'gap-2' },
    slots: { default: () => [h('button', 'One'), h('button', 'Two')] },
    attachTo: document.body,
  })
}

describe('ScrollRow', () => {
  it('puts attributes on the outer box and the row layout on the content', () => {
    const wrapper = mountRow()
    expect(wrapper.attributes('role')).toBe('tablist')
    expect(wrapper.classes()).toContain('mt-2')
    const content = wrapper.get('[data-slot="scroll-row"]')
    expect(content.classes()).toEqual(expect.arrayContaining(['flex', 'gap-2']))
    expect(content.findAll('button')).toHaveLength(2)
    wrapper.unmount()
  })

  it('scrolls in a viewport that fades its edges and is no tab stop of its own', () => {
    const wrapper = mountRow()
    const viewport = wrapper.vm.scroller
    expect(viewport).toBeInstanceOf(HTMLElement)
    expect(viewport?.classList).toContain('scroll-fade-x')
    expect(viewport?.getAttribute('tabindex')).toBe('-1')
    expect(viewport?.contains(wrapper.get('[data-slot="scroll-row"]').element)).toBe(true)
    wrapper.unmount()
  })
})
