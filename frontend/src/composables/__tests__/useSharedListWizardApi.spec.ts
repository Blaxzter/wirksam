import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  CANDIDATE_PAGE_SIZE,
  SHIFT_TASKS_PER_REQUEST,
  useSharedListWizardApi,
} from '@/composables/useSharedListWizardApi'

import type {
  SharedListCandidate,
  SharedListCandidateListResponse,
  SharedListCandidateShift,
} from '@/client/types.gen'

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), patch: vi.fn() }))

vi.mock('@/composables/useAuthenticatedClient', () => ({
  useAuthenticatedClient: () => api,
}))

function candidate(id: string): SharedListCandidate {
  return {
    id,
    name: id,
    location: null,
    manager_names: [],
    shift_count: 1,
    dates: ['2026-12-05'],
    capacity: 2,
    free: 2,
    team: null,
    earns_vouchers: false,
  }
}

function page(items: SharedListCandidate[], total: number): SharedListCandidateListResponse {
  return { items, total, skip: 0, limit: CANDIDATE_PAGE_SIZE, locked_count: 0, locked_names: [] }
}

function shift(id: string, taskId: string): SharedListCandidateShift {
  return {
    id,
    task_id: taskId,
    date: '2026-12-05',
    start_time: '10:00:00',
    end_time: '12:00:00',
    capacity: 2,
    free: 1,
  }
}

/** Let the queued promise callbacks run. */
const flush = () => new Promise((resolve) => setTimeout(resolve, 0))

beforeEach(() => {
  vi.resetAllMocks()
})

describe('useSharedListWizardApi requests', () => {
  it('reads the event', async () => {
    api.get.mockResolvedValue({ data: { id: 'e1' } })
    await expect(useSharedListWizardApi().fetchEvent('e1')).resolves.toEqual({ id: 'e1' })
    expect(api.get).toHaveBeenCalledWith({ url: '/events/e1' })
  })

  it('asks for a page of candidates, sending a search only when there is one', async () => {
    api.get.mockResolvedValue({ data: page([], 0) })
    const { fetchCandidates } = useSharedListWizardApi()

    await fetchCandidates('e1')
    expect(api.get).toHaveBeenLastCalledWith({
      url: '/events/e1/shared-lists/candidates',
      query: { q: undefined, skip: 0, limit: CANDIDATE_PAGE_SIZE },
    })

    await fetchCandidates('e1', { q: 'bar', skip: 50 })
    expect(api.get).toHaveBeenLastCalledWith({
      url: '/events/e1/shared-lists/candidates',
      query: { q: 'bar', skip: 50, limit: CANDIDATE_PAGE_SIZE },
    })
  })

  it('finds picked tasks page by page, in the order asked, leaving out the unknown', async () => {
    const first = Array.from({ length: CANDIDATE_PAGE_SIZE }, (_, i) => candidate(`t${i}`))
    api.get
      .mockResolvedValueOnce({ data: page(first, CANDIDATE_PAGE_SIZE + 1) })
      .mockResolvedValueOnce({ data: page([candidate('late')], CANDIDATE_PAGE_SIZE + 1) })

    const found = await useSharedListWizardApi().findCandidates('e1', ['late', 'nope', 't3'])

    expect(found.map((c) => c.id)).toEqual(['late', 't3'])
    expect(api.get).toHaveBeenCalledTimes(2)
    expect(api.get.mock.calls[1][0].query.skip).toBe(CANDIDATE_PAGE_SIZE)
  })

  it('stops looking once every task is found', async () => {
    api.get.mockResolvedValue({ data: page([candidate('a')], 500) })
    await useSharedListWizardApi().findCandidates('e1', ['a'])
    expect(api.get).toHaveBeenCalledTimes(1)
  })

  it('asks for nothing when no task was picked', async () => {
    await expect(useSharedListWizardApi().findCandidates('e1', [])).resolves.toEqual([])
    expect(api.get).not.toHaveBeenCalled()
  })

  it('asks for shifts in batches the API takes', async () => {
    const ids = Array.from({ length: SHIFT_TASKS_PER_REQUEST + 1 }, (_, i) => `t${i}`)
    api.get
      .mockResolvedValueOnce({ data: [shift('a', 't0')] })
      .mockResolvedValueOnce({ data: [shift('b', `t${SHIFT_TASKS_PER_REQUEST}`)] })

    const shifts = await useSharedListWizardApi().fetchCandidateShifts('e1', ids)

    expect(shifts.map((s) => s.id)).toEqual(['a', 'b'])
    expect(api.get.mock.calls[0][0]).toEqual({
      url: '/events/e1/shared-lists/candidate-shifts',
      query: { task_id: ids.slice(0, SHIFT_TASKS_PER_REQUEST) },
    })
    expect(api.get.mock.calls[1][0].query.task_id).toEqual([`t${SHIFT_TASKS_PER_REQUEST}`])
  })

  it('reads, creates and edits a list', async () => {
    const { fetchDetail, create, update } = useSharedListWizardApi()
    api.get.mockResolvedValue({ data: { id: 'l1' } })
    api.post.mockResolvedValue({ data: { id: 'l2' } })
    api.patch.mockResolvedValue({ data: { id: 'l1' } })

    await expect(fetchDetail('l1')).resolves.toEqual({ id: 'l1' })
    expect(api.get).toHaveBeenCalledWith({ url: '/shared-lists/l1' })

    const body = { title: 'Bar', task_ids: ['t1'] }
    await expect(create('e1', body)).resolves.toEqual({ id: 'l2' })
    expect(api.post).toHaveBeenCalledWith({ url: '/events/e1/shared-lists', body })

    await expect(update('l1', { title: 'Kasse' })).resolves.toEqual({ id: 'l1' })
    expect(api.patch).toHaveBeenCalledWith({ url: '/shared-lists/l1', body: { title: 'Kasse' } })
  })
})

