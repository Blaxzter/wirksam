// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'

import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, onTestFinished, vi } from 'vitest'

import DropdownMenuContent from '@/components/ui/dropdown-menu/DropdownMenuContent.vue'

import VenueMapEditor from '@/components/venue-map/VenueMapEditor.vue'
import VenueMarkerPalette from '@/components/venue-map/VenueMarkerPalette.vue'
import VenueDecorPalette from '@/components/venue-map/editor/VenueDecorPalette.vue'

import type {
  LocationRead,
  VenueMarkerRead,
  VenuePlanRead,
  VenueShapeRead,
  VenueTemplateSummary,
} from '@/client/types.gen'
import { type ShapeOp, applyOps } from '@/lib/venue-shape-edit'
import i18n from '@/locales/i18n'

/**
 * The map editor against a mocked API: placing, dragging, nudging and
 * removing pins, and the plan list. jsdom has no layout, so the SVG maps a
 * client point 1:1 to image units (see `clientToImage`): a click at
 * (500, 250) on the 1000×500 plan is the normalised point (0.5, 0.5).
 */

// The buttons' tooltips (reka-ui) measure themselves when they open on focus
// or hover; jsdom has no ResizeObserver.
globalThis.ResizeObserver ??= class {
  observe() {}
  unobserve() {}
  disconnect() {}
}

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

