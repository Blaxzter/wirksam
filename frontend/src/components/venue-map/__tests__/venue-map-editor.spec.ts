// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'

import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import VenueMapEditor from '@/components/venue-map/VenueMapEditor.vue'
import VenueMarkerPalette from '@/components/venue-map/VenueMarkerPalette.vue'

import type {
  LocationRead,
  VenueMarkerRead,
  VenuePlanRead,
  VenueShapeRead,
} from '@/client/types.gen'
import { type ShapeOp, applyOps } from '@/lib/venue-shape-edit'
import i18n from '@/locales/i18n'

/**
 * The map editor against a mocked API: placing, dragging, nudging and
 * removing pins, and the plan list. jsdom has no layout, so the SVG maps a
 * client point 1:1 to image units (see `clientToImage`): a click at
 * (500, 250) on the 1000×500 plan is the normalised point (0.5, 0.5).
 */

const api = {
  get: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
  patch: vi.fn(),
  delete: vi.fn(),
  getAuthToken: async () => 'tok',
}

vi.mock('@/composables/useAuthenticatedClient', () => ({
  useAuthenticatedClient: () => api,
}))

const confirmDestructive = vi.fn(async () => true)
vi.mock('@/composables/useDialog', () => ({
  useDialog: () => ({ confirmDestructive }),
}))

const fetchMock = vi.fn()

const stamp = '2026-10-01T00:00:00Z'

const foyer: LocationRead = {
  id: 'loc-foyer',
  event_id: 'e1',
  name: 'Foyer',
  created_at: stamp,
  updated_at: stamp,
}
const kitchen: LocationRead = { ...foyer, id: 'loc-kitchen', name: 'Kitchen' }

function makePlan(overrides: Partial<VenuePlanRead> = {}): VenuePlanRead {
  return {
    id: 'plan-1',
    event_id: 'e1',
    name: 'Grounds',
    sort_order: 0,
    image_etag: 'etag1',
    image_width: 1000,
    image_height: 500,
    canvas_width: 1600,
    canvas_height: 1000,
    shapes_revision: 0,
    width: 1000,
    height: 500,
    created_at: stamp,
    updated_at: stamp,
    markers: [
      { id: 'm1', plan_id: 'plan-1', kind: 'location', location_id: 'loc-foyer', x: 0.5, y: 0.5 },
    ],
    shapes: [],
    ...overrides,
  }
}

/** A plan without a picture: a 1000×500 blank canvas. */
function blankPlan(overrides: Partial<VenuePlanRead> = {}): VenuePlanRead {
  return makePlan({
    image_etag: null,
    image_width: null,
    image_height: null,
    canvas_width: 1000,
    canvas_height: 500,
    markers: [],
    ...overrides,
  })
}

function rectShape(overrides: Partial<VenueShapeRead> = {}): VenueShapeRead {
  return {
    id: 'shape-1',
    plan_id: 'plan-1',
    kind: 'rect',
    style: 'room',
    points: [
      [0.1, 0.1],
      [0.3, 0.3],
    ],
    label: 'Hall',
    label_size: 'md',
    label_x: null,
    label_y: null,
    stroke_width: null,
    location_id: null,
    sort_order: 0,
    ...overrides,
  }
}

/** The server side of the batch endpoint: apply the ops for real. */
let serverShapes: VenueShapeRead[] = []
let serverRevision = 0

function batchCalls() {
  return api.post.mock.calls
    .map((c) => c[0] as { url: string; body: { ops: ShapeOp[]; expected_revision: number } })
    .filter((c) => c.url.endsWith('/shapes/batch'))
}

let plans: VenuePlanRead[]

