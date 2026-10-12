// @vitest-environment jsdom
import { mount } from '@vue/test-utils'
import { h } from 'vue'

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'

import LocationDescription from '@/components/locations/LocationDescription.vue'
import VenueMapCanvas from '@/components/venue-map/VenueMapCanvas.vue'
import VenueMarkerGlyph from '@/components/venue-map/VenueMarkerGlyph.vue'
import VenueMiniMap from '@/components/venue-map/VenueMiniMap.vue'
import VenuePlanSwitcher from '@/components/venue-map/VenuePlanSwitcher.vue'

import type { LocationPin, LocationRead, VenuePlanRead } from '@/client/types.gen'
import i18n from '@/locales/i18n'

/**
 * Smoke tests for the shared map components: they render, wire their props
 * through and emit what F2–F4 rely on. Geometry and loading are covered by the
 * lib and composable specs.
 */

vi.mock('@/composables/useAuthenticatedClient', () => ({
  useAuthenticatedClient: () => ({ getAuthToken: async () => 'tok' }),
}))

const fetchMock = vi.fn()

beforeEach(() => {
  // jsdom has no layout; ChipNav scrolls the active chip into view.
  Element.prototype.scrollIntoView = () => {}
  i18n.global.locale.value = 'en'
  fetchMock.mockResolvedValue({ ok: true, status: 200, blob: async () => new Blob(['x']) })
  vi.stubGlobal('fetch', fetchMock)
  vi.stubGlobal(
    'URL',
    Object.assign(URL, { createObjectURL: () => 'blob:plan', revokeObjectURL: () => {} }),
  )
})

afterEach(() => {
  vi.unstubAllGlobals()
  fetchMock.mockReset()
})

const flush = () => new Promise((r) => setTimeout(r, 0))

const foyer: LocationRead = {
  id: 'loc-foyer',
  event_id: 'e1',
  name: 'Foyer',
  description: '**Ground floor**, left of the stairs',
  address: 'Main St 1',
  map_url: 'https://maps.example/foyer',
  contact: 'Anna, 0123',
  created_at: '2026-10-01T00:00:00Z',
  updated_at: '2026-10-01T00:00:00Z',
}

const plan: VenuePlanRead = {
  id: 'plan-1',
  event_id: 'e1',
  name: 'Grounds',
  sort_order: 0,
  image_etag: 'etag1',
  image_width: 1000,
  image_height: 500,
  created_at: '2026-10-01T00:00:00Z',
  updated_at: '2026-10-01T00:00:00Z',
  markers: [
    { id: 'm1', plan_id: 'plan-1', kind: 'location', location_id: 'loc-foyer', x: 0.5, y: 0.5 },
    { id: 'm2', plan_id: 'plan-1', kind: 'first_aid', label: 'Tent', x: 0.1, y: 0.2 },
  ],
}

describe('VenueMarkerGlyph', () => {
  it('places and scales itself, and rings when highlighted', () => {
    const wrapper = mount({
      render: () =>
        h('svg', [
          h(VenueMarkerGlyph, {
            kind: 'parking',
            x: 10,
            y: 20,
            scale: 2,
            label: 'P1',
            highlighted: true,
          }),
        ]),
    })
    const g = wrapper.get('g.venue-marker')
    expect(g.attributes('transform')).toBe('translate(10 20) scale(2)')
    expect(g.attributes('data-kind')).toBe('parking')
    expect(wrapper.find('[data-testid="marker-highlight"]').exists()).toBe(true)
    expect(wrapper.get('title').text()).toBe('P1')
  })
})

