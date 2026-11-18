// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent } from 'vue'

import { describe, expect, it, vi } from 'vitest'
import { type Router, createMemoryHistory, createRouter } from 'vue-router'

import {
  MAX_SEARCH_LENGTH,
  type TableQuery,
  type TableQueryOptions,
  useTableQuery,
} from '@/composables/useTableQuery'

type Sort = 'status' | 'title' | 'created_at'
type Filter = 'active' | 'todo' | 'ended'

const OPTIONS: TableQueryOptions<Sort, Filter> = {
  sortKeys: ['status', 'title', 'created_at'],
  defaultSort: 'status',
  sortDirs: { created_at: 'desc' },
  filters: ['active', 'todo', 'ended'],
  defaultFilter: 'active',
}

const Page = { template: '<div />' }

async function setup<S extends string, F extends string = never>(
  url: string,
  options: TableQueryOptions<S, F>,
): Promise<{ table: TableQuery<S, F>; router: Router }> {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/lists', name: 'lists', component: Page },
      { path: '/other', name: 'other', component: Page },
    ],
  })
  await router.push(url)
  await router.isReady()
  let table!: TableQuery<S, F>
  mount(
    defineComponent({
      setup() {
        table = useTableQuery(options)
        return () => null
      },
    }),
    { global: { plugins: [router] } },
  )
  return { table, router }
}

const query = (router: Router) => router.currentRoute.value.query

describe('useTableQuery: reading the URL', () => {
  it('starts from the defaults on a bare URL', async () => {
    const { table } = await setup('/lists', OPTIONS)
    expect(table.page.value).toBe(1)
    expect(table.sort.value).toBe('status')
    expect(table.dir.value).toBe('asc')
    expect(table.q.value).toBe('')
    expect(table.filter.value).toBe('active')
    expect(table.pageSize).toBe(20)
    expect(table.params.value).toEqual({
      status_filter: 'active',
      sort_by: 'status',
      sort_dir: 'asc',
      skip: 0,
      limit: 20,
    })
  })

  it('takes the state a URL carries', async () => {
    const { table } = await setup('/lists?page=3&sort=title&dir=desc&q=+Bar+&filter=todo', OPTIONS)
    expect(table.params.value).toEqual({
      status_filter: 'todo',
      q: 'Bar',
      sort_by: 'title',
      sort_dir: 'desc',
      skip: 40,
      limit: 20,
    })
  })

  it('gives a key its own default direction', async () => {
    const { table } = await setup('/lists?sort=created_at', OPTIONS)
    expect(table.dir.value).toBe('desc')
  })

  it('falls back to the defaults for values it does not know', async () => {
    const { table } = await setup('/lists?page=0&sort=nope&dir=up&filter=all', OPTIONS)
    expect(table.page.value).toBe(1)
    expect(table.sort.value).toBe('status')
    expect(table.dir.value).toBe('asc')
    expect(table.filter.value).toBe('active')

    const { table: again } = await setup('/lists?page=two', OPTIONS)
    expect(again.page.value).toBe(1)
  })

  it('reads the first of a repeated key, and clips a long search', async () => {
    const long = 'x'.repeat(MAX_SEARCH_LENGTH + 20)
    const { table } = await setup(`/lists?sort=title&sort=status&q=${long}`, OPTIONS)
    expect(table.sort.value).toBe('title')
    expect(table.q.value).toHaveLength(MAX_SEARCH_LENGTH)
  })

  it('keeps tables with a prefix apart', async () => {
    const { table } = await setup('/lists?page=4&signups_page=2&signups_sort=title', {
      ...OPTIONS,
      prefix: 'signups',
      pageSize: 10,
    })
    expect(table.page.value).toBe(2)
    expect(table.sort.value).toBe('title')
    expect(table.params.value.skip).toBe(10)
  })
})