beforeEach(() => {
  setActivePinia(createPinia())
  i18n.global.locale.value = 'en'
  Element.prototype.scrollIntoView = () => {}
  plans = [makePlan()]
  serverShapes = []
  serverRevision = 0
  api.post.mockImplementation(
    async ({ url, body }: { url: string; body: { ops: ShapeOp[]; name?: string } }) => {
      if (url.endsWith('/shapes/batch')) {
        serverShapes = applyOps(serverShapes, body.ops, 'plan-1')
        serverRevision += 1
        return { data: { plan_id: 'plan-1', revision: serverRevision, shapes: serverShapes } }
      }
      if (url.endsWith('/venue-plans')) {
        return { data: blankPlan({ id: 'plan-new', name: body.name! }) }
      }
      throw new Error(`unexpected POST ${url}`)
    },
  )
  api.get.mockImplementation(async ({ url }: { url: string }) => {
    if (url.endsWith('/venue-map')) {
      return {
        data: { event_id: 'e1', on: '2026-10-12', plans, locations: [], my_location_ids: [] },
      }
    }
    if (url.endsWith('/locations')) return { data: [foyer, kitchen] }
    throw new Error(`unexpected GET ${url}`)
  })
  fetchMock.mockResolvedValue({ ok: true, status: 200, blob: async () => new Blob(['x']) })
  vi.stubGlobal('fetch', fetchMock)
  vi.stubGlobal(
    'URL',
    Object.assign(URL, { createObjectURL: () => 'blob:plan', revokeObjectURL: () => {} }),
  )
})

const mounted: { unmount: () => void }[] = []

afterEach(() => {
  // Unmount for real: a still-mounted editor keeps its document key listeners.
  for (const w of mounted.splice(0)) w.unmount()
  vi.unstubAllGlobals()
  vi.clearAllMocks()
  document.body.innerHTML = ''
})

async function mountEditor() {
  const wrapper = mount(VenueMapEditor, {
    props: { eventId: 'e1' },
    global: { plugins: [i18n] },
    attachTo: document.body,
  })
  mounted.push(wrapper)
  await flushPromises()
  return wrapper
}

function pointer(el: Element, type: string, x: number, y: number) {
  el.dispatchEvent(
    new PointerEvent(type, {
      bubbles: true,
      cancelable: true,
      clientX: x,
      clientY: y,
      pointerId: 1,
      pointerType: 'mouse',
      button: 0,
    }),
  )
}

