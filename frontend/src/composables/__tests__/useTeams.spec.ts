import { effectScope, nextTick, ref } from 'vue'

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { invalidateTeams, teamsPageLocation, useTeams } from '@/composables/useTeams'

import type { EventTeamRead } from '@/client/types.gen'

const api = vi.hoisted(() => ({ get: vi.fn() }))

vi.mock('@/composables/useAuthenticatedClient', () => ({
  useAuthenticatedClient: () => ({ get: api.get }),
}))

function team(id: string, name: string, eventId = 'e1'): EventTeamRead {
  return {
    id,
    event_id: eventId,
    name,
    requires_approval: true,
    created_at: '2026-10-01T00:00:00Z',
  }
}

/** Let the queued promise callbacks run. */
const flush = () => new Promise((r) => setTimeout(r, 0))

const scopes: ReturnType<typeof effectScope>[] = []
function setup(eventId: Parameters<typeof useTeams>[0]) {
  const scope = effectScope()
  scopes.push(scope)
  return scope.run(() => useTeams(eventId))!
}

beforeEach(() => {
  vi.resetAllMocks()
  invalidateTeams()
})

afterEach(() => {
  scopes.splice(0).forEach((s) => s.stop())
})

describe('useTeams', () => {
  it('loads the event’s teams', async () => {
    api.get.mockResolvedValue({ data: [team('t1', 'Kasse')] })
    const { teams, loading } = setup('e1')

    expect(loading.value).toBe(true)
    await flush()

    expect(api.get).toHaveBeenCalledWith({ url: '/events/e1/teams' })
    expect(teams.value.map((t) => t.name)).toEqual(['Kasse'])
    expect(loading.value).toBe(false)
  })

  it('shares a request still in flight between instances', async () => {
    api.get.mockResolvedValue({ data: [team('t1', 'Kasse')] })
    const a = setup('e1')
    const b = setup('e1')
    await flush()

    expect(api.get).toHaveBeenCalledTimes(1)
    expect(b.teams.value).toEqual(a.teams.value)
  })

  it('does not keep a settled list: the next instance asks again', async () => {
    // The list carries the viewer's own status, which joining changes.
    api.get.mockResolvedValue({ data: [team('t1', 'Kasse')] })
    setup('e1')
    await flush()
    setup('e1')
    await flush()

    expect(api.get).toHaveBeenCalledTimes(2)
  })

  it('is empty without an event and makes no request', async () => {
    const { teams, loading } = setup(null)
    await flush()

    expect(api.get).not.toHaveBeenCalled()
    expect(teams.value).toEqual([])
    expect(loading.value).toBe(false)
  })

  it('follows a changing event id', async () => {
    api.get.mockImplementation(({ url }: { url: string }) =>
      Promise.resolve({
        data: url.includes('e2') ? [team('t2', 'Küche', 'e2')] : [team('t1', 'Kasse')],
      }),
    )
    const eventId = ref<string | null>('e1')
    const { teams } = setup(eventId)
    await flush()
    expect(teams.value[0]!.name).toBe('Kasse')

    eventId.value = 'e2'
    await flush()
    expect(teams.value[0]!.name).toBe('Küche')

    eventId.value = null
    await flush()
    expect(teams.value).toEqual([])
  })

  it('drops an older response that settles after a newer one', async () => {
    let resolveFirst!: (value: unknown) => void
    api.get
      .mockImplementationOnce(() => new Promise((res) => (resolveFirst = res)))
      .mockResolvedValueOnce({ data: [team('t2', 'Küche', 'e2')] })
    const eventId = ref('e1')
    const { teams } = setup(eventId)
    eventId.value = 'e2'
    await flush()
    resolveFirst({ data: [team('t1', 'Kasse')] })
    await flush()

    expect(teams.value.map((t) => t.name)).toEqual(['Küche'])
  })

  it('reloads every instance of an event after invalidateTeams', async () => {
    api.get
      .mockResolvedValueOnce({ data: [team('t1', 'Kasse')] })
      .mockResolvedValueOnce({ data: [team('t1', 'Kasse'), team('t2', 'Küche')] })
    const a = setup('e1')
    const b = setup('e1')
    await flush()

    invalidateTeams('e1')
    await nextTick()
    await flush()

    expect(api.get).toHaveBeenCalledTimes(2)
    expect(a.teams.value).toHaveLength(2)
    expect(b.teams.value).toHaveLength(2)
  })

  it('reload asks again', async () => {
    api.get.mockResolvedValue({ data: [] })
    const { reload } = setup('e1')
    await flush()
    await reload()

    expect(api.get).toHaveBeenCalledTimes(2)
  })

  it('records an error and lets the next caller retry', async () => {
    api.get.mockRejectedValueOnce(new Error('500')).mockResolvedValueOnce({
      data: [team('t1', 'Kasse')],
    })
    const first = setup('e1')
    await flush()
    expect(first.error.value).toBeInstanceOf(Error)
    expect(first.teams.value).toEqual([])
    expect(first.loading.value).toBe(false)

    const second = setup('e1')
    await flush()
    expect(api.get).toHaveBeenCalledTimes(2)
    expect(second.teams.value).toHaveLength(1)
  })

  it('keeps a newer in-flight request when an invalidated one settles', async () => {
    let resolveFirst!: (value: unknown) => void
    let resolveSecond!: (value: unknown) => void
    api.get
      .mockImplementationOnce(() => new Promise((res) => (resolveFirst = res)))
      .mockImplementationOnce(() => new Promise((res) => (resolveSecond = res)))
    setup('e1')
    invalidateTeams('e1')
    await nextTick()
    // The first request settles while the second one is still on its way…
    resolveFirst({ data: [] })
    await flush()
    // …so a new instance joins the second instead of asking a third time.
    setup('e1')
    await flush()
    expect(api.get).toHaveBeenCalledTimes(2)
    resolveSecond({ data: [] })
    await flush()
  })
})

describe('teamsPageLocation', () => {
  it('points at the Teams page and its team', () => {
    expect(teamsPageLocation('e1', 't1')).toEqual({
      name: 'teams',
      params: { eventId: 'e1' },
      query: { team: 't1' },
    })
    expect(teamsPageLocation(null)).toEqual({ name: 'teams', params: {}, query: {} })
  })
})
