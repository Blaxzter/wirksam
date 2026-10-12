import { effectScope, nextTick, ref } from 'vue'

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { invalidateLocations, useLocations } from '@/composables/useLocations'

import type { LocationRead } from '@/client/types.gen'

const api = vi.hoisted(() => ({ get: vi.fn() }))

vi.mock('@/composables/useAuthenticatedClient', () => ({
  useAuthenticatedClient: () => ({ get: api.get }),
}))

function location(id: string, name: string, eventId = 'e1'): LocationRead {
  return {
    id,
    event_id: eventId,
    name,
    created_at: '2026-10-01T00:00:00Z',
    updated_at: '2026-10-01T00:00:00Z',
  }
}

/** Let the queued promise callbacks run. */
const flush = () => new Promise((r) => setTimeout(r, 0))

const scopes: ReturnType<typeof effectScope>[] = []
function setup(eventId: Parameters<typeof useLocations>[0]) {
  const scope = effectScope()
  scopes.push(scope)
  return scope.run(() => useLocations(eventId))!
}

beforeEach(() => {
  vi.resetAllMocks()
  // The cache is module state; start every test from nothing.
  invalidateLocations()
})

afterEach(() => {
  scopes.splice(0).forEach((s) => s.stop())
})

describe('useLocations', () => {
  it('loads the event’s locations', async () => {
    api.get.mockResolvedValue({ data: [location('l1', 'Foyer')] })
    const { locations, loading } = setup('e1')

    expect(loading.value).toBe(true)
    await flush()

    expect(api.get).toHaveBeenCalledWith({ url: '/events/e1/locations' })
    expect(locations.value.map((l) => l.name)).toEqual(['Foyer'])
    expect(loading.value).toBe(false)
  })

  it('shares one request between instances for the same event', async () => {
    api.get.mockResolvedValue({ data: [location('l1', 'Foyer')] })
    const a = setup('e1')
    const b = setup('e1')
    await flush()

    expect(api.get).toHaveBeenCalledTimes(1)
    expect(b.locations.value).toEqual(a.locations.value)
  })

  it('is empty without an event and makes no request', async () => {
    const { locations, loading } = setup(null)
    await flush()

    expect(api.get).not.toHaveBeenCalled()
    expect(locations.value).toEqual([])
    expect(loading.value).toBe(false)
  })

  it('follows a changing event id', async () => {
    api.get.mockImplementation(({ url }: { url: string }) =>
      Promise.resolve({
        data: url.includes('e2') ? [location('l2', 'Hall', 'e2')] : [location('l1', 'Foyer')],
      }),
    )
    const eventId = ref<string | null>('e1')
    const { locations } = setup(eventId)
    await flush()
    expect(locations.value[0]!.name).toBe('Foyer')

    eventId.value = 'e2'
    await flush()
    expect(locations.value[0]!.name).toBe('Hall')

    eventId.value = null
    await flush()
    expect(locations.value).toEqual([])
  })

  it('reloads every instance of an event after invalidateLocations', async () => {
    api.get
      .mockResolvedValueOnce({ data: [location('l1', 'Foyer')] })
      .mockResolvedValueOnce({ data: [location('l1', 'Foyer'), location('l2', 'Hall')] })
    const a = setup('e1')
    const b = setup('e1')
    await flush()

    invalidateLocations('e1')
    await nextTick()
    await flush()

    expect(api.get).toHaveBeenCalledTimes(2)
    expect(a.locations.value).toHaveLength(2)
    expect(b.locations.value).toHaveLength(2)
  })

  it('reload bypasses the cache', async () => {
    api.get.mockResolvedValue({ data: [] })
    const { reload } = setup('e1')
    await flush()
    await reload()

    expect(api.get).toHaveBeenCalledTimes(2)
  })

  it('records an error and lets the next caller retry', async () => {
    api.get.mockRejectedValueOnce(new Error('404')).mockResolvedValueOnce({
      data: [location('l1', 'Foyer')],
    })
    const first = setup('e1')
    await flush()
    expect(first.error.value).toBeInstanceOf(Error)
    expect(first.locations.value).toEqual([])
    expect(first.loading.value).toBe(false)

    const second = setup('e1')
    await flush()
    expect(api.get).toHaveBeenCalledTimes(2)
    expect(second.locations.value).toHaveLength(1)
  })

  it('keeps a newer cache entry when an old failed request settles', async () => {
    let rejectFirst!: (reason: unknown) => void
    api.get
      .mockImplementationOnce(() => new Promise((_res, rej) => (rejectFirst = rej)))
      .mockResolvedValueOnce({ data: [location('l1', 'Foyer')] })
    const { reload, locations, error } = setup('e1')
    // A forced reload replaces the pending entry before the first one fails.
    await reload()
    rejectFirst(new Error('late'))
    await flush()

    expect(locations.value).toHaveLength(1)
    expect(error.value).toBeNull()
    // The successful entry survived: a new instance makes no request.
    setup('e1')
    await flush()
    expect(api.get).toHaveBeenCalledTimes(2)
  })
})