describe('useSharedListWizardApi shifts per task', () => {
  it('loads the shifts of each task once and keeps them', async () => {
    api.get.mockResolvedValue({ data: [shift('a1', 'a'), shift('b1', 'b')] })
    const { loadShifts, shiftsByTask, shiftsLoading } = useSharedListWizardApi()

    const pending = loadShifts('e1', ['a', 'b'])
    expect(shiftsLoading.value).toBe(true)
    await pending

    expect(shiftsLoading.value).toBe(false)
    expect(shiftsByTask.value.get('a')?.map((s) => s.id)).toEqual(['a1'])
    expect(shiftsByTask.value.get('b')?.map((s) => s.id)).toEqual(['b1'])

    await loadShifts('e1', ['a', 'b'])
    expect(api.get).toHaveBeenCalledTimes(1)
  })

  it('knows a task without shifts ahead as one with none', async () => {
    api.get.mockResolvedValue({ data: [] })
    const { loadShifts, shiftsByTask } = useSharedListWizardApi()
    await loadShifts('e1', ['a'])
    expect(shiftsByTask.value.get('a')).toEqual([])
  })

  it('asks only for the tasks it does not know, nor is already asking about', async () => {
    let answer: (value: { data: SharedListCandidateShift[] }) => void = () => {}
    api.get.mockReturnValueOnce(new Promise((resolve) => (answer = resolve)))
    api.get.mockResolvedValueOnce({ data: [shift('c1', 'c')] })
    const { loadShifts, shiftsByTask } = useSharedListWizardApi()

    const first = loadShifts('e1', ['a'])
    await loadShifts('e1', ['a', 'c'])
    expect(api.get.mock.calls[1][0].query.task_id).toEqual(['c'])

    answer({ data: [shift('a1', 'a')] })
    await first
    expect([...shiftsByTask.value.keys()].sort()).toEqual(['a', 'c'])
  })

  it('keeps the error and asks again on the next try', async () => {
    const failure = new Error('offline')
    api.get.mockRejectedValueOnce(failure).mockResolvedValueOnce({ data: [shift('a1', 'a')] })
    const { loadShifts, shiftsByTask, shiftsError, shiftsLoading } = useSharedListWizardApi()

    await loadShifts('e1', ['a'])
    expect(shiftsError.value).toBe(failure)
    expect(shiftsLoading.value).toBe(false)
    expect(shiftsByTask.value.has('a')).toBe(false)

    await loadShifts('e1', ['a'])
    await flush()
    expect(shiftsError.value).toBeNull()
    expect(shiftsByTask.value.has('a')).toBe(true)
  })
})