describe('VenueMapCanvas', () => {
  it('draws the plan image and one button per marker', async () => {
    const wrapper = mount(VenueMapCanvas, {
      props: { plan, locations: [foyer], highlightIds: ['loc-foyer'], selectedMarkerId: 'm2' },
      global: { plugins: [i18n] },
    })
    await flush()

    expect(fetchMock).toHaveBeenCalledWith(
      `${import.meta.env.VITE_API_URL}/venue-plans/plan-1/image?v=etag1`,
      expect.anything(),
    )
    expect(wrapper.get('svg').attributes('viewBox')).toBe('0 0 1000 500')
    expect(wrapper.get('image').attributes('href')).toBe('blob:plan')

    const foyerMarker = wrapper.get('[data-testid="map-marker-loc-foyer"]')
    expect(foyerMarker.attributes('role')).toBe('button')
    expect(foyerMarker.attributes('aria-label')).toBe('Foyer')
    expect(foyerMarker.attributes('data-highlighted')).toBe('true')
    expect(wrapper.get('[data-testid="map-marker-m2"]').attributes('aria-label')).toBe(
      'Tent (First aid)',
    )
  })

  it('emits select-marker on click and on Enter', async () => {
    const wrapper = mount(VenueMapCanvas, {
      props: { plan, locations: [foyer] },
      global: { plugins: [i18n] },
    })
    await wrapper.get('[data-testid="map-marker-loc-foyer"]').trigger('click')
    await wrapper.get('[data-testid="map-marker-m2"]').trigger('keydown', { key: 'Enter' })
    await wrapper.get('[data-testid="map-marker-m2"]').trigger('keydown', { key: 'a' })

    const events = wrapper.emitted('select-marker')!
    expect(events.map(([m]) => (m as { id: string }).id)).toEqual(['m1', 'm2'])
  })

  it('keeps marker order when the selection changes and draws an inert copy on top', async () => {
    const wrapper = mount(VenueMapCanvas, {
      props: { plan, locations: [foyer], selectedMarkerId: null },
      global: { plugins: [i18n] },
    })
    const order = () => wrapper.findAll('[role="button"]').map((m) => m.attributes('data-testid'))
    const before = order()
    expect(wrapper.find('[data-testid="map-marker-selected-copy"]').exists()).toBe(false)

    await wrapper.setProps({ selectedMarkerId: 'm1' })
    // Moving the focused marker in the DOM would drop keyboard focus.
    expect(order()).toEqual(before)
    const copy = wrapper.get('[data-testid="map-marker-selected-copy"]')
    expect(copy.attributes('aria-hidden')).toBe('true')
    expect(copy.attributes('role')).toBeUndefined()
    expect(wrapper.findAll('g.venue-marker').at(-1)!.element).toBe(copy.element)
  })

  it('is inert when not interactive', async () => {
    const wrapper = mount(VenueMapCanvas, {
      props: { plan, interactive: false },
      global: { plugins: [i18n] },
    })
    const marker = wrapper.get('[data-testid="map-marker-loc-foyer"]')
    expect(marker.attributes('role')).toBeUndefined()
    await marker.trigger('click')
    expect(wrapper.emitted('select-marker')).toBeUndefined()
  })

  it('exposes focusMarker and ready', async () => {
    const wrapper = mount(VenueMapCanvas, { props: { plan }, global: { plugins: [i18n] } })
    const vm = wrapper.vm as unknown as {
      focusMarker: (id: string, zoom?: number) => void
      ready: () => Promise<void>
    }
    vm.focusMarker('m1', 2)
    await wrapper.vm.$nextTick()
    expect(wrapper.get('svg').attributes('viewBox')).toBe('250 125 500 250')

    await flush()
    await wrapper.get('image').trigger('load')
    await expect(vm.ready()).resolves.toBeUndefined()
  })

  it('shows an error when the image cannot be loaded', async () => {
    fetchMock.mockResolvedValue({ ok: false, status: 404 })
    const wrapper = mount(VenueMapCanvas, { props: { plan }, global: { plugins: [i18n] } })
    await flush()
    expect(wrapper.get('[role="alert"]').text()).toContain('could not be loaded')
  })
})

describe('VenueMiniMap', () => {
  const pin: LocationPin = {
    plan_id: 'plan-1',
    plan_name: 'Grounds',
    marker_id: 'm1',
    image_etag: 'etag1',
    image_width: 1000,
    image_height: 500,
    x: 0.5,
    y: 0.5,
  }
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', component: { render: () => null } },
      { path: '/app/map/:eventId?', name: 'event-map', component: { render: () => null } },
    ],
  })

  it('crops around the pin and links to the map', async () => {
    const wrapper = mount(VenueMiniMap, {
      props: { eventId: 'e1', pin, locationId: 'loc-foyer' },
      global: { plugins: [i18n, router] },
    })
    await flush()

    const vb = wrapper.get('svg').attributes('viewBox')!.split(' ').map(Number)
    expect(vb[0]! + vb[2]! / 2).toBeCloseTo(500)
    expect(wrapper.get('a').attributes('href')).toBe('/app/map/e1?plan=plan-1&location=loc-foyer')
    expect(wrapper.text()).toContain('Open map')
  })

  it('renders without a link when static', async () => {
    const wrapper = mount(VenueMiniMap, {
      props: { eventId: 'e1', pin, static: true },
      global: { plugins: [i18n, router] },
    })
    await flush()
    expect(wrapper.find('a').exists()).toBe(false)
    expect(wrapper.text()).toContain('Grounds')
    await wrapper.get('image').trigger('load')
    await expect(
      (wrapper.vm as unknown as { ready: () => Promise<void> }).ready(),
    ).resolves.toBeUndefined()
  })
})

describe('VenuePlanSwitcher', () => {
  it('maps chip clicks to plan ids', async () => {
    const plans = [
      { id: 'a', name: 'Grounds' },
      { id: 'b', name: 'Hall' },
    ]
    const wrapper = mount(VenuePlanSwitcher, {
      props: { plans, modelValue: 'a' },
      global: { plugins: [i18n] },
    })
    const buttons = wrapper.findAll('button')
    expect(buttons.map((b) => b.text())).toEqual(['Grounds', 'Hall'])
    await buttons[1]!.trigger('click')
    expect(wrapper.emitted('update:modelValue')).toEqual([['b']])
  })
})

describe('LocationDescription', () => {
  it('renders markdown, address, contact and a safe map link', () => {
    const wrapper = mount(LocationDescription, {
      props: { location: foyer },
      global: { plugins: [i18n] },
    })
    expect(wrapper.get('[data-testid="location-description-body"]').html()).toContain(
      '<strong>Ground floor</strong>',
    )
    expect(wrapper.text()).toContain('Main St 1')
    expect(wrapper.text()).toContain('Anna, 0123')
    const link = wrapper.get('[data-testid="location-map-link"]')
    expect(link.attributes('href')).toBe('https://maps.example/foyer')
    expect(link.attributes('target')).toBe('_blank')
  })

  it('compact leaves out the contact and drops a non-http map link', () => {
    const wrapper = mount(LocationDescription, {
      props: { location: { ...foyer, map_url: 'javascript:alert(1)' }, compact: true },
      global: { plugins: [i18n] },
    })
    expect(wrapper.text()).not.toContain('Anna')
    expect(wrapper.find('[data-testid="location-map-link"]').exists()).toBe(false)
  })
})