const templateSummary: VenueTemplateSummary = {
  id: 'tpl-1',
  name: 'Festwiese',
  canvas_width: 1000,
  canvas_height: 500,
  image_etag: null,
  shape_count: 0,
  created_at: stamp,
  updated_at: stamp,
  width: 1000,
  height: 500,
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
      if (url.endsWith('/save-as-template')) {
        return { data: { ...templateSummary, name: body.name!, shapes: [] } }
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
    if (url === '/venue-templates') return { data: [templateSummary] }
    if (url.startsWith('/venue-templates/')) return { data: { ...templateSummary, shapes: [] } }
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

describe('VenueMapEditor: templates', () => {
  /** Open the plan menu (by keyboard: jsdom) and pick an entry. */
  async function planMenu(item: string) {
    q('plan-actions').dispatchEvent(new KeyboardEvent('keydown', { bubbles: true, key: 'Enter' }))
    await flushPromises()
    return q(item)
  }

  it('creates a plan from a template and opens it for placing pins', async () => {
    plans = []
    const wrapper = await mountEditor()
    await wrapper.find('[data-testid="plan-add"]').trigger('click')
    await flushPromises()
    q('plan-create-template').querySelector('input')!.click()
    await flushPromises()
    q('template-card-tpl-1')
      .querySelector<HTMLInputElement>('[data-testid="template-pick"]')!
      .click()
    await flushPromises()
    q('plan-name-save').click()
    await flushPromises()

    expect(api.post).toHaveBeenCalledWith({
      url: '/events/e1/venue-plans',
      body: { name: 'Festwiese', template_id: 'tpl-1' },
    })
    expect(wrapper.find('[data-testid="editor-canvas"]').exists()).toBe(true)
    // Not a drawing tool: the drawing is there, the pins are next.
    expect(q('tool-select').getAttribute('aria-pressed')).toBe('true')
    expect(wrapper.emitted('changed')).toBeTruthy()
  })

  it('reloads the templates when the picked one was deleted meanwhile', async () => {
    plans = []
    const wrapper = await mountEditor()
    await wrapper.find('[data-testid="plan-add"]').trigger('click')
    await flushPromises()
    q('plan-create-template').querySelector('input')!.click()
    await flushPromises()
    q('template-card-tpl-1')
      .querySelector<HTMLInputElement>('[data-testid="template-pick"]')!
      .click()
    await flushPromises()

    api.post.mockRejectedValueOnce(
      Object.assign(new Error('gone'), {
        isAxiosError: true,
        response: {
          status: 404,
          data: { status: 404, title: 'x', code: 'venue_template.not_found' },
        },
      }),
    )
    const listLoads = () => api.get.mock.calls.filter((c) => c[0].url === '/venue-templates').length
    const before = listLoads()
    q('plan-name-save').click()
    await flushPromises()

    expect(listLoads()).toBe(before + 1)
    // The dead pick is dropped, so "Create" waits for a new one.
    expect(q<HTMLButtonElement>('plan-name-save').disabled).toBe(true)
  })

  it('saves the plan as a template after its pending drawing steps', async () => {
    plans = [blankPlan({ shapes: [rectShape()], shapes_revision: 1 })]
    await mountEditor()
    ;(await planMenu('plan-save-template')).click()
    await flushPromises()
    expect(q<HTMLInputElement>('template-name-input').value).toBe('Grounds')
    await typeInto('template-name-input', 'Gelände Vorlage')
    q('template-name-save').click()
    await flushPromises()
    expect(api.post).toHaveBeenCalledWith({
      url: '/venue-plans/plan-1/save-as-template',
      body: { name: 'Gelände Vorlage' },
    })
    expect(document.querySelector('[data-testid="template-name-dialog"]')).toBeNull()
  })

  it('keeps the dialog open when the template cannot be saved', async () => {
    plans = [makePlan()]
    await mountEditor()
    api.post.mockRejectedValueOnce(new Error('limit'))
    ;(await planMenu('plan-save-template')).click()
    await flushPromises()
    q('template-name-save').click()
    await flushPromises()
    expect(document.querySelector('[data-testid="template-name-dialog"]')).not.toBeNull()
  })

  it('has nothing to save from a plan with no drawing and no picture', async () => {
    plans = [blankPlan()]
    await mountEditor()
    const item = await planMenu('plan-save-template')
    expect(item.getAttribute('data-disabled')).not.toBeNull()
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

describe('VenueMapEditor: decoration', () => {
  function treeShape(overrides: Partial<VenueShapeRead> = {}): VenueShapeRead {
    return rectShape({
      id: 'tree-1',
      kind: 'prop',
      style: 'green',
      points: [[0.5, 0.5]],
      label: null,
      prop: 'tree',
      rotation: 0,
      scale: 1,
      ...overrides,
    })
  }

  it('names the decoration in a grammatical German hint', async () => {
    i18n.global.locale.value = 'de'
    plans = [blankPlan()]
    const wrapper = await mountEditor()
    await wrapper.find('[data-testid="tool-prop"]').trigger('click')
    expect(wrapper.find('[data-testid="draw-hint"]').text()).toBe(
      'Tipp auf den Plan, um etwas hinzuzufügen: Laubbaum. Fertig? Tipp auf den Pfeil.',
    )
  })

  it('shows the palette with the tool and stamps the chosen decoration', async () => {
    const random = vi.spyOn(Math, 'random').mockReturnValue(0)
    onTestFinished(() => random.mockRestore())
    plans = [blankPlan()]
    const wrapper = await mountEditor()
    expect(wrapper.find('[data-testid="decor-palette"]').exists()).toBe(false)
    await wrapper.find('[data-testid="tool-prop"]').trigger('click')
    const palette = wrapper.find('[data-testid="decor-palette"]')
    expect(palette.exists()).toBe(true)
    expect(palette.text()).not.toContain('has no shifts')
    expect(wrapper.find('[data-testid="draw-hint"]').text()).toContain('Tap the arrow')

    await wrapper.find('[data-testid="decor-item-conifer"]').trigger('click')
    expect(wrapper.find('[data-testid="decor-item-conifer"]').attributes('aria-checked')).toBe(
      'true',
    )

    const svg = wrapper.find('[data-testid="editor-canvas"]').element
    pointer(svg, 'pointerdown', 500, 250)
    pointer(svg, 'pointerup', 500, 250)
    await flushPromises()
    expect(batchCalls()[0]!.body.ops[0]).toMatchObject({
      op: 'create',
      shape: { kind: 'prop', prop: 'conifer', style: 'green', points: [[0.5, 0.5]], rotation: 0 },
    })
    // Still stamping, and the new one is selected with its own controls.
    expect(wrapper.find('[data-testid="tool-prop"]').attributes('aria-pressed')).toBe('true')
    const inspector = wrapper.find('[data-testid="shape-inspector"]')
    expect(inspector.find('[data-testid="prop-rotation"]').exists()).toBe(true)
    expect(inspector.find('[data-testid="prop-scale"]').exists()).toBe(true)
    expect(inspector.find('[data-testid="style-picker"]').exists()).toBe(false)
    expect(inspector.find('[data-testid="shape-link"]').exists()).toBe(false)
    // Its grips, even while stamping: turn and size, nothing else.
    expect(wrapper.find('[data-testid="handle-rotate"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="handle-scale"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid^="handle-resize-"]').exists()).toBe(false)

    // Esc is "done": back to selecting, the palette goes away.
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await flushPromises()
    expect(wrapper.find('[data-testid="decor-palette"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="shape-inspector"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="handle-rotate"]').exists()).toBe(true)
  })

  it('turns, resizes and retypes the selected decoration from the side panel', async () => {
    plans = [blankPlan({ shapes: [treeShape()], shapes_revision: 2 })]
    serverShapes = [treeShape()]
    serverRevision = 2
    const wrapper = await mountEditor()
    const glyph = wrapper.find('[data-testid="venue-shape-tree-1"]').element
    pointer(glyph, 'pointerdown', 500, 250)
    pointer(glyph, 'pointerup', 500, 250)
    await flushPromises()
    const inspector = () => wrapper.find('[data-testid="shape-inspector"]')
    expect(inspector().find('[data-testid="shape-inspector-heading"]').text()).toContain(
      'Decoration ·',
    )

    await inspector().find('[data-testid="prop-rotate-right"]').trigger('click')
    await flushPromises()
    await inspector().find('[data-testid="prop-rotate-left"]').trigger('click')
    await flushPromises()
    await inspector().find('[data-testid="prop-rotate-left"]').trigger('click')
    await flushPromises()
    const slider = inspector().find('[data-testid="prop-scale"]')
    await slider.setValue('2')
    await slider.trigger('change')
    await flushPromises()
    expect(inspector().find('[data-testid="prop-scale-value"]').text()).toBe('200 %')
    await inspector().find('[data-testid="prop-scale-reset"]').trigger('click')
    await flushPromises()
    const rotation = inspector().find('[data-testid="prop-rotation"]')
    await rotation.setValue('90')
    await rotation.trigger('change')
    await flushPromises()
    await inspector().find('[data-testid="decor-type-tent"]').trigger('click')
    await flushPromises()
    expect(batchCalls().map((c) => c.body.ops[0])).toEqual([
      { op: 'update', id: 'tree-1', patch: { rotation: 15 } },
      { op: 'update', id: 'tree-1', patch: { rotation: 0 } },
      { op: 'update', id: 'tree-1', patch: { rotation: 345 } },
      { op: 'update', id: 'tree-1', patch: { scale: 2 } },
      { op: 'update', id: 'tree-1', patch: { scale: 1 } },
      { op: 'update', id: 'tree-1', patch: { rotation: 90 } },
      { op: 'update', id: 'tree-1', patch: { prop: 'tent', style: 'area' } },
    ])
  })

  async function selectTree() {
    plans = [blankPlan({ shapes: [treeShape()], shapes_revision: 2 })]
    serverShapes = [treeShape()]
    serverRevision = 2
    const wrapper = await mountEditor()
    const glyph = wrapper.find('[data-testid="venue-shape-tree-1"]').element
    pointer(glyph, 'pointerdown', 500, 250)
    pointer(glyph, 'pointerup', 500, 250)
    await flushPromises()
    return wrapper
  }

  /** Where a grip is drawn (its first circle or square), in client = plan units. */
  function gripAt(wrapper: Awaited<ReturnType<typeof mountEditor>>, testid: string) {
    const el = wrapper.find(`[data-testid="${testid}"]`)
    const circle = el.find('circle').element
    return {
      el: el.element,
      x: Number(circle.getAttribute('cx')),
      y: Number(circle.getAttribute('cy')),
    }
  }

  /** One step of a slider drag: `input` only (`setValue` would also fire `change`). */
  async function slide(
    slider: ReturnType<Awaited<ReturnType<typeof mountEditor>>['find']>,
    value: string,
  ) {
    ;(slider.element as HTMLInputElement).value = value
    await slider.trigger('input')
  }

  it('shows a slider drag on the map at once, and saves it once on release', async () => {
    const wrapper = await selectTree()
    const tree = () => wrapper.find('[data-testid="venue-shape-tree-1"]')
    const scale = wrapper.find('[data-testid="prop-scale"]')
    // Every `input` while dragging moves the tree on the map…
    await slide(scale, '1.5')
    await slide(scale, '2')
    expect(tree().attributes('data-scale')).toBe('2')
    expect(wrapper.find('[data-testid="prop-scale-value"]').text()).toBe('200 %')
    // …but nothing is saved until the slider is let go.
    await flushPromises()
    expect(batchCalls()).toHaveLength(0)
    await scale.trigger('change')
    await flushPromises()
    const rotation = wrapper.find('[data-testid="prop-rotation"]')
    await slide(rotation, '30')
    await slide(rotation, '45')
    expect(tree().attributes('data-rotation')).toBe('45')
    await rotation.trigger('change')
    await flushPromises()
    expect(batchCalls().map((c) => c.body.ops)).toEqual([
      [{ op: 'update', id: 'tree-1', patch: { scale: 2 } }],
      [{ op: 'update', id: 'tree-1', patch: { rotation: 45 } }],
    ])

    // One undo step per slider drag.
    await wrapper.find('[data-testid="tool-undo"]').trigger('click')
    await flushPromises()
    expect(tree().attributes('data-rotation')).toBe('0')
    expect(tree().attributes('data-scale')).toBe('2')
  })

  it('turns the decoration with its round grip, live, in one step', async () => {
    const wrapper = await selectTree()
    const tree = () => wrapper.find('[data-testid="venue-shape-tree-1"]')
    const grip = gripAt(wrapper, 'handle-rotate')
    // Straight above the tree, which is not turned.
    expect(grip.x).toBeCloseTo(500)
    expect(grip.y).toBeLessThan(250)

    pointer(grip.el, 'pointerdown', grip.x, grip.y)
    // To the right of the tree: a quarter turn, shown at once with its angle.
    pointer(grip.el, 'pointermove', 600, 252)
    pointer(grip.el, 'pointermove', 600, 250)
    await flushPromises()
    expect(tree().attributes('data-rotation')).toBe('90')
    expect(wrapper.find('[data-testid="grip-badge"]').text()).toBe('90°')
    expect(wrapper.find('[data-testid="handle-rotate"]').attributes('data-active')).toBe('true')
    expect(batchCalls()).toHaveLength(0)
    pointer(grip.el, 'pointerup', 600, 250)
    await flushPromises()
    expect(wrapper.find('[data-testid="grip-badge"]').exists()).toBe(false)
    expect(batchCalls().map((c) => c.body.ops)).toEqual([
      [{ op: 'update', id: 'tree-1', patch: { rotation: 90 } }],
    ])
    // The panel follows, and the tree stays selected.
    expect(wrapper.find('[data-testid="prop-rotation-value"]').text()).toBe('90°')
    expect(tree().attributes('data-selected')).toBe('true')

    // Shift snaps to 15° steps.
    const again = gripAt(wrapper, 'handle-rotate')
    pointer(again.el, 'pointerdown', again.x, again.y)
    const shifted = new PointerEvent('pointermove', {
      bubbles: true,
      clientX: 500 + 100 * Math.cos((10 * Math.PI) / 180),
      clientY: 250 + 100 * Math.sin((10 * Math.PI) / 180),
      pointerId: 1,
      pointerType: 'mouse',
      shiftKey: true,
    })
    again.el.dispatchEvent(shifted)
    await flushPromises()
    expect(tree().attributes('data-rotation')).toBe('105')
    pointer(again.el, 'pointerup', 0, 0)
    await flushPromises()

    await wrapper.find('[data-testid="tool-undo"]').trigger('click')
    await flushPromises()
    expect(tree().attributes('data-rotation')).toBe('90')
  })

  it('resizes the decoration with its corner grip, live, in one step', async () => {
    const wrapper = await selectTree()
    const tree = () => wrapper.find('[data-testid="venue-shape-tree-1"]')
    const grip = gripAt(wrapper, 'handle-scale')
    // Bottom right of the tree.
    expect(grip.x).toBeGreaterThan(500)
    expect(grip.y).toBeGreaterThan(250)

    pointer(grip.el, 'pointerdown', grip.x, grip.y)
    // Twice as far from the centre: twice the size.
    const far = { x: 500 + (grip.x - 500) * 2, y: 250 + (grip.y - 250) * 2 }
    pointer(grip.el, 'pointermove', far.x, far.y)
    await flushPromises()
    expect(tree().attributes('data-scale')).toBe('2')
    expect(wrapper.find('[data-testid="grip-badge"]').text()).toBe('200 %')
    // Way out: no bigger than the largest size.
    pointer(grip.el, 'pointermove', 990, 490)
    await flushPromises()
    expect(tree().attributes('data-scale')).toBe('4')
    pointer(grip.el, 'pointermove', far.x, far.y)
    pointer(grip.el, 'pointerup', far.x, far.y)
    await flushPromises()
    expect(batchCalls().map((c) => c.body.ops)).toEqual([
      [{ op: 'update', id: 'tree-1', patch: { scale: 2 } }],
    ])
    expect(wrapper.find('[data-testid="prop-scale-value"]').text()).toBe('200 %')
  })

  it('keeps the resize grip hit circle off the glyph, so a press there moves it', async () => {
    const original = window.matchMedia
    // A finger: the grips get their large hit circles.
    window.matchMedia = ((query: string) => ({
      matches: query.includes('coarse'),
      media: query,
      onchange: null,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
      dispatchEvent: () => false,
    })) as unknown as typeof window.matchMedia
    try {
      const wrapper = await selectTree()
      const tree = () => wrapper.find('[data-testid="venue-shape-tree-1"]')
      const hit = wrapper.find('[data-testid="handle-scale"] circle').element
      const cx = Number(hit.getAttribute('cx'))
      const cy = Number(hit.getAttribute('cy'))
      const r = Number(hit.getAttribute('r'))
      // The tree's centre is well outside the grip's circle.
      expect(Math.hypot(cx - 500, cy - 250)).toBeGreaterThan(r)
      // The visible square is still inside it.
      const square = wrapper.find('[data-testid="handle-scale"] rect').element
      const sx = Number(square.getAttribute('x')) + Number(square.getAttribute('width')) / 2
      const sy = Number(square.getAttribute('y')) + Number(square.getAttribute('height')) / 2
      expect(Math.hypot(cx - sx, cy - sy)).toBeLessThan(r)

      // A drag from the glyph moves it and leaves its size alone.
      const glyph = tree().element
      pointer(glyph, 'pointerdown', 500, 250)
      pointer(glyph, 'pointermove', 540, 210)
      pointer(glyph, 'pointerup', 540, 210)
      await flushPromises()
      const ops = batchCalls().map((c) => c.body.ops)
      expect(ops).toHaveLength(1)
      expect(ops[0]).toEqual([
        { op: 'update', id: 'tree-1', patch: { points: expect.any(Array) } },
      ])
    } finally {
      window.matchMedia = original
    }
  })

  it('keeps the decoration selected when Escape cancels a grip drag released on the ground', async () => {
    const wrapper = await selectTree()
    const tree = () => wrapper.find('[data-testid="venue-shape-tree-1"]')
    const grip = gripAt(wrapper, 'handle-rotate')
    pointer(grip.el, 'pointerdown', grip.x, grip.y)
    pointer(grip.el, 'pointermove', 600, 250)
    await flushPromises()
    expect(tree().attributes('data-rotation')).toBe('90')
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await flushPromises()
    expect(tree().attributes('data-rotation')).toBe('0')

    // Let go far from the tree: the browser's click lands on the empty plan.
    const svg = wrapper.find('[data-testid="editor-canvas"]').element
    pointer(svg, 'pointerup', 900, 450)
    svg.dispatchEvent(new MouseEvent('click', { bubbles: true, clientX: 900, clientY: 450 }))
    await flushPromises()
    expect(tree().attributes('data-selected')).toBe('true')
    expect(wrapper.find('[data-testid="handle-rotate"]').exists()).toBe(true)
    expect(batchCalls()).toHaveLength(0)

    // A plain tap on the ground afterwards still clears the selection.
    pointer(svg, 'pointerdown', 900, 450)
    pointer(svg, 'pointerup', 900, 450)
    svg.dispatchEvent(new MouseEvent('click', { bubbles: true, clientX: 900, clientY: 450 }))
    await flushPromises()
    expect(wrapper.find('[data-testid="handle-rotate"]').exists()).toBe(false)
  })

  it('draws a hedge from the line presets, and starts a sandpit', async () => {
    plans = [blankPlan()]
    const wrapper = await mountEditor()
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'd' }))
    await flushPromises()
    await wrapper.find('[data-testid="decor-line-hedge"]').trigger('click')
    expect(wrapper.find('[data-testid="tool-path"]').attributes('aria-pressed')).toBe('true')
    const svg = wrapper.find('[data-testid="editor-canvas"]').element
    for (const [x, y] of [
      [100, 100],
      [300, 100],
    ]) {
      pointer(svg, 'pointerdown', x!, y!)
      pointer(svg, 'pointerup', x!, y!)
    }
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter' }))
    await flushPromises()
    expect(batchCalls()[0]!.body.ops[0]).toMatchObject({
      shape: { kind: 'path', style: 'hedge', stroke_width: 0.016 },
    })

    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'd' }))
    await flushPromises()
    await wrapper.find('[data-testid="decor-area-sand"]').trigger('click')
    expect(wrapper.find('[data-testid="tool-polygon"]').attributes('aria-pressed')).toBe('true')
  })
})