describe('VenueMapEditor', () => {
  it('shows the empty state without plans', async () => {
    plans = []
    const wrapper = await mountEditor()
    expect(wrapper.find('[data-testid="map-editor-empty"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="editor-canvas"]').exists()).toBe(false)
  })

  it('opens a plan without a picture onto the canvas, ready to draw or add a picture', async () => {
    plans = [blankPlan()]
    const wrapper = await mountEditor()
    expect(wrapper.find('[data-testid="editor-canvas"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="editor-canvas-bounds"]').attributes('width')).toBe('1000')
    expect(wrapper.find('[data-testid="draw-hint"]').text()).toContain('Draw your venue')
    expect(wrapper.find('[data-testid="plan-upload-replace"]').text()).toContain(
      'Put a picture underneath',
    )
    // No image to load.
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('offers only the locations that are not on the plan yet', async () => {
    const wrapper = await mountEditor()
    expect(wrapper.find('[data-testid="palette-location-loc-foyer"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="palette-location-loc-kitchen"]').exists()).toBe(true)
    expect(wrapper.findAll('[data-testid^="palette-kind-"]')).toHaveLength(6)
  })

  it('places a location pin where the plan is clicked', async () => {
    const created: VenueMarkerRead = {
      id: 'm2',
      plan_id: 'plan-1',
      kind: 'location',
      location_id: 'loc-kitchen',
      x: 0.5,
      y: 0.5,
    }
    api.post.mockResolvedValue({ data: created })
    const wrapper = await mountEditor()

    await wrapper.find('[data-testid="palette-location-loc-kitchen"]').trigger('click')
    expect(wrapper.find('[data-testid="placement-banner"]').text()).toContain('Kitchen')

    await wrapper.find('[data-testid="editor-canvas"]').trigger('click', {
      clientX: 500,
      clientY: 250,
    })
    await flushPromises()

    expect(api.post).toHaveBeenCalledWith({
      url: '/venue-plans/plan-1/markers',
      body: { kind: 'location', location_id: 'loc-kitchen', x: 0.5, y: 0.5 },
    })
    expect(wrapper.find('[data-testid="placement-banner"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="map-marker-loc-kitchen"]').exists()).toBe(true)
    // The new pin is selected, and the location left the palette.
    expect(wrapper.find('[data-testid="marker-panel"]').text()).toContain('Kitchen')
    expect(wrapper.find('[data-testid="palette-location-loc-kitchen"]').exists()).toBe(false)
  })

  it('places a generic pin in the middle of the view from the keyboard', async () => {
    api.post.mockImplementation(async ({ body }: { body: Record<string, unknown> }) => ({
      data: { id: 'm3', plan_id: 'plan-1', label: null, ...body },
    }))
    const wrapper = await mountEditor()
    await wrapper.find('[data-testid="palette-kind-first_aid"]').trigger('click')
    await wrapper.find('[data-testid="placement-centre"]').trigger('click')
    await flushPromises()
    expect(api.post).toHaveBeenCalledWith({
      url: '/venue-plans/plan-1/markers',
      body: { kind: 'first_aid', location_id: null, x: 0.5, y: 0.5 },
    })
    // Generic pins can be labelled.
    expect(wrapper.find('[data-testid="marker-label"]').exists()).toBe(true)
  })

  it('cancels placement with Escape', async () => {
    const wrapper = await mountEditor()
    await wrapper.find('[data-testid="palette-kind-parking"]').trigger('click')
    expect(wrapper.find('[data-testid="placement-banner"]').exists()).toBe(true)
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await flushPromises()
    expect(wrapper.find('[data-testid="placement-banner"]').exists()).toBe(false)
  })

  it('drags a pin and saves where it was dropped', async () => {
    api.patch.mockImplementation(async ({ body }: { body: Record<string, unknown> }) => ({
      data: { ...plans[0]!.markers![0]!, ...body },
    }))
    const wrapper = await mountEditor()
    const marker = wrapper.find('[data-testid="map-marker-loc-foyer"]').element

    pointer(marker, 'pointerdown', 500, 250)
    pointer(marker, 'pointermove', 600, 300)
    pointer(marker, 'pointerup', 600, 300)
    await flushPromises()

    expect(api.patch).toHaveBeenCalledWith({
      url: '/venue-markers/m1',
      body: { x: 0.6, y: 0.6 },
    })
  })

  it('puts a dragged pin back when saving fails', async () => {
    api.patch.mockRejectedValue(new Error('nope'))
    const wrapper = await mountEditor()
    const marker = wrapper.find('[data-testid="map-marker-loc-foyer"]')

    pointer(marker.element, 'pointerdown', 500, 250)
    pointer(marker.element, 'pointermove', 700, 250)
    pointer(marker.element, 'pointerup', 700, 250)
    await flushPromises()

    expect(marker.attributes('transform')).toContain('translate(500 250)')
  })

  it('does not move a pin on a plain tap, but selects it', async () => {
    const wrapper = await mountEditor()
    const marker = wrapper.find('[data-testid="map-marker-loc-foyer"]').element
    pointer(marker, 'pointerdown', 500, 250)
    pointer(marker, 'pointerup', 501, 250)
    await flushPromises()
    expect(api.patch).not.toHaveBeenCalled()
    expect(wrapper.find('[data-testid="marker-panel"]').text()).toContain('Foyer')
  })

  it('nudges the focused pin with the arrow keys in one save', async () => {
    vi.useFakeTimers()
    api.patch.mockImplementation(async ({ body }: { body: Record<string, unknown> }) => ({
      data: { ...plans[0]!.markers![0]!, ...body },
    }))
    const wrapper = await mountEditor()
    const marker = wrapper.find('[data-testid="map-marker-loc-foyer"]')
    await marker.trigger('keydown', { key: 'ArrowRight' })
    await marker.trigger('keydown', { key: 'ArrowDown', shiftKey: true })
    expect(api.patch).not.toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(500)
    vi.useRealTimers()

    expect(api.patch).toHaveBeenCalledTimes(1)
    const body = api.patch.mock.calls[0]![0].body
    expect(body.x).toBeCloseTo(0.505)
    expect(body.y).toBeCloseTo(0.52)
  })

  it('removes the focused pin with Delete after confirming', async () => {
    api.delete.mockResolvedValue(undefined)
    const wrapper = await mountEditor()
    await wrapper.find('[data-testid="map-marker-loc-foyer"]').trigger('keydown', { key: 'Delete' })
    await flushPromises()
    expect(confirmDestructive).toHaveBeenCalled()
    expect(api.delete).toHaveBeenCalledWith({ url: '/venue-markers/m1' })
    expect(wrapper.find('[data-testid="map-marker-loc-foyer"]').exists()).toBe(false)
  })

  it('labels a generic pin', async () => {
    plans = [
      makePlan({
        markers: [{ id: 'g1', plan_id: 'plan-1', kind: 'entrance', label: null, x: 0.2, y: 0.2 }],
      }),
    ]
    api.patch.mockResolvedValue({
      data: { id: 'g1', plan_id: 'plan-1', kind: 'entrance', label: 'North gate', x: 0.2, y: 0.2 },
    })
    const wrapper = await mountEditor()
    await wrapper.find('[data-testid="map-marker-g1"]').trigger('focus')
    const input = wrapper.find('[data-testid="marker-label"]')
    await input.setValue('  North gate ')
    await input.trigger('change')
    await flushPromises()
    expect(api.patch).toHaveBeenCalledWith({
      url: '/venue-markers/g1',
      body: { label: 'North gate' },
    })
  })
})

function q<T extends Element = HTMLElement>(testid: string): T {
  const el = document.querySelector<T>(`[data-testid="${testid}"]`)
  if (!el) throw new Error(`missing ${testid}`)
  return el
}

async function typeInto(testid: string, value: string) {
  const input = q<HTMLInputElement>(testid)
  input.value = value
  input.dispatchEvent(new Event('input', { bubbles: true }))
  await flushPromises()
}

describe('VenueMapEditor: creating plans', () => {
  it('creates a blank plan in the chosen aspect and opens it with the rectangle tool', async () => {
    plans = []
    const wrapper = await mountEditor()
    await wrapper.find('[data-testid="plan-add"]').trigger('click')
    await flushPromises()
    await typeInto('plan-name-input', '  Halle ')
    q('plan-aspect-portrait').querySelector('input')!.click()
    await flushPromises()
    q('plan-name-save').click()
    await flushPromises()

    expect(api.post).toHaveBeenCalledWith({
      url: '/events/e1/venue-plans',
      body: { name: 'Halle', canvas: 'portrait' },
    })
    expect(q('tool-rect').getAttribute('aria-pressed')).toBe('true')
    expect(wrapper.emitted('changed')).toBeTruthy()
  })

  it('offers the picture upload big after "Use a picture"', async () => {
    plans = []
    const wrapper = await mountEditor()
    await wrapper.find('[data-testid="plan-add"]').trigger('click')
    await flushPromises()
    await typeInto('plan-name-input', 'Gelände')
    q('plan-create-picture').querySelector('input')!.click()
    await flushPromises()
    // Pictures have no aspect to choose.
    expect(document.querySelector('[data-testid="plan-aspect-square"]')).toBeNull()
    q('plan-name-save').click()
    await flushPromises()
    expect(
      wrapper.find('[data-testid="picture-card"] [data-testid="plan-upload-zone"]').exists(),
    ).toBe(true)
    expect(q('tool-select').getAttribute('aria-pressed')).toBe('true')
  })

  it('cannot pick a picture in the demo, but can draw', async () => {
    plans = [blankPlan()]
    const wrapper = mount(VenueMapEditor, {
      props: { eventId: 'e1', sandbox: true },
      global: { plugins: [i18n] },
      attachTo: document.body,
    })
    mounted.push(wrapper)
    await flushPromises()
    expect(wrapper.find('[data-testid="plan-upload-sandbox"]').text()).toContain('Not in the demo')
    await wrapper.find('[data-testid="plan-add"]').trigger('click')
    await flushPromises()
    expect(q('plan-create-picture').querySelector('input')!.disabled).toBe(true)
    expect(wrapper.find('[data-testid="draw-toolbar"]').exists()).toBe(true)
  })
})

describe('VenueMapEditor: drawing', () => {
  it('draws a rectangle by dragging and saves it as one batch', async () => {
    plans = [blankPlan()]
    const wrapper = await mountEditor()
    await wrapper.find('[data-testid="tool-rect"]').trigger('click')
    const svg = wrapper.find('[data-testid="editor-canvas"]').element
    pointer(svg, 'pointerdown', 100, 100)
    pointer(svg, 'pointermove', 200, 180)
    await flushPromises()
    expect(wrapper.find('[data-testid="draw-rubber-band"]').exists()).toBe(true)
    pointer(svg, 'pointermove', 300, 250)
    pointer(svg, 'pointerup', 300, 250)
    await flushPromises()

    const [call] = batchCalls()
    expect(call!.url).toBe('/venue-plans/plan-1/shapes/batch')
    expect(call!.body.expected_revision).toBe(0)
    expect(call!.body.ops[0]).toMatchObject({
      op: 'create',
      shape: {
        kind: 'rect',
        style: 'room',
        points: [
          [0.1, 0.2],
          [0.3, 0.5],
        ],
      },
    })
    const id = (call!.body.ops[0] as { shape: { id: string } }).shape.id
    expect(wrapper.find(`[data-testid="venue-shape-${id}"]`).exists()).toBe(true)
    // Selected, with the inspector open.
    expect(wrapper.find('[data-testid="shape-inspector"]').exists()).toBe(true)
    expect(wrapper.emitted('changed')).toBeTruthy()
    expect(wrapper.find('[data-testid="draw-save-state"]').text()).toContain('All changes saved')

    // Undo removes it again, by the same id.
    await wrapper.find('[data-testid="tool-undo"]').trigger('click')
    await flushPromises()
    expect(batchCalls()[1]!.body).toEqual({ ops: [{ op: 'delete', id }], expected_revision: 1 })
    expect(wrapper.find(`[data-testid="venue-shape-${id}"]`).exists()).toBe(false)
    // …and Ctrl+Shift+Z brings it back.
    document.dispatchEvent(
      new KeyboardEvent('keydown', { key: 'Z', ctrlKey: true, shiftKey: true }),
    )
    await flushPromises()
    expect(batchCalls()[2]!.body.ops[0]).toMatchObject({ op: 'create', shape: { id } })
  })

  it('draws a polygon by taps and the "Close shape" button', async () => {
    plans = [blankPlan()]
    const wrapper = await mountEditor()
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'p' }))
    await flushPromises()
    const svg = wrapper.find('[data-testid="editor-canvas"]').element
    for (const [x, y] of [
      [100, 100],
      [300, 100],
      [300, 300],
    ]) {
      pointer(svg, 'pointerdown', x!, y!)
      pointer(svg, 'pointerup', x!, y!)
    }
    await flushPromises()
    expect(wrapper.find('[data-testid="draw-bar"]').exists()).toBe(true)
    await wrapper.find('[data-testid="draw-close"]').trigger('click')
    await flushPromises()
    expect(batchCalls()[0]!.body.ops[0]).toMatchObject({
      shape: {
        kind: 'polygon',
        style: 'area',
        points: [
          [0.1, 0.2],
          [0.3, 0.2],
          [0.3, 0.6],
        ],
      },
    })
  })

  it('selects a shape by pressing it, links it to a place and deletes it with Delete', async () => {
    plans = [blankPlan({ shapes: [rectShape()], shapes_revision: 4 })]
    serverShapes = [rectShape()]
    serverRevision = 4
    const wrapper = await mountEditor()
    const shape = wrapper.find('[data-testid="venue-shape-shape-1"] .vs-body').element
    pointer(shape, 'pointerdown', 200, 100)
    pointer(shape, 'pointerup', 200, 100)
    await flushPromises()
    expect(wrapper.find('[data-testid="shape-inspector"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="handle-resize-se"]').exists()).toBe(true)

    await wrapper.find('[data-testid="shape-link"]').setValue('loc-kitchen')
    await flushPromises()
    expect(batchCalls()[0]!.body).toEqual({
      ops: [{ op: 'update', id: 'shape-1', patch: { location_id: 'loc-kitchen' } }],
      expected_revision: 4,
    })

    await wrapper.find('[data-testid="style-stage"]').trigger('click')
    await flushPromises()
    expect(batchCalls()[1]!.body.ops[0]).toEqual({
      op: 'update',
      id: 'shape-1',
      patch: { style: 'stage' },
    })

    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Delete' }))
    await flushPromises()
    expect(batchCalls()[2]!.body.ops).toEqual([{ op: 'delete', id: 'shape-1' }])
    expect(wrapper.find('[data-testid="shape-inspector"]').exists()).toBe(false)
  })

  it('keeps its shortcuts to itself: not behind a dialog, not from the rest of the page', async () => {
    plans = [blankPlan({ shapes: [rectShape()], shapes_revision: 4 })]
    serverShapes = [rectShape()]
    serverRevision = 4
    const wrapper = await mountEditor()
    const shape = wrapper.find('[data-testid="venue-shape-shape-1"] .vs-body').element
    pointer(shape, 'pointerdown', 200, 100)
    pointer(shape, 'pointerup', 200, 100)
    await flushPromises()

    const outside = document.createElement('button')
    document.body.appendChild(outside)
    const dialog = document.createElement('div')
    dialog.setAttribute('role', 'alertdialog')
    const inDialog = document.createElement('button')
    dialog.appendChild(inDialog)
    try {
      outside.dispatchEvent(new KeyboardEvent('keydown', { key: 'Delete', bubbles: true }))
      outside.dispatchEvent(new KeyboardEvent('keydown', { key: 'r', bubbles: true }))
      document.body.appendChild(dialog)
      inDialog.dispatchEvent(new KeyboardEvent('keydown', { key: 'Backspace', bubbles: true }))
      document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Delete' }))
      await flushPromises()
      expect(batchCalls()).toHaveLength(0)
      expect(wrapper.find('[data-testid="tool-select"]').attributes('aria-pressed')).toBe('true')

      dialog.remove()
      document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Delete' }))
      await flushPromises()
      expect(batchCalls()[0]!.body.ops).toEqual([{ op: 'delete', id: 'shape-1' }])
    } finally {
      outside.remove()
      dialog.remove()
    }
  })

  it('places a text and creates it once it has words', async () => {
    plans = [blankPlan()]
    const wrapper = await mountEditor()
    await wrapper.find('[data-testid="tool-label"]').trigger('click')
    const svg = wrapper.find('[data-testid="editor-canvas"]').element
    pointer(svg, 'pointerdown', 500, 250)
    pointer(svg, 'pointerup', 500, 250)
    await flushPromises()
    const input = wrapper.find('[data-testid="label-draft-input"]')
    // Nothing was selected before, so the field only just mounted: it still gets focus.
    expect(document.activeElement).toBe(input.element)
    await input.setValue('Bühne')
    await input.trigger('keydown', { key: 'Enter' })
    await flushPromises()
    expect(batchCalls()[0]!.body.ops[0]).toMatchObject({
      shape: { kind: 'label', label: 'Bühne', points: [[0.5, 0.5]] },
    })
  })

  it('rolls a failed save back and says why', async () => {
    plans = [blankPlan({ shapes: [rectShape()] })]
    api.post.mockRejectedValueOnce(
      Object.assign(new Error('fail'), {
        isAxiosError: true,
        response: { status: 422, data: { status: 422, title: 'x', code: 'venue_shape.too_small' } },
      }),
    )
    const wrapper = await mountEditor()
    const shape = wrapper.find('[data-testid="venue-shape-shape-1"] .vs-body').element
    pointer(shape, 'pointerdown', 200, 100)
    pointer(shape, 'pointerup', 200, 100)
    await flushPromises()
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Delete' }))
    await flushPromises()
    expect(wrapper.find('[data-testid="venue-shape-shape-1"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="tool-undo"]').attributes('disabled')).toBeDefined()
  })

  it('reloads the plan when someone else saved in between', async () => {
    plans = [blankPlan({ shapes: [rectShape()] })]
    api.post.mockRejectedValueOnce(
      Object.assign(new Error('fail'), {
        isAxiosError: true,
        response: {
          status: 409,
          data: { status: 409, title: 'x', code: 'venue_shape.revision_conflict' },
        },
      }),
    )
    const wrapper = await mountEditor()
    const loads = api.get.mock.calls.filter((c) => String(c[0].url).endsWith('/venue-map')).length
    const shape = wrapper.find('[data-testid="venue-shape-shape-1"] .vs-body').element
    pointer(shape, 'pointerdown', 200, 100)
    pointer(shape, 'pointerup', 200, 100)
    await flushPromises()
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Delete' }))
    await flushPromises()
    expect(api.get.mock.calls.filter((c) => String(c[0].url).endsWith('/venue-map')).length).toBe(
      loads + 1,
    )
    expect(wrapper.find('[data-testid="venue-shape-shape-1"]').exists()).toBe(true)
  })

  it('removes the picture after confirming, keeping the drawing', async () => {
    plans = [makePlan({ shapes: [rectShape()] })]
    api.delete.mockResolvedValue({ data: blankPlan({ shapes: [rectShape()] }) })
    const wrapper = await mountEditor()
    expect(wrapper.find('[data-testid="picture-stretch-hint"]').exists()).toBe(true)
    await wrapper.find('[data-testid="picture-remove"]').trigger('click')
    await flushPromises()
    expect(confirmDestructive).toHaveBeenCalled()
    expect(api.delete).toHaveBeenCalledWith({ url: '/venue-plans/plan-1/image' })
    expect(wrapper.find('[data-testid="picture-remove"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="venue-shape-shape-1"]').exists()).toBe(true)
  })
})

describe('VenueMarkerPalette', () => {
  it('says so when there are no locations, and marks the active item', async () => {
    const wrapper = mount(VenueMarkerPalette, {
      props: { locations: [], placedLocationIds: [], active: 'kind:toilets' },
      global: { plugins: [i18n] },
    })
    expect(wrapper.text()).toContain('No locations yet')
    expect(wrapper.find('[data-testid="palette-kind-toilets"]').attributes('aria-pressed')).toBe(
      'true',
    )
    await wrapper.find('[data-testid="palette-kind-kitchen"]').trigger('click')
    expect(wrapper.emitted('pick-kind')).toEqual([['kitchen']])
  })

  it('says when every location is placed', () => {
    const wrapper = mount(VenueMarkerPalette, {
      props: { locations: [foyer], placedLocationIds: ['loc-foyer'] },
      global: { plugins: [i18n] },
    })
    expect(wrapper.text()).toContain('All locations are on this map.')
  })
})
