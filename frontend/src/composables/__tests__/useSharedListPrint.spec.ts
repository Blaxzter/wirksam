import { AxiosError, type AxiosResponse } from 'axios'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useSharedListPrint } from '@/composables/useSharedListPrint'

import type { EventRead, ShiftRead, TaskRead } from '@/client/types.gen'
import { noticeListBody } from '@/lib/shared-list-print'

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), patch: vi.fn() }))
const toastApiError = vi.hoisted(() => vi.fn())

vi.mock('@/composables/useAuthenticatedClient', () => ({ useAuthenticatedClient: () => api }))
vi.mock('@/lib/api-errors', async (original) => ({
  ...(await original<typeof import('@/lib/api-errors')>()),
  toastApiError,
}))

function event(patch: Partial<EventRead> = {}): EventRead {
  return {
    id: 'e1',
    name: 'Basar',
    start_date: '2099-12-05',
    end_date: '2099-12-06',
    status: 'published',
    timezone: 'Europe/Berlin',
    is_sandbox: false,
    managed_task_count: 0,
    managers_share_lists: true,
    created_at: '',
    updated_at: '',
    can_manage: true,
    is_expired: false,
    ...patch,
  }
}

function task(id: string, patch: Partial<TaskRead> = {}): TaskRead {
  return {
    id,
    name: `Task ${id}`,
    start_date: '2099-12-05',
    end_date: '2099-12-05',
    status: 'published',
    event_id: 'e1',
    can_manage: true,
    created_at: '',
    updated_at: '',
    ...patch,
  }
}

/** A shift far ahead with a place left. */
const open: ShiftRead = {
  id: 's1',
  task_id: 't1',
  title: 'Kuchen',
  date: '2099-12-05',
  start_time: '10:00:00',
  max_bookings: 2,
  current_bookings: 0,
  created_at: '',
  updated_at: '',
}

function refusal(status: number) {
  return new AxiosError('refused', String(status), undefined, undefined, {
    status,
    data: { status, title: 'refused', code: 'shared_list.forbidden' },
  } as AxiosResponse)
}

/** What the reusable lookup answers now; a test may change it between calls. */
const lookup: { list: unknown } = { list: null }

/** GET /events/{id} answers `ev`; the reusable lookup answers `lookup.list` (or throws it). */
function serve(ev: EventRead, list: unknown) {
  lookup.list = list
  api.get.mockImplementation(({ url }: { url: string }) => {
    if (url === `/events/${ev.id}`) return Promise.resolve({ data: ev })
    if (url.endsWith('/shared-lists/reusable')) {
      return lookup.list instanceof Error
        ? Promise.reject(lookup.list)
        : Promise.resolve({ data: { list: lookup.list } })
    }
    return Promise.reject(new Error(`unexpected GET ${url}`))
  })
}

beforeEach(() => {
  vi.resetAllMocks()
})

afterEach(() => {
  delete globalThis.__APP_CONFIG__
})

describe('useSharedListPrint, one task', () => {
  it('prints the plain sheet for someone who neither runs the event nor the task', async () => {
    const notice = useSharedListPrint()
    expect(await notice.startTask(task('t1', { can_manage: false }), [open])).toEqual({
      kind: 'plain',
    })
    expect(await notice.startTask(task('t1', { event_id: null }), [open])).toEqual({
      kind: 'plain',
    })
    expect(api.get).not.toHaveBeenCalled()
  })

  it('prints the plain sheet in a demo, without looking for a list', async () => {
    serve(event({ is_sandbox: true }), null)
    const notice = useSharedListPrint()
    expect(await notice.startTask(task('t1'), [open])).toEqual({ kind: 'plain' })
    expect(api.get).toHaveBeenCalledOnce()
  })

  it('explains why a team-only task gets no QR code', async () => {
    serve(event(), null)
    const notice = useSharedListPrint()
    expect(await notice.startTask(task('t1', { team_id: 'x' }), [open])).toEqual({
      kind: 'asking',
    })
    expect(notice.dialog.value).toEqual({ kind: 'task', problem: 'team_locked' })
  })

  it('goes to the open list of exactly this task', async () => {
    serve(event(), { id: 'l1' })
    const notice = useSharedListPrint()
    expect(await notice.startTask(task('t1'), [open])).toEqual({ kind: 'list', listId: 'l1' })
    expect(api.get).toHaveBeenCalledWith({
      url: '/events/e1/shared-lists/reusable',
      query: { task_id: ['t1'] },
    })
    expect(notice.dialog.value).toBeNull()
  })

  it('asks before creating a list named after the task when there is none', async () => {
    serve(event(), null)
    const notice = useSharedListPrint()
    expect(await notice.startTask(task('t1'), [open])).toEqual({ kind: 'asking' })
    expect(notice.dialog.value).toEqual({
      kind: 'create',
      eventId: 'e1',
      title: 'Task t1',
      taskIds: ['t1'],
      leftOut: [],
      covering: false,
    })
    expect(notice.wizardRoute()).toEqual({
      name: 'shared-list-create',
      params: { eventId: 'e1' },
      query: { tasks: 't1' },
    })
  })

  it.each([403, 404])('takes a %i from the lookup as the server saying no list', async (status) => {
    serve(event(), refusal(status))
    const notice = useSharedListPrint()
    expect(await notice.startTask(task('t1'), [open])).toEqual({ kind: 'plain' })
  })

  it('passes on any other failure of the lookup', async () => {
    serve(event(), refusal(500))
    const notice = useSharedListPrint()
    await expect(notice.startTask(task('t1'), [open])).rejects.toBeInstanceOf(AxiosError)
  })
})