describe('VenueDecorPalette', () => {
  it('moves the choice with the arrow keys, keeping them from the editor', async () => {
    const wrapper = mount(VenueDecorPalette, {
      props: { modelValue: 'tree', mode: 'stamp' },
      global: { plugins: [i18n] },
      attachTo: document.body,
    })
    mounted.push(wrapper)
    const outer = vi.fn()
    document.addEventListener('keydown', outer)
    const tree = wrapper.find('[data-testid="decor-item-tree"]')
    expect(tree.attributes('tabindex')).toBe('0')
    expect(wrapper.find('[data-testid="decor-item-bench"]').attributes('tabindex')).toBe('-1')
    await tree.trigger('keydown', { key: 'ArrowRight' })
    await tree.trigger('keydown', { key: 'ArrowLeft' })
    await tree.trigger('keydown', { key: 'End' })
    await tree.trigger('keydown', { key: 'Home' })
    await tree.trigger('keydown', { key: 'x' })
    expect(wrapper.emitted('update:modelValue')).toEqual([
      ['conifer'],
      ['lamp'],
      ['lamp'],
      ['tree'],
    ])
    // Only the unrelated key reached the document.
    expect(outer).toHaveBeenCalledTimes(1)
    document.removeEventListener('keydown', outer)

    await wrapper.find('[data-testid="decor-line-water"]').trigger('click')
    await wrapper.find('[data-testid="decor-area-sand"]').trigger('click')
    expect(wrapper.emitted('pick-line')).toEqual([['water']])
    expect(wrapper.emitted('pick-area')).toEqual([['sand']])
  })

  it('is a grid of types in the side panel, and does nothing while disabled', async () => {
    const wrapper = mount(VenueDecorPalette, {
      props: { modelValue: null, mode: 'picker', disabled: true },
      global: { plugins: [i18n] },
    })
    expect(wrapper.find('[data-testid="decor-line-hedge"]').exists()).toBe(false)
    // Nothing chosen: the first one takes the Tab stop.
    expect(wrapper.find('[data-testid="decor-type-tree"]').attributes('tabindex')).toBe('0')
    await wrapper.find('[data-testid="decor-type-bench"]').trigger('click')
    expect(wrapper.emitted('update:modelValue')).toBeUndefined()
    await wrapper.setProps({ disabled: false, modelValue: 'bench' })
    await wrapper.find('[data-testid="decor-type-bench"]').trigger('click')
    expect(wrapper.emitted('update:modelValue')).toBeUndefined()
    await wrapper.find('[data-testid="decor-type-bin"]').trigger('click')
    expect(wrapper.emitted('update:modelValue')).toEqual([['bin']])
  })
})

