// @vitest-environment jsdom
import { mount } from '@vue/test-utils'

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import SearchField from '@/components/data-table/SearchField.vue'

import i18n from '@/locales/i18n'

/**
 * The search box above a table: one request per pause in typing, not one per
 * key; Enter and the clear button do not wait; and a search cleared from
 * outside empties the box.
 */

function mountField(modelValue = '') {
  return mount(SearchField, {
    props: { modelValue, label: 'Search lists', placeholder: 'Title, group, task…' },
    global: { plugins: [i18n] },
  })
}

const input = (w: ReturnType<typeof mountField>) => w.find('input')

beforeEach(() => {
  vi.useFakeTimers()
  i18n.global.locale.value = 'en'
})

afterEach(() => {
  vi.useRealTimers()
})

describe('SearchField', () => {
  it('is a labelled search box that clears with one named button', async () => {
    const w = mountField()
    expect(input(w).attributes('type')).toBe('search')
    expect(input(w).attributes('aria-label')).toBe('Search lists')
    expect(input(w).attributes('placeholder')).toBe('Title, group, task…')
    expect(input(w).attributes('maxlength')).toBe('100')
    expect(w.find('[data-testid="search-clear"]').exists()).toBe(false)
    await input(w).setValue('bar')
    expect(w.find('[data-testid="search-clear"]').attributes('aria-label')).toBe('Reset')
  })

  it('reports what was typed once the typing pauses, trimmed', async () => {
    const w = mountField()
    await input(w).setValue('b')
    await input(w).setValue(' bar ')
    vi.advanceTimersByTime(299)
    expect(w.emitted('update:modelValue')).toBeUndefined()
    vi.advanceTimersByTime(1)
    await vi.runAllTimersAsync()
    expect(w.emitted('update:modelValue')).toEqual([['bar']])
  })

  it('reports at once on Enter, and only a change', async () => {
    const w = mountField('bar')
    await input(w).setValue('bar ')
    await input(w).trigger('keydown', { key: 'Enter' })
    expect(w.emitted('update:modelValue')).toBeUndefined()
    await input(w).setValue('bühne')
    await input(w).trigger('keydown', { key: 'Enter' })
    expect(w.emitted('update:modelValue')).toEqual([['bühne']])
  })

  it('empties the box and the search with the clear button', async () => {
    const w = mountField('bar')
    await w.find('[data-testid="search-clear"]').trigger('click')
    expect(input(w).element.value).toBe('')
    expect(w.emitted('update:modelValue')).toEqual([['']])
  })

  it('takes a search set from outside', async () => {
    const w = mountField('bar')
    await w.setProps({ modelValue: '' })
    expect(input(w).element.value).toBe('')
  })
})
