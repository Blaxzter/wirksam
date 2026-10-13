import { effectScope, nextTick, ref } from 'vue'

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { invalidatePlanShapes, usePlanShapes } from '@/composables/usePlanShapes'

import type { VenueShapeRead } from '@/client/types.gen'

const api = vi.hoisted(() => ({ get: vi.fn() }))

vi.mock('@/composables/useAuthenticatedClient', () => ({
  useAuthenticatedClient: () => ({ get: api.get }),
}))

function shape(id: string, planId = 'p1'): VenueShapeRead {
  return {
    id,
    plan_id: planId,
    kind: 'rect',
    style: 'room',
    points: [
      [0, 0],
      [0.5, 0.5],
    ],
    label_size: 'md',
    sort_order: 0,
  }
}

function reply(planId: string, revision: number, shapes: VenueShapeRead[]) {
  return { data: { plan_id: planId, revision, shapes } }
}

/** Let the queued promise callbacks run. */
const flush = () => new Promise((r) => setTimeout(r, 0))

const scopes: ReturnType<typeof effectScope>[] = []
function setup(...args: Parameters<typeof usePlanShapes>) {
  const scope = effectScope()
  scopes.push(scope)
  return scope.run(() => usePlanShapes(...args))!
}

beforeEach(() => {
  vi.resetAllMocks()
  // The cache is module state; start every test from nothing.
  invalidatePlanShapes()
})

afterEach(() => {
  scopes.splice(0).forEach((s) => s.stop())
})

describe('usePlanShapes', () => {
  it('loads a plan’s shapes', async () => {
    api.get.mockResolvedValue(reply('p1', 3, [shape('s1')]))
    const { shapes, loading, ready } = setup('p1', 3)

    expect(loading.value).toBe(true)
    await ready()

    expect(api.get).toHaveBeenCalledWith({ url: '/venue-plans/p1/shapes' })
    expect(shapes.value.map((s) => s.id)).toEqual(['s1'])
    expect(loading.value).toBe(false)
  })

  it('shares one request per plan and revision, and asks again for a new revision', async () => {
    api.get.mockResolvedValue(reply('p1', 3, [shape('s1')]))
    const revision = ref(3)
    const a = setup('p1', revision)
    const b = setup('p1', 3)
    await flush()
    expect(api.get).toHaveBeenCalledTimes(1)
    expect(b.shapes.value).toHaveLength(1)

    api.get.mockResolvedValue(reply('p1', 4, [shape('s1'), shape('s2')]))
    revision.value = 4
    await nextTick()
    await a.ready()
    expect(api.get).toHaveBeenCalledTimes(2)
    expect(a.shapes.value).toHaveLength(2)
  })

  it('reloads after invalidatePlanShapes, for that plan only', async () => {
    api.get.mockImplementation(({ url }: { url: string }) =>
      Promise.resolve(reply(url.includes('p2') ? 'p2' : 'p1', 1, [shape('s1')])),
    )
    setup('p1', 1)
    setup('p2', 1)
    await flush()
    expect(api.get).toHaveBeenCalledTimes(2)

    invalidatePlanShapes('p1')
    await flush()
    // Both instances re-run, but only p1 missed the cache.
    expect(api.get).toHaveBeenCalledTimes(3)
    expect(api.get).toHaveBeenLastCalledWith({ url: '/venue-plans/p1/shapes' })
  })

  it('asks for nothing without a plan or when disabled', async () => {
    const enabled = ref(false)
    const none = setup(null, 3)
    const off = setup('p1', 3, enabled)
    await flush()
    expect(api.get).not.toHaveBeenCalled()
    for (const s of [none, off]) {
      expect(s.shapes.value).toEqual([])
      expect(s.loading.value).toBe(false)
      await expect(s.ready()).resolves.toBeUndefined()
    }

    api.get.mockResolvedValue(reply('p1', 3, [shape('s1')]))
    enabled.value = true
    await nextTick()
    await off.ready()
    expect(off.shapes.value).toHaveLength(1)
  })

  it('fetches at revision 0 too: a cloned plan holds shapes it never saved', async () => {
    api.get.mockResolvedValue(reply('p1', 0, [shape('s1')]))
    const cloned = setup('p1', 0)
    await cloned.ready()
    expect(api.get).toHaveBeenCalledWith({ url: '/venue-plans/p1/shapes' })
    expect(cloned.shapes.value).toHaveLength(1)
  })

  it('reports an error, and the next caller retries', async () => {
    const failure = new Error('nope')
    api.get.mockRejectedValueOnce(failure)
    const a = setup('p1', 2)
    await a.ready()
    expect(a.error.value).toBe(failure)
    expect(a.shapes.value).toEqual([])
    expect(a.loading.value).toBe(false)

    api.get.mockResolvedValue(reply('p1', 2, [shape('s1')]))
    const b = setup('p1', 2)
    await b.ready()
    expect(b.error.value).toBeNull()
    expect(b.shapes.value).toHaveLength(1)
  })

  it('ignores a response for a plan that is no longer shown', async () => {
    let resolveOld: (v: unknown) => void = () => {}
    api.get.mockImplementationOnce(() => new Promise((r) => (resolveOld = r)))
    let rejectOld: (e: unknown) => void = () => {}
    api.get.mockImplementationOnce(() => new Promise((_r, j) => (rejectOld = j)))
    api.get.mockResolvedValue(reply('p3', 1, [shape('new', 'p3')]))

    const planId = ref('p1')
    const s = setup(planId, 1)
    planId.value = 'p2'
    await nextTick()
    planId.value = 'p3'
    await nextTick()
    await s.ready()

    resolveOld(reply('p1', 1, [shape('old')]))
    rejectOld(new Error('late'))
    await flush()
    expect(s.shapes.value.map((x) => x.id)).toEqual(['new'])
    expect(s.error.value).toBeNull()
    expect(s.loading.value).toBe(false)
  })
})
