// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'

import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import VenueMapEditor from '@/components/venue-map/VenueMapEditor.vue'
import VenueMarkerPalette from '@/components/venue-map/VenueMarkerPalette.vue'

import type { LocationRead, VenueMarkerRead, VenuePlanRead } from '@/client/types.gen'
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
    created_at: stamp,
    updated_at: stamp,
    markers: [
      { id: 'm1', plan_id: 'plan-1', kind: 'location', location_id: 'loc-foyer', x: 0.5, y: 0.5 },
    ],
    ...overrides,
  }
}

let plans: VenuePlanRead[]

beforeEach(() => {
  setActivePinia(createPinia())
  i18n.global.locale.value = 'en'
  Element.prototype.scrollIntoView = () => {}
  plans = [makePlan()]
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

afterEach(() => {
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

  it('asks for a picture while the plan has none', async () => {
    plans = [makePlan({ image_etag: null, image_width: null, image_height: null, markers: [] })]
    const wrapper = await mountEditor()
    expect(wrapper.find('[data-testid="plan-upload-zone"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="editor-canvas"]').exists()).toBe(false)
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