describe('useTableQuery: changing the state', () => {
  it('goes back to page 1 on a new filter, and writes it to the URL', async () => {
    const { table, router } = await setup('/lists?page=3&tab=links#top', OPTIONS)
    table.filter.value = 'todo'
    await flushPromises()
    expect(table.page.value).toBe(1)
    expect(query(router)).toEqual({ tab: 'links', filter: 'todo' })
    expect(router.currentRoute.value.hash).toBe('#top')
  })

  it('ignores a filter it does not know, and the one already on', async () => {
    const { table, router } = await setup('/lists?page=2', OPTIONS)
    table.filter.value = 'nope' as Filter
    table.filter.value = 'active'
    await flushPromises()
    expect(table.page.value).toBe(2)
    expect(query(router)).toEqual({ page: '2' })
  })

  it('goes back to page 1 on a new search, trimmed, and only when it changed', async () => {
    const { table, router } = await setup('/lists?page=2&q=bar', OPTIONS)
    table.q.value = ' bar '
    expect(table.page.value).toBe(2)
    table.q.value = ' bühne '
    await flushPromises()
    expect(table.page.value).toBe(1)
    expect(query(router)).toEqual({ q: 'bühne' })
    table.q.value = ''
    await flushPromises()
    expect(query(router)).toEqual({})
  })

  it('flips the direction on the same column, and starts another in its own', async () => {
    const { table, router } = await setup('/lists?page=2', OPTIONS)
    table.setSort('status')
    expect(table.dir.value).toBe('desc')
    expect(table.page.value).toBe(1)
    table.setSort('status')
    expect(table.dir.value).toBe('asc')
    table.setSort('created_at')
    expect(table.dir.value).toBe('desc')
    await flushPromises()
    expect(query(router)).toEqual({ sort: 'created_at' })
    table.setSort('title')
    await flushPromises()
    expect(query(router)).toEqual({ sort: 'title' })
  })

  it('takes an explicit direction, and does nothing when it is already so', async () => {
    const { table, router } = await setup('/lists?page=2', OPTIONS)
    table.setSort('status', 'asc')
    expect(table.page.value).toBe(2)
    table.setSort('title', 'desc')
    await flushPromises()
    expect(query(router)).toEqual({ sort: 'title', dir: 'desc' })
  })

  it('keeps a page within reach, and leaves page 1 out of the URL', async () => {
    const { table, router } = await setup('/lists', OPTIONS)
    table.page.value = 2.7
    await flushPromises()
    expect(query(router)).toEqual({ page: '2' })
    table.page.value = -4
    await flushPromises()
    expect(table.page.value).toBe(1)
    expect(query(router)).toEqual({})
  })

  it('writes several changes in one tick with one replace', async () => {
    const { table, router } = await setup('/lists', OPTIONS)
    const replace = vi.spyOn(router, 'replace')
    table.filter.value = 'ended'
    table.q.value = 'bar'
    table.setSort('title')
    await flushPromises()
    expect(replace).toHaveBeenCalledTimes(1)
    expect(query(router)).toEqual({ filter: 'ended', q: 'bar', sort: 'title' })
  })

  it('steps back to the last page that still has rows', async () => {
    const { table } = await setup('/lists?page=3', OPTIONS)
    table.clampTo(41)
    expect(table.page.value).toBe(3)
    table.clampTo(40)
    expect(table.page.value).toBe(2)
    table.clampTo(0)
    expect(table.page.value).toBe(1)
  })

  it('resets to the defaults, which empties its part of the URL', async () => {
    const { table, router } = await setup('/lists?filter=todo&q=bar&page=2&tab=tasks', OPTIONS)
    const replace = vi.spyOn(router, 'replace')
    table.reset()
    await flushPromises()
    expect(query(router)).toEqual({ tab: 'tasks' })
    table.reset()
    await flushPromises()
    expect(replace).toHaveBeenCalledTimes(1)
  })

  it('changes its key with the state, and only then', async () => {
    const { table } = await setup('/lists', OPTIONS)
    const before = table.key.value
    table.filter.value = 'active'
    expect(table.key.value).toBe(before)
    table.page.value = 2
    expect(table.key.value).not.toBe(before)
  })
})

describe('useTableQuery: the URL changing underneath', () => {
  it('follows a navigation to the same page with another query', async () => {
    const { table, router } = await setup('/lists?q=bar', OPTIONS)
    const replace = vi.spyOn(router, 'replace')
    await router.push({ name: 'lists', query: { filter: 'todo' } })
    await flushPromises()
    expect(table.filter.value).toBe('todo')
    expect(table.q.value).toBe('')
    expect(replace).not.toHaveBeenCalled()
  })

  it('leaves the URL of another page alone', async () => {
    const { table, router } = await setup('/lists?filter=todo', OPTIONS)
    await router.push({ name: 'other', query: { page: '5' } })
    await flushPromises()
    expect(table.filter.value).toBe('todo')
    table.page.value = 3
    await flushPromises()
    expect(query(router)).toEqual({ page: '5' })
  })
})

describe('useTableQuery: a table without filters', () => {
  it('has no filter, and sends none', async () => {
    const { table, router } = await setup<'created_at' | 'name'>('/lists?filter=todo', {
      sortKeys: ['created_at', 'name'],
      defaultSort: 'created_at',
      sortDirs: { created_at: 'desc' },
      pageSize: 10,
    })
    expect(table.filter.value).toBeUndefined()
    table.filter.value = undefined
    await flushPromises()
    expect(table.params.value).toEqual({
      sort_by: 'created_at',
      sort_dir: 'desc',
      skip: 0,
      limit: 10,
    })
    expect(query(router)).toEqual({ filter: 'todo' })
  })
})
