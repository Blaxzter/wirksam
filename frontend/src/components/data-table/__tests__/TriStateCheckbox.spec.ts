// @vitest-environment jsdom
import { mount } from '@vue/test-utils'

import { describe, expect, it } from 'vitest'

import TriStateCheckbox from '@/components/data-table/TriStateCheckbox.vue'

/**
 * A half-ticked box must not look ticked: it is filled and shows a dash,
 * while a ticked one shows the tick.
 */

describe('TriStateCheckbox', () => {
  it('draws a dash on a filled box when half ticked', () => {
    const box = mount(TriStateCheckbox, {
      props: { modelValue: 'indeterminate' },
      attrs: { 'aria-label': 'Select all' },
    })
    const root = box.find('[role="checkbox"]')
    expect(root.attributes('aria-checked')).toBe('mixed')
    expect(root.attributes('aria-label')).toBe('Select all')
    expect(root.classes()).toContain('data-[state=indeterminate]:bg-primary')
    expect(box.find('svg').classes()).toContain('lucide-minus')
  })

  it('draws the tick when ticked', () => {
    const box = mount(TriStateCheckbox, { props: { modelValue: true } })
    expect(box.find('[role="checkbox"]').attributes('aria-checked')).toBe('true')
    expect(box.find('svg').classes()).toContain('lucide-check')
  })

  it('reports a click as the new value', async () => {
    const box = mount(TriStateCheckbox, { props: { modelValue: false } })
    await box.find('[role="checkbox"]').trigger('click')
    expect(box.emitted('update:modelValue')).toEqual([[true]])
  })
})
