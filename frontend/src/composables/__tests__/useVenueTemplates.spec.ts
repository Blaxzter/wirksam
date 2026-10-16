import { effectScope, nextTick, ref } from 'vue'

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  forgetTemplateShapes,
  useTemplateShapes,
  useVenueTemplates,
} from '@/composables/useVenueTemplates'

import type { VenueTemplateRead, VenueTemplateShape } from '@/client/types.gen'

const api = vi.hoisted(() => ({ get: vi.fn(), patch: vi.fn(), delete: vi.fn() }))

vi.mock('@/composables/useAuthenticatedClient', () => ({
  useAuthenticatedClient: () => api,
}))

const stamp = '2026-10-16T00:00:00Z'

function template(id: string, overrides: Partial<VenueTemplateRead> = {}): VenueTemplateRead {
  return {
    id,
    name: `Template ${id}`,
    canvas_width: 1600,
    canvas_height: 1000,
    image_etag: null,
    shape_count: 1,
    created_at: stamp,
    updated_at: stamp,
    width: 1600,
    height: 1000,
    ...overrides,
  }
}

const shape: VenueTemplateShape = {
  id: 's1',
  kind: 'rect',
  style: 'room',
  points: [
    [0, 0],
    [0.5, 0.5],
  ],
}

/** Let the queued promise callbacks run. */
const flush = () => new Promise((r) => setTimeout(r, 0))

const scopes: ReturnType<typeof effectScope>[] = []
function inScope<T>(fn: () => T): T {
  const scope = effectScope()
  scopes.push(scope)
  return scope.run(fn)!
}

beforeEach(() => {
  vi.resetAllMocks()
  forgetTemplateShapes()
})

afterEach(() => {
  scopes.splice(0).forEach((s) => s.stop())
})

describe('useVenueTemplates', () => {
  it('loads my templates', async () => {
    api.get.mockResolvedValue({ data: [template('t1'), template('t2')] })
    const { templates, loading, loadError, load } = useVenueTemplates()
    const pending = load()
    expect(loading.value).toBe(true)
    await pending
    expect(api.get).toHaveBeenCalledWith({ url: '/venue-templates' })
    expect(templates.value.map((t) => t.id)).toEqual(['t1', 't2'])
    expect(loading.value).toBe(false)
    expect(loadError.value).toBe(false)
  })

  it('reports a failed load instead of an empty list', async () => {
    api.get.mockRejectedValue(new Error('offline'))
    const { templates, loadError, load } = useVenueTemplates()
    await load()
    expect(templates.value).toEqual([])
    expect(loadError.value).toBe(true)
  })

  it('keeps the newest list when an older answer arrives late', async () => {
    let first!: (v: unknown) => void
    api.get
      .mockImplementationOnce(() => new Promise((r) => (first = r)))
      .mockResolvedValueOnce({ data: [template('new')] })
    const { templates, loading, load } = useVenueTemplates()
    const slow = load()
    await load()
    first({ data: [template('old')] })
    await slow
    expect(templates.value.map((t) => t.id)).toEqual(['new'])
    expect(loading.value).toBe(false)
  })

  it('ignores a failure of an outdated load', async () => {
    let fail!: (e: unknown) => void
    api.get
      .mockImplementationOnce(() => new Promise((_r, rej) => (fail = rej)))
      .mockResolvedValueOnce({ data: [template('t1')] })
    const { templates, loadError, load } = useVenueTemplates()
    const slow = load()
    await load()
    fail(new Error('late'))
    await slow
    expect(templates.value).toHaveLength(1)
    expect(loadError.value).toBe(false)
  })

  it('renames a template in place', async () => {
    api.get.mockResolvedValue({ data: [template('t1'), template('t2')] })
    api.patch.mockResolvedValue({ data: template('t2', { name: 'Halle' }) })
    const { templates, load, rename } = useVenueTemplates()
    await load()
    const res = await rename('t2', 'Halle')
    expect(api.patch).toHaveBeenCalledWith({ url: '/venue-templates/t2', body: { name: 'Halle' } })
    expect(res.name).toBe('Halle')
    expect(templates.value.map((t) => t.name)).toEqual(['Template t1', 'Halle'])
    // Renaming one that is not in the list (yet) changes nothing locally.
    api.patch.mockResolvedValue({ data: template('t9', { name: 'X' }) })
    await rename('t9', 'X')
    expect(templates.value).toHaveLength(2)
  })

  it('deletes a template and forgets its drawing', async () => {
    api.get.mockImplementation(async ({ url }: { url: string }) =>
      url === '/venue-templates'
        ? { data: [template('t1')] }
        : { data: { ...template('t1'), shapes: [shape] } },
    )
    const list = useVenueTemplates()
    await list.load()
    const thumb = inScope(() => useTemplateShapes('t1'))
    await flush()
    expect(thumb.shapes.value).toHaveLength(1)

    api.delete.mockResolvedValue({})
    await list.remove('t1')
    expect(api.delete).toHaveBeenCalledWith({ url: '/venue-templates/t1' })
    expect(list.templates.value).toEqual([])

    // The cache entry is gone: the next look asks the server again.
    inScope(() => useTemplateShapes('t1'))
    await flush()
    expect(api.get.mock.calls.filter((c) => c[0].url === '/venue-templates/t1')).toHaveLength(2)
  })
})