describe('VenueMapEditor: decoration on top of a room', () => {
  it('places the tree on the room and keeps the tree selected', async () => {
    plans = [blankPlan({ shapes: [rectShape()], shapes_revision: 1 })]
    serverShapes = [rectShape()]
    serverRevision = 1
    const wrapper = await mountEditor()
    await wrapper.find('[data-testid="tool-prop"]').trigger('click')
    const room = wrapper.find('[data-testid="venue-shape-shape-1"] .vs-body').element
    pointer(room, 'pointerdown', 200, 100)
    pointer(room, 'pointerup', 200, 100)
    room.dispatchEvent(new MouseEvent('click', { bubbles: true, clientX: 200, clientY: 100 }))
    await flushPromises()
    const create = batchCalls()[0]!.body.ops[0] as { op: string; shape: { id: string } }
    expect(create).toMatchObject({ op: 'create', shape: { kind: 'prop', points: [[0.2, 0.2]] } })
    expect(wrapper.find('[data-testid="shape-inspector-heading"]').text()).toContain('Decoration ·')
    // Enter on a focused shape still selects it.
    const shape = wrapper.find('[data-testid="venue-shape-shape-1"]')
    await shape.trigger('keydown', { key: 'Enter' })
    expect(wrapper.find('[data-testid="shape-inspector-heading"]').text()).toBe('Hall')
  })
})

