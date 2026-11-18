// @vitest-environment jsdom
import { mount } from '@vue/test-utils'
import { ref } from 'vue'

import { beforeEach, describe, expect, it, vi } from 'vitest'

import ListPagination from '@/components/data-table/ListPagination.vue'

import i18n from '@/locales/i18n'

/**
 * Pages of a server-paginated list: in the app's language (the shadcn parts
 * underneath say "Previous" and "More pages" in English), the current page
 * announced, and narrower on a phone, where it measures its own width.
 */

const size = vi.hoisted(() => ({ width: 0 }))
vi.mock('@vueuse/core', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@vueuse/core')>()),
  useElementSize: () => ({ width: ref(size.width), height: ref(0) }),
}))

function mountPagination(props: { page: number; total: number; pageSize: number }) {
  return mount(ListPagination, { props, global: { plugins: [i18n] } })
}

const pageButtons = (w: ReturnType<typeof mountPagination>) =>
  w.findAll('[data-type="page"]').map((button) => button.text())

beforeEach(() => {
  i18n.global.locale.value = 'en'
  size.width = 0
})

describe('ListPagination', () => {
  it('renders nothing while everything fits on one page', () => {
    const w = mountPagination({ page: 1, total: 20, pageSize: 20 })
    expect(w.find('[data-testid="list-pagination"]').exists()).toBe(false)
    expect(w.find('nav').exists()).toBe(false)
  })

  it('names the pages in the app’s language', () => {
    i18n.global.locale.value = 'de'
    const w = mountPagination({ page: 3, total: 100, pageSize: 20 })
    expect(w.find('nav').attributes('aria-label')).toBe('Seiten')
    const current = w.find('[aria-current="page"]')
    expect(current.text()).toBe('3')
    expect(current.attributes('aria-label')).toBe('Seite 3 von 5')
    expect(w.find('[data-slot="pagination-previous"]').attributes('aria-label')).toBe('Zurück')
    expect(w.find('[data-slot="pagination-next"]').attributes('aria-label')).toBe('Weiter')
    expect(w.text()).not.toMatch(/Previous|Next|More pages/)
  })

  it('keeps to the current page and the edges on a phone', () => {
    const w = mountPagination({ page: 5, total: 200, pageSize: 20 })
    expect(pageButtons(w)).toEqual(['1', '5', '10'])
    expect(w.findAll('[data-type="ellipsis"]')).toHaveLength(2)
    expect(w.find('[data-type="ellipsis"]').text()).toBe('More pages')
    expect(w.find('[data-slot="pagination-first"]').exists()).toBe(false)
    expect(w.find('[data-slot="pagination-last"]').exists()).toBe(false)
    expect(w.find('[data-slot="pagination-previous"]').text()).toBe('')
  })

  it('adds the neighbours, words and first and last where there is room', () => {
    size.width = 800
    const w = mountPagination({ page: 5, total: 200, pageSize: 20 })
    expect(pageButtons(w)).toEqual(['1', '4', '5', '6', '10'])
    expect(w.find('[data-slot="pagination-first"]').attributes('aria-label')).toBe('First page')
    expect(w.find('[data-slot="pagination-last"]').attributes('aria-label')).toBe('Last page')
    expect(w.find('[data-slot="pagination-previous"]').text()).toBe('Previous')
    expect(w.find('[data-slot="pagination-next"]').text()).toBe('Next')
  })

  it('reports the page picked, and leaves the page itself to the parent', async () => {
    const w = mountPagination({ page: 1, total: 60, pageSize: 20 })
    await w
      .findAll('[data-type="page"]')
      .find((b) => b.text() === '3')!
      .trigger('click')
    await w.find('[data-slot="pagination-next"]').trigger('click')
    expect(w.emitted('update:page')).toEqual([[3], [2]])
    expect(w.find('[aria-current="page"]').text()).toBe('1')
  })

  it('cannot go back from the first page or on from the last', async () => {
    const first = mountPagination({ page: 1, total: 60, pageSize: 20 })
    expect(first.find('[data-slot="pagination-previous"]').attributes()).toHaveProperty('disabled')
    const last = mountPagination({ page: 3, total: 60, pageSize: 20 })
    expect(last.find('[data-slot="pagination-next"]').attributes()).toHaveProperty('disabled')
  })
})