describe('useTemplateShapes', () => {
  it('loads a template’s drawing once and shares it', async () => {
    api.get.mockResolvedValue({ data: { ...template('t1'), shapes: [shape] } })
    const a = inScope(() => useTemplateShapes('t1'))
    const b = inScope(() => useTemplateShapes('t1'))
    expect(a.loading.value).toBe(true)
    await flush()
    expect(a.shapes.value).toEqual([shape])
    expect(b.shapes.value).toEqual([shape])
    expect(a.loading.value).toBe(false)
    expect(api.get).toHaveBeenCalledTimes(1)
    expect(api.get).toHaveBeenCalledWith({ url: '/venue-templates/t1' })
  })

  it('treats a template without a shapes list as empty', async () => {
    api.get.mockResolvedValue({ data: template('t1') })
    const { shapes } = inScope(() => useTemplateShapes('t1'))
    await flush()
    expect(shapes.value).toEqual([])
  })

  it('skips the request when disabled or without an id', async () => {
    const id = ref<string | null>(null)
    const { shapes, loading } = inScope(() => useTemplateShapes(id, false))
    await flush()
    expect(api.get).not.toHaveBeenCalled()
    expect(shapes.value).toEqual([])
    expect(loading.value).toBe(false)
  })

  it('reports a failure and retries on the next look', async () => {
    api.get.mockRejectedValueOnce(new Error('offline'))
    const { shapes, error } = inScope(() => useTemplateShapes('t1'))
    await flush()
    expect(shapes.value).toEqual([])
    expect(error.value).toBeInstanceOf(Error)

    api.get.mockResolvedValue({ data: { ...template('t1'), shapes: [shape] } })
    const again = inScope(() => useTemplateShapes('t1'))
    await flush()
    expect(again.shapes.value).toEqual([shape])
  })

  it('shows the latest template when the id changes mid-load', async () => {
    let first!: (v: unknown) => void
    api.get
      .mockImplementationOnce(() => new Promise((r) => (first = r)))
      .mockResolvedValueOnce({ data: { ...template('t2'), shapes: [{ ...shape, id: 's2' }] } })
    const id = ref('t1')
    const { shapes } = inScope(() => useTemplateShapes(id))
    id.value = 't2'
    await nextTick()
    await flush()
    first({ data: { ...template('t1'), shapes: [shape] } })
    await flush()
    expect(shapes.value.map((s) => s.id)).toEqual(['s2'])
  })

  it('ignores a late failure for a template no longer shown', async () => {
    let fail!: (e: unknown) => void
    api.get
      .mockImplementationOnce(() => new Promise((_r, rej) => (fail = rej)))
      .mockResolvedValueOnce({ data: { ...template('t2'), shapes: [shape] } })
    const id = ref('t1')
    const { shapes, error } = inScope(() => useTemplateShapes(id))
    id.value = 't2'
    await nextTick()
    await flush()
    fail(new Error('late'))
    await flush()
    expect(shapes.value).toHaveLength(1)
    expect(error.value).toBeNull()
  })

  it('forgets one template or all of them', async () => {
    api.get.mockResolvedValue({ data: { ...template('t1'), shapes: [shape] } })
    inScope(() => useTemplateShapes('t1'))
    await flush()
    forgetTemplateShapes('t1')
    inScope(() => useTemplateShapes('t1'))
    await flush()
    forgetTemplateShapes()
    inScope(() => useTemplateShapes('t1'))
    await flush()
    expect(api.get).toHaveBeenCalledTimes(3)
  })
})
