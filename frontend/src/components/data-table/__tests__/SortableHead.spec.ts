// @vitest-environment jsdom
import { mount } from '@vue/test-utils'

import { describe, expect, it } from 'vitest'

import SortableHead from '@/components/data-table/SortableHead.vue'

/**
 * A sortable column header: the header cell says how the table is sorted
 * (`aria-sort`, which a screen reader announces), and its button only reports
 * which column was asked for; the direction is the caller's to work out.
 */

type Key = 'title' | 'free'

function mountHead(props: {
  activeKey: Key
  dir: 'asc' | 'desc'
  defaultDir?: 'asc' | 'desc'
  align?: 'start' | 'end'
}) {
  return mount(SortableHead, { props: { label: 'Places', sortKey: 'free', ...props } })
}

describe('SortableHead', () => {
  it('says nothing about the order of a column the table is not sorted by', () => {
    const w = mountHead({ activeKey: 'title', dir: 'asc' })
    expect(w.element.tagName).toBe('TH')
    expect(w.attributes('aria-sort')).toBe('none')
  })

  it('says which way its own column is sorted', async () => {
    const w = mountHead({ activeKey: 'free', dir: 'asc' })
    expect(w.attributes('aria-sort')).toBe('ascending')
    await w.setProps({ dir: 'desc' })
    expect(w.attributes('aria-sort')).toBe('descending')
  })

  it('is a real button named by the column alone', () => {
    const w = mountHead({ activeKey: 'free', dir: 'desc' })
    const button = w.find('button')
    expect(button.attributes('type')).toBe('button')
    expect(button.attributes('data-testid')).toBe('sort-free')
    expect(button.text()).toBe('Places')
    expect(w.find('svg').element.closest('[aria-hidden="true"]')).not.toBeNull()
  })

  it('reports its column when clicked, whatever the current order', async () => {
    const w = mountHead({ activeKey: 'title', dir: 'asc', defaultDir: 'desc' })
    await w.find('button').trigger('click')
    expect(w.emitted('sort')).toEqual([['free']])
  })

  it('lines numbers up on the right', () => {
    const w = mountHead({ activeKey: 'title', dir: 'asc', align: 'end' })
    expect(w.classes()).toContain('text-right')
    expect(w.find('button').classes()).toContain('flex-row-reverse')
  })
})