describe('useSharedListPrint, a whole event', () => {
  const shiftsOf = (taskId: string) => (taskId === 'over' ? [] : [open])

  it('prints plain sheets for whoever cannot share here', async () => {
    const notice = useSharedListPrint()
    const outcome = await notice.startEvent(
      event({ can_manage: false }),
      [task('a')],
      shiftsOf,
      'Basar – alle Aufgaben',
    )
    expect(outcome).toEqual({ kind: 'plain' })
  })

  it('explains when no task can go on a list', async () => {
    const notice = useSharedListPrint()
    const outcome = await notice.startEvent(event(), [task('over')], shiftsOf, 'Basar')
    expect(outcome).toEqual({ kind: 'asking' })
    expect(notice.dialog.value).toEqual({
      kind: 'event',
      reason: 'none_offered',
      offered: 0,
      leftOut: [{ id: 'over', name: 'Task over', problem: 'no_shift_ahead' }],
    })
  })

  it('looks for a list holding at least the tasks it can offer', async () => {
    serve(event(), { id: 'all' })
    const notice = useSharedListPrint()
    const outcome = await notice.startEvent(event(), [task('a'), task('b')], shiftsOf, 'Basar')
    expect(outcome).toEqual({ kind: 'list', listId: 'all' })
    expect(api.get).toHaveBeenCalledWith({
      url: '/events/e1/shared-lists/reusable',
      query: { task_id: ['a', 'b'], covering: true },
    })
  })

  it('asks about one list for the tasks it can offer, naming the rest', async () => {
    serve(event(), null)
    const notice = useSharedListPrint()
    const outcome = await notice.startEvent(event(), [task('a'), task('over')], shiftsOf, 'Basar')
    expect(outcome).toEqual({ kind: 'asking' })
    expect(notice.dialog.value).toEqual({
      kind: 'create',
      eventId: 'e1',
      title: 'Basar',
      taskIds: ['a'],
      leftOut: [{ id: 'over', name: 'Task over', problem: 'no_shift_ahead' }],
      covering: true,
    })
  })
})

describe('useSharedListPrint, creating', () => {
  async function asking() {
    serve(event(), null)
    const notice = useSharedListPrint()
    await notice.startTask(task('t1'), [open])
    return notice
  }

  it('creates the list with the defaults and closes the question', async () => {
    const notice = await asking()
    api.post.mockResolvedValue({ data: { id: 'new' } })

    expect(await notice.createList()).toBe('new')
    expect(api.post).toHaveBeenCalledWith({
      url: '/events/e1/shared-lists',
      body: noticeListBody('Task t1', ['t1']),
    })
    expect(notice.dialog.value).toBeNull()
    expect(notice.creating.value).toBe(false)
  })

  it('takes the list someone made while the question stood open', async () => {
    const notice = await asking()
    lookup.list = { id: 'theirs' }

    expect(await notice.createList()).toBe('theirs')
    expect(api.post).not.toHaveBeenCalled()
    expect(notice.dialog.value).toBeNull()
  })

  it('says why when the server refuses, and keeps asking', async () => {
    const notice = await asking()
    api.post.mockRejectedValue(refusal(422))

    expect(await notice.createList()).toBeNull()
    expect(toastApiError).toHaveBeenCalledOnce()
    expect(notice.dialog.value?.kind).toBe('create')
  })

  it('creates nothing twice, nor without the question', async () => {
    const notice = await asking()
    let answer: (value: unknown) => void = () => {}
    api.post.mockReturnValue(new Promise((resolve) => (answer = resolve)))

    const first = notice.createList()
    expect(await notice.createList()).toBeNull()
    answer({ data: { id: 'new' } })
    expect(await first).toBe('new')

    expect(await notice.createList()).toBeNull()
    expect(notice.wizardRoute()).toBeNull()
    expect(api.post).toHaveBeenCalledOnce()
  })

  it('closes', async () => {
    const notice = await asking()
    notice.close()
    expect(notice.dialog.value).toBeNull()
  })
})
