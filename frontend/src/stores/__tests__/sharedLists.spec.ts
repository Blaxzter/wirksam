import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  type ListParams,
  PREVIEW_CHOICES_LIMIT,
  type SignupParams,
  type TaskParams,
  useSharedListsStore,
} from '@/stores/sharedLists'

import type {
  SharedListDetail,
  SharedListListResponse,
  SharedListOverview,
  SharedListRow,
  SharedListSignupListResponse,
  SharedListTaskListResponse,
} from '@/client/types.gen'

/**
 * The management page's store: one event's figures, the current page of each
 * table, the open list and its sign-ups. Every change reloads what is on
 * screen; a late answer never overwrites a newer one, nor the next event's.
 */

const api = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
}))
const toastApiError = vi.hoisted(() => vi.fn())

vi.mock('@/composables/useAuthenticatedClient', () => ({
  useAuthenticatedClient: () => ({ get: api.get, post: api.post, patch: api.patch }),
}))
vi.mock('@/lib/api-errors', () => ({ toastApiError }))

const EVENT = 'event-1'

function overview(patch: Partial<SharedListOverview> = {}): SharedListOverview {
  return {
    summary: { live_lists: 2, active_lists: 3, signups: 5, guests: 5, free_in_live: 7 },
    unshared: { task_count: 0, free: 0, task_names: [] },
    can_create: true,
    can_pause_all: true,
    is_admin: true,
    managers_share_lists: true,
    event_timezone: 'Europe/Berlin',
    ...patch,
  }
}

function row(id: string, patch: Partial<SharedListRow> = {}): SharedListRow {
  return {
    id,
    code: `code-${id}`,
    title: `List ${id}`,
    share_note: null,
    status: 'live',
    effective_status: 'live',
    ends_mode: 'last_shift',
    ends_on: null,
    closes_at: '2026-12-01T10:00:00',
    expires_soon: false,
    is_full: false,
    created_at: '2026-11-01T09:00:00',
    created_by_name: 'Anna',
    tasks: [],
    only_days: null,
    excluded_shift_count: 0,
    capacity: 10,
    free: 4,
    signup_count: 6,
    guest_count: 6,
    view_count: 12,
    issue: null,
    access: 'admin',
    ...patch,
  }
}

function lists(items: SharedListRow[]): SharedListListResponse {
  return {
    items,
    total: items.length,
    skip: 0,
    limit: 20,
    counts: { active: items.length, todo: 0, live: items.length, paused: 0, ended: 0 },
    ended_matching: 0,
  }
}

function tasks(): SharedListTaskListResponse {
  return { items: [], total: 0, skip: 0, limit: 20, counts: { all: 0, todo: 0 } }
}

function detail(id: string, patch: Partial<SharedListDetail> = {}): SharedListDetail {
  return {
    ...row(id),
    intro: null,
    ask_email: 'required',
    ask_phone: 'off',
    show_names: 'none',
    max_per_person: null,
    rotated_at: null,
    paused_at: null,
    ended_at: null,
    task_ids: [],
    excluded_shift_ids: [],
    detail_tasks: [],
    event: {
      id: EVENT,
      name: 'Fest',
      start_date: '2026-12-01',
      end_date: '2026-12-03',
      timezone: 'Europe/Berlin',
    },
    ...patch,
  }
}

function signups(total = 0): SharedListSignupListResponse {
  return { items: [], total, skip: 0, limit: 10, hidden_count: 0, can_erase: true }
}

const LIST_PARAMS: ListParams = {
  status_filter: 'active',
  sort_by: 'status',
  sort_dir: 'asc',
  skip: 0,
  limit: 20,
}
const TASK_PARAMS: TaskParams = {
  status_filter: 'all',
  sort_by: 'name',
  sort_dir: 'asc',
  skip: 0,
  limit: 20,
}
const SIGNUP_PARAMS: SignupParams = { sort_by: 'created_at', sort_dir: 'desc', skip: 0, limit: 10 }

/** Answers a GET by its path, so a reload of several things gets each its own. */
function serve(routes: Record<string, unknown>) {
  api.get.mockImplementation(({ url }: { url: string }) => {
    if (url in routes) return Promise.resolve({ data: routes[url] })
    return Promise.reject(new Error(`unexpected GET ${url}`))
  })
}

/** A promise and the function that settles it, for answers that arrive out of order. */
function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((r) => (resolve = r))
  return { promise, resolve }
}

function openStore() {
  const store = useSharedListsStore()
  store.setEvent(EVENT)
  return store
}

beforeEach(() => {
  vi.resetAllMocks()
  setActivePinia(createPinia())
})