describe('VenueMapEditor: decoration ghost', () => {
  it('shows a faint copy of the decoration under the pointer, gone when it leaves', async () => {
    plans = [blankPlan()]
    const wrapper = await mountEditor()
    await wrapper.find('[data-testid="tool-prop"]').trigger('click')
    await wrapper.find('[data-testid="decor-item-bench"]').trigger('click')
    pointer(window as unknown as Element, 'pointermove', 400, 200)
    await flushPromises()
    const ghost = wrapper.find('[data-testid="draw-prop-ghost"]')
    expect(ghost.attributes('data-prop')).toBe('bench')
    expect(ghost.find('[data-prop="bench"]').exists()).toBe(true)
    await wrapper.find('[data-testid="editor-canvas"]').trigger('pointerleave')
    expect(wrapper.find('[data-testid="draw-prop-ghost"]').exists()).toBe(false)
  })
})

describe('VenueMapEditor: the phone sheet', () => {
  // jsdom applies no CSS: "shut" is the `max-lg:hidden` class on the panel.
  const isShut = (wrapper: Awaited<ReturnType<typeof mountEditor>>) =>
    wrapper.get('[data-testid="editor-panel"]').classes().includes('max-lg:hidden')

  it('starts shut, opens with its button and shuts again for placing a pin', async () => {
    api.post.mockResolvedValue({
      data: {
        id: 'm2',
        plan_id: 'plan-1',
        kind: 'location',
        location_id: 'loc-kitchen',
        x: 0.5,
        y: 0.5,
      },
    })
    const wrapper = await mountEditor()
    expect(isShut(wrapper)).toBe(true)

    await wrapper.get('[data-testid="editor-sheet-open"]').trigger('click')
    expect(isShut(wrapper)).toBe(false)
    expect(wrapper.get('[data-testid="editor-panel"]').attributes('aria-label')).toBe(
      'Pins & picture',
    )

    // Picking a place puts the sheet away, so the plan can be tapped.
    await wrapper.get('[data-testid="palette-location-loc-kitchen"]').trigger('click')
    expect(isShut(wrapper)).toBe(true)
    expect(wrapper.find('[data-testid="editor-sheet-open"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="placement-banner"]').exists()).toBe(true)

    // The new pin is selected, but the sheet stays shut for the next one.
    await wrapper
      .get('[data-testid="editor-canvas"]')
      .trigger('click', { clientX: 500, clientY: 250 })
    await flushPromises()
    expect(wrapper.find('[data-testid="marker-panel"]').exists()).toBe(true)
    expect(isShut(wrapper)).toBe(true)
    expect(wrapper.get('[data-testid="editor-sheet-open"]').text()).toBe('Selection')
  })

  it('opens for a tapped pin but not for a dragged one, and hides with its button', async () => {
    api.patch.mockImplementation(async ({ body }: { body: Record<string, unknown> }) => ({
      data: { ...plans[0]!.markers![0]!, ...body },
    }))
    const wrapper = await mountEditor()
    const marker = wrapper.get('[data-testid="map-marker-loc-foyer"]').element

    pointer(marker, 'pointerdown', 500, 250)
    await flushPromises()
    pointer(marker, 'pointermove', 600, 300)
    pointer(marker, 'pointerup', 600, 300)
    await flushPromises()
    expect(wrapper.find('[data-testid="marker-panel"]').exists()).toBe(true)
    expect(isShut(wrapper)).toBe(true)

    await wrapper
      .get('[data-testid="editor-canvas"]')
      .trigger('click', { clientX: 900, clientY: 50 })
    await flushPromises()
    pointer(marker, 'pointerdown', 600, 300)
    await flushPromises()
    pointer(marker, 'pointerup', 600, 300)
    await flushPromises()
    expect(isShut(wrapper)).toBe(false)
    expect(wrapper.get('[data-testid="editor-panel"]').attributes('aria-label')).toBe('Selection')

    await wrapper.get('[data-testid="editor-sheet-close"]').trigger('click')
    expect(isShut(wrapper)).toBe(true)
    // Still selected: the button on the plan brings it back.
    expect(wrapper.find('[data-testid="marker-panel"]').exists()).toBe(true)
  })

  it('opens for a shape picked with the select tool and shuts for another tool', async () => {
    plans = [blankPlan({ shapes: [rectShape()] })]
    serverShapes = [rectShape()]
    const wrapper = await mountEditor()
    await wrapper.get('[data-testid="venue-shape-shape-1"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-testid="shape-inspector"]').exists()).toBe(true)
    expect(isShut(wrapper)).toBe(false)

    await wrapper.get('[data-testid="tool-prop"]').trigger('click')
    await flushPromises()
    expect(isShut(wrapper)).toBe(true)
  })

  it('stays shut for a picked decoration, so its grips stay in reach', async () => {
    const tree = rectShape({
      id: 'tree-1',
      kind: 'prop',
      style: 'green',
      points: [[0.5, 0.5]],
      label: null,
      prop: 'tree',
      rotation: 0,
      scale: 1,
    })
    plans = [blankPlan({ shapes: [tree] })]
    serverShapes = [tree]
    const wrapper = await mountEditor()
    await wrapper.get('[data-testid="venue-shape-tree-1"]').trigger('click')
    await flushPromises()
    expect(isShut(wrapper)).toBe(true)
    expect(wrapper.get('[data-testid="editor-sheet-open"]').text()).toBe('Selection')

    await wrapper.get('[data-testid="editor-sheet-open"]').trigger('click')
    expect(isShut(wrapper)).toBe(false)
    expect(wrapper.find('[data-testid="shape-inspector"]').exists()).toBe(true)
  })

  it('shuts when a tap on the plan finds nothing to select', async () => {
    const wrapper = await mountEditor()
    await wrapper.get('[data-testid="editor-sheet-open"]').trigger('click')
    await wrapper
      .get('[data-testid="editor-canvas"]')
      .trigger('click', { clientX: 900, clientY: 50 })
    expect(isShut(wrapper)).toBe(true)
  })

  it('keeps the plan switcher compact and moves redo and snapping into "More"', async () => {
    const wrapper = await mountEditor()
    expect(wrapper.get('[data-testid="plan-switcher-menu"]').text()).toBe('Grounds')
    expect(wrapper.get('[data-testid="tool-more"]').attributes('aria-label')).toBe('More')
  })

  it('anchors the menus behind a hint to their own buttons', async () => {
    // A menu trigger inside HintTooltip registers with the tooltip, not its
    // menu; without an explicit reference the menu opens off-screen.
    const wrapper = await mountEditor()
    const references = wrapper
      .findAllComponents(DropdownMenuContent)
      .map((menu) => menu.props('reference'))
    expect(references).toContain(q('plan-actions'))
    expect(references).toContain(q('tool-more'))
  })
})
