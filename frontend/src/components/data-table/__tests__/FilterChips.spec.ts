// @vitest-environment jsdom
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'

import { describe, expect, it, vi } from 'vitest'

import FilterChips, { type FilterChip } from '@/components/data-table/FilterChips.vue'

/**
 * The filter chips above a table: a named group of toggle buttons, exactly
 * one of them pressed, and on a phone a row that scrolls sideways and keeps
 * the pressed chip in view.
 */

type Filter = 'active' | 'todo' | 'ended'

const CHIPS: FilterChip<Filter>[] = [
  { value: 'active', label: 'Active', count: 4 },
  { value: 'todo', label: 'To do', count: 2, variant: 'warning' },
  { value: 'ended', label: 'Ended' },
]

function mountChips(modelValue: Filter = 'active') {
  return mount(FilterChips, { props: { chips: CHIPS, label: 'Show lists', modelValue } })
}

const chip = (w: ReturnType<typeof mountChips>, value: Filter) =>
  w.find(`[data-testid="filter-chip-${value}"]`)

describe('FilterChips', () => {
  it('is a named group of real buttons', () => {
    const w = mountChips()
    expect(w.attributes('role')).toBe('group')
    expect(w.attributes('aria-label')).toBe('Show lists')
    expect(w.findAll('button')).toHaveLength(3)
    expect(chip(w, 'active').attributes('type')).toBe('button')
  })

  it('presses the chip that is on, and only that one', () => {
    const w = mountChips('todo')
    expect(chip(w, 'todo').attributes('aria-pressed')).toBe('true')
    expect(chip(w, 'active').attributes('aria-pressed')).toBe('false')
    expect(chip(w, 'ended').attributes('aria-pressed')).toBe('false')
  })

  it('shows a count only where there is one', () => {
    const w = mountChips()
    expect(chip(w, 'active').text()).toBe('Active 4')
    expect(chip(w, 'ended').text()).toBe('Ended')
  })

  it('marks the chip with things to do', () => {
    const w = mountChips()
    expect(chip(w, 'todo').classes().join(' ')).toMatch(/amber/)
    expect(chip(w, 'ended').classes().join(' ')).not.toMatch(/amber/)
  })

  it('turns another chip on when clicked, and scrolls it into view', async () => {
    const scrollIntoView = vi.fn()
    Element.prototype.scrollIntoView = scrollIntoView
    const w = mountChips()
    await chip(w, 'ended').trigger('click')
    expect(w.emitted('update:modelValue')).toEqual([['ended']])
    await w.setProps({ modelValue: 'ended' })
    await nextTick()
    expect(chip(w, 'ended').attributes('aria-pressed')).toBe('true')
    expect(scrollIntoView).toHaveBeenCalledWith({ block: 'nearest', inline: 'nearest' })
  })
})