describe('useSharedListsStore', () => {
  describe('the event', () => {
    it('starts empty and refuses to load without an event', async () => {
      const store = useSharedListsStore()
      expect(store.eventId).toBeNull()
      expect(store.overview).toBeNull()
      await expect(store.fetchOverview()).rejects.toThrow('No event chosen')
      expect(api.get).not.toHaveBeenCalled()
    })

    it('forgets the last event when another is chosen, and keeps it when it is the same', async () => {
      serve({
        [`/events/${EVENT}/shared-lists/overview`]: overview(),
        [`/events/${EVENT}/shared-lists`]: lists([row('a')]),
        [`/events/${EVENT}/shared-lists/tasks`]: tasks(),
        '/shared-lists/a': detail('a'),
      })
      const store = openStore()
      await store.fetchOverview()
      await store.fetchLists(LIST_PARAMS)
      await store.fetchTasks(TASK_PARAMS)
      await store.fetchDetail('a')

      store.setEvent(EVENT)
      expect(store.lists?.items).toHaveLength(1)

      store.setEvent('event-2')
      expect(store.eventId).toBe('event-2')
      expect(store.overview).toBeNull()
      expect(store.lists).toBeNull()
      expect(store.tasks).toBeNull()
      expect(store.detail).toBeNull()
    })

    it('drops an answer for the event that was left', async () => {
      const late = deferred<{ data: SharedListListResponse }>()
      api.get.mockReturnValueOnce(late.promise)
      const store = openStore()
      const loading = store.fetchLists(LIST_PARAMS)
      expect(store.listsLoading).toBe(true)

      store.setEvent('event-2')
      late.resolve({ data: lists([row('old')]) })
      await loading

      expect(store.lists).toBeNull()
      expect(store.listsLoading).toBe(false)
    })
  })

  describe('reading', () => {
    it('loads the figures', async () => {
      serve({ [`/events/${EVENT}/shared-lists/overview`]: overview() })
      const store = openStore()
      await expect(store.fetchOverview()).resolves.toMatchObject({ can_create: true })
      expect(store.overview?.summary.live_lists).toBe(2)
    })

    it('loads a page of lists with the table query', async () => {
      serve({ [`/events/${EVENT}/shared-lists`]: lists([row('a'), row('b')]) })
      const store = openStore()
      await store.fetchLists({ ...LIST_PARAMS, q: 'Kuchen' })
      expect(api.get).toHaveBeenCalledWith({
        url: `/events/${EVENT}/shared-lists`,
        query: { ...LIST_PARAMS, q: 'Kuchen' },
      })
      expect(store.lists?.items.map((r) => r.id)).toEqual(['a', 'b'])
      expect(store.listsLoading).toBe(false)
    })

    it('keeps the newer page when an older answer arrives last', async () => {
      const first = deferred<{ data: SharedListListResponse }>()
      const second = deferred<{ data: SharedListListResponse }>()
      api.get.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise)
      const store = openStore()
      const a = store.fetchLists(LIST_PARAMS)
      const b = store.fetchLists({ ...LIST_PARAMS, skip: 20 })

      second.resolve({ data: lists([row('page-2')]) })
      await b
      first.resolve({ data: lists([row('page-1')]) })
      await a

      expect(store.lists?.items.map((r) => r.id)).toEqual(['page-2'])
    })

    it('stops loading when the page fails, and says nothing itself', async () => {
      api.get.mockRejectedValueOnce(new Error('500'))
      const store = openStore()
      await expect(store.fetchLists(LIST_PARAMS)).rejects.toThrow('500')
      expect(store.listsLoading).toBe(false)
      expect(toastApiError).not.toHaveBeenCalled()
    })

    it('loads a page of tasks, newest request winning', async () => {
      const first = deferred<{ data: SharedListTaskListResponse }>()
      api.get.mockReturnValueOnce(first.promise).mockResolvedValueOnce({
        data: { ...tasks(), total: 3 },
      })
      const store = openStore()
      const a = store.fetchTasks(TASK_PARAMS)
      await store.fetchTasks({ ...TASK_PARAMS, status_filter: 'todo' })
      first.resolve({ data: { ...tasks(), total: 9 } })
      await a

      expect(api.get).toHaveBeenLastCalledWith({
        url: `/events/${EVENT}/shared-lists/tasks`,
        query: { ...TASK_PARAMS, status_filter: 'todo' },
      })
      expect(store.tasks?.total).toBe(3)
      expect(store.tasksLoading).toBe(false)
    })

    it('opens a list, clearing another one at once', async () => {
      serve({ '/shared-lists/a': detail('a'), '/shared-lists/b': detail('b') })
      const store = openStore()
      await store.fetchDetail('a')
      expect(store.detail?.id).toBe('a')

      const opening = store.fetchDetail('b')
      expect(store.detail).toBeNull()
      await opening
      expect(store.detail?.id).toBe('b')
    })

    it('keeps the open list while it reloads', async () => {
      serve({ '/shared-lists/a': detail('a') })
      const store = openStore()
      await store.fetchDetail('a')
      const reloading = store.fetchDetail('a')
      expect(store.detail?.id).toBe('a')
      await reloading
    })

    it('closes the list and drops its late answers', async () => {
      const late = deferred<{ data: SharedListDetail }>()
      api.get.mockReturnValueOnce(late.promise)
      const store = openStore()
      const opening = store.fetchDetail('a')
      store.closeDetail()
      late.resolve({ data: detail('a') })
      await opening
      expect(store.detail).toBeNull()
    })

    it('loads the sign-ups of the open list', async () => {
      serve({ '/shared-lists/a/signups': signups(4) })
      const store = openStore()
      await store.fetchSignups('a', SIGNUP_PARAMS)
      expect(api.get).toHaveBeenCalledWith({
        url: '/shared-lists/a/signups',
        query: SIGNUP_PARAMS,
      })
      expect(store.signups?.total).toBe(4)
      expect(store.signupsLoading).toBe(false)
    })

    it('drops sign-ups that arrive after the list was closed', async () => {
      const late = deferred<{ data: SharedListSignupListResponse }>()
      api.get.mockReturnValueOnce(late.promise)
      const store = openStore()
      const loading = store.fetchSignups('a', SIGNUP_PARAMS)
      store.closeDetail()
      late.resolve({ data: signups(2) })
      await loading
      expect(store.signups).toBeNull()
      expect(store.signupsLoading).toBe(false)
    })

    it('offers every list that has not ended for the preview', async () => {
      serve({ [`/events/${EVENT}/shared-lists`]: lists([row('a')]) })
      const store = openStore()
      await expect(store.fetchPreviewChoices()).resolves.toHaveLength(1)
      expect(api.get).toHaveBeenCalledWith({
        url: `/events/${EVENT}/shared-lists`,
        query: { status_filter: 'active', sort_by: 'title', limit: PREVIEW_CHOICES_LIMIT },
      })
      expect(store.lists).toBeNull()
    })

    it('loads the page a guest would see', async () => {
      const page = { code: 'abc', title: 'Kuchen' }
      serve({ '/shared-lists/a/preview': page })
      const store = openStore()
      await expect(store.fetchPreview('a')).resolves.toEqual(page)
    })
  })

  describe('who may reopen', () => {
    it.each([
      [null, false],
      [overview({ is_admin: true, managers_share_lists: false }), false],
      [overview({ is_admin: false, managers_share_lists: true }), false],
      [overview({ is_admin: false, managers_share_lists: false }), true],
    ])('locks a person in charge only while sharing is off for them', (value, locked) => {
      const store = openStore()
      store.overview = value
      expect(store.reshareLocked).toBe(locked)
    })
  })

  describe('changing a list', () => {
    async function seeded() {
      serve({
        [`/events/${EVENT}/shared-lists/overview`]: overview(),
        [`/events/${EVENT}/shared-lists`]: lists([row('a'), row('b')]),
        [`/events/${EVENT}/shared-lists/tasks`]: tasks(),
        '/shared-lists/a': detail('a'),
        '/shared-lists/b': detail('b'),
        '/shared-lists/a/signups': signups(1),
      })
      const store = openStore()
      await store.fetchOverview()
      await store.fetchLists(LIST_PARAMS)
      await store.fetchTasks(TASK_PARAMS)
      api.get.mockClear()
      return store
    }

    const gets = () => api.get.mock.calls.map(([options]) => (options as { url: string }).url)

    it.each(['pause', 'resume', 'end', 'rotate'] as const)(
      'posts %s and reloads the figures and both tables',
      async (action) => {
        const store = await seeded()
        api.post.mockResolvedValueOnce({ data: detail('b', { status: 'paused' }) })

        await store.act('b', action)

        expect(api.post).toHaveBeenCalledWith({ url: `/shared-lists/b/${action}` })
        expect(gets()).toEqual([
          `/events/${EVENT}/shared-lists/overview`,
          `/events/${EVENT}/shared-lists`,
          `/events/${EVENT}/shared-lists/tasks`,
        ])
      },
    )

    it('extends a list until its last shift', async () => {
      const store = await seeded()
      api.patch.mockResolvedValueOnce({ data: detail('a', { ends_mode: 'last_shift' }) })

      await store.act('a', 'extend')

      expect(api.patch).toHaveBeenCalledWith({
        url: '/shared-lists/a',
        body: { ends_mode: 'last_shift', ends_on: null },
      })
    })

    it('takes the open list from the answer instead of loading it again', async () => {
      const store = await seeded()
      await store.fetchDetail('a')
      api.get.mockClear()
      api.post.mockResolvedValueOnce({ data: detail('a', { effective_status: 'paused' }) })

      await store.act('a', 'pause')

      expect(store.detail?.effective_status).toBe('paused')
      expect(gets()).not.toContain('/shared-lists/a')
    })

    it('keeps a change of the open list over an older load of it still on its way', async () => {
      const store = await seeded()
      await store.fetchDetail('a')
      const late = deferred<{ data: SharedListDetail }>()
      api.get.mockReturnValueOnce(late.promise)
      const reloading = store.fetchDetail('a')
      api.post.mockResolvedValueOnce({ data: detail('a', { effective_status: 'paused' }) })

      await store.act('a', 'pause')
      late.resolve({ data: detail('a', { effective_status: 'live' }) })
      await reloading

      expect(store.detail?.effective_status).toBe('paused')
    })

    it('reloads the open list when another one changed', async () => {
      const store = await seeded()
      await store.fetchDetail('a')
      api.get.mockClear()
      api.post.mockResolvedValueOnce({ data: detail('b') })

      await store.act('b', 'end')

      expect(gets()).toContain('/shared-lists/a')
    })

    it('says so when the reload fails, after the change itself worked', async () => {
      const store = await seeded()
      api.post.mockResolvedValueOnce({ data: detail('a') })
      const failure = new Error('502')
      api.get.mockRejectedValue(failure)

      await expect(store.act('a', 'pause')).resolves.toMatchObject({ id: 'a' })

      expect(toastApiError).toHaveBeenCalledOnce()
      expect(toastApiError).toHaveBeenCalledWith(failure)
      expect(store.lists?.items).toHaveLength(2)
    })

    it('leaves the screen alone when the change is refused', async () => {
      const store = await seeded()
      api.post.mockRejectedValueOnce(new Error('409'))
      await expect(store.act('a', 'resume')).rejects.toThrow('409')
      expect(api.get).not.toHaveBeenCalled()
    })

    it('changes several lists at once and reloads', async () => {
      const store = await seeded()
      const result = { changed: ['a'], skipped: [{ id: 'b', code: 'shared_list.ended' }] }
      api.post.mockResolvedValueOnce({ data: result })

      await expect(store.bulk('end', ['a', 'b'])).resolves.toEqual(result)

      expect(api.post).toHaveBeenCalledWith({
        url: `/events/${EVENT}/shared-lists/bulk`,
        body: { action: 'end', list_ids: ['a', 'b'] },
      })
      expect(gets()).toContain(`/events/${EVENT}/shared-lists`)
    })

    it.each([true, false])('pauses every list, locking people in charge: %s', async (lock) => {
      const store = await seeded()
      api.post.mockResolvedValueOnce({ data: { changed: ['a', 'b'], skipped: [] } })

      await store.pauseAll(lock)

      expect(api.post).toHaveBeenCalledWith({
        url: `/events/${EVENT}/shared-lists/pause-all`,
        body: { lock_managers: lock },
      })
      expect(gets()).toContain(`/events/${EVENT}/shared-lists/overview`)
    })

    it('turns sharing for people in charge off through the event', async () => {
      const store = await seeded()
      api.patch.mockResolvedValueOnce({ data: {} })

      await store.setManagersShareLists(false)

      expect(api.patch).toHaveBeenCalledWith({
        url: `/events/${EVENT}`,
        body: { managers_share_lists: false },
      })
      expect(gets()).toContain(`/events/${EVENT}/shared-lists/overview`)
    })

    it('removes sign-ups and reloads the list and its sign-ups', async () => {
      const store = await seeded()
      await store.fetchDetail('a')
      await store.fetchSignups('a', SIGNUP_PARAMS)
      api.get.mockClear()
      const result = { removed: ['bk-1'], erased_guests: 0, also_removed: 0, skipped: [] }
      api.post.mockResolvedValueOnce({ data: result })

      await expect(
        store.removeSignups('a', { booking_ids: ['bk-1'], notify: false, erase: false }),
      ).resolves.toEqual(result)

      expect(api.post).toHaveBeenCalledWith({
        url: '/shared-lists/a/signups/remove',
        body: { booking_ids: ['bk-1'], notify: false, erase: false },
      })
      expect(gets()).toEqual(expect.arrayContaining(['/shared-lists/a', '/shared-lists/a/signups']))
    })
  })
})
