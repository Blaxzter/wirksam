// @vitest-environment jsdom
import { mount } from '@vue/test-utils'
import { h } from 'vue'

import { beforeEach, describe, expect, it } from 'vitest'

import VenueShapeLayer from '@/components/venue-map/VenueShapeLayer.vue'

import type { RenderShape } from '@/lib/venue-shapes'
import i18n from '@/locales/i18n'

beforeEach(() => {
  i18n.global.locale.value = 'en'
})

function shape(overrides: Partial<RenderShape> & Pick<RenderShape, 'id'>): RenderShape {
  return {
    kind: 'rect',
    style: 'room',
    points: [
      [0.1, 0.1],
      [0.5, 0.5],
    ],
    label: null,
    label_size: 'md',
    label_x: null,
    label_y: null,
    stroke_width: null,
    location_id: null,
    sort_order: 0,
    ...overrides,
  }
}

const room = shape({ id: 'room', label: 'Hall', location_id: 'loc-hall' })
const area = shape({
  id: 'area',
  kind: 'polygon',
  style: 'area',
  points: [
    [0.6, 0.1],
    [0.9, 0.1],
    [0.75, 0.4],
  ],
  location_id: 'loc-meadow',
})
const path = shape({
  id: 'path',
  kind: 'path',
  style: 'path',
  points: [
    [0, 0.9],
    [0.5, 0.95],
    [1, 0.9],
  ],
  stroke_width: 0.05,
  label: 'Walkway',
})
const text = shape({
  id: 'text',
  kind: 'label',
  style: 'wall',
  points: [[0.5, 0.7]],
  label: 'Gate',
})
const wall = shape({ id: 'wall', style: 'wall' })

type Props = InstanceType<typeof VenueShapeLayer>['$props']

function render(props: Partial<Props> = {}) {
  return mount(
    {
      render: () =>
        h('svg', [
          h(VenueShapeLayer, {
            shapes: [room, area, path, text, wall],
            width: 1000,
            height: 1000,
            unitsPerPixel: 1,
            ...props,
          } as Props),
        ]),
    },
    { global: { plugins: [i18n] } },
  )
}

describe('VenueShapeLayer', () => {
  it('draws each kind with its style class', () => {
    const wrapper = render()
    const g = (id: string) => wrapper.get(`[data-testid="venue-shape-${id}"]`)

    const rect = g('room').get('rect.vs-body')
    expect(rect.attributes()).toMatchObject({ x: '100', y: '100', width: '400', height: '400' })
    expect(Number(rect.attributes('rx'))).toBeCloseTo(6)
    expect(g('room').classes()).toContain('vs-room')
    expect(g('room').attributes('data-linked')).toBe('true')

    expect(g('area').get('polygon.vs-body').attributes('points')).toBe('600,100 900,100 750,400')
    expect(g('area').classes()).toContain('vs-area')

    const line = g('path').get('polyline.vs-body')
    expect(line.attributes('points')).toBe('0,900 500,950 1000,900')
    // In plan units, inline so no stylesheet rule beats it.
    expect(line.attributes('style')).toContain('stroke-width: 50px')
    expect(g('path').attributes('data-linked')).toBe('false')

    // Walls and paths have square corners.
    expect(g('wall').get('rect').attributes('rx')).toBe('0')

    // A text-only shape draws no geometry.
    expect(g('text').find('.vs-body').exists()).toBe(false)
    expect(g('text').classes()).toContain('vs-label-kind')
  })

  it('draws every caption after every shape', () => {
    const wrapper = render()
    const layers = wrapper.findAll('[data-layer]').map((l) => l.attributes('data-layer'))
    expect(layers).toEqual(['shapes', 'shape-labels'])
    const labels = wrapper.get('[data-layer="shape-labels"]')
    expect(labels.attributes('pointer-events')).toBe('none')
    expect(labels.findAll('text').map((t) => t.text())).toEqual(['Hall', 'Walkway', 'Gate'])

    const gate = wrapper.get('[data-testid="venue-shape-label-text"]')
    expect(gate.classes()).toEqual(expect.arrayContaining(['vs-wall', 'vs-label-kind']))
    expect(gate.attributes()).toMatchObject({ x: '500', y: '700', 'paint-order': 'stroke' })
    expect(Number(gate.attributes('font-size'))).toBeCloseTo(26)
    expect(gate.attributes('stroke-width')).toBe('3')
  })

  it('hides captions that are too small, or when labels are off', () => {
    // 26 units at 10 units per px = 2.6px: hidden.
    expect(render({ unitsPerPixel: 10 }).findAll('.venue-shape-label')).toHaveLength(0)
    expect(render({ showLabels: false }).findAll('.venue-shape-label')).toHaveLength(0)
    // At 5 units per px the free label is clamped up to the minimum size.
    const gate = render({ unitsPerPixel: 5, minLabelPx: 9 }).get(
      '[data-testid="venue-shape-label-text"]',
    )
    expect(Number(gate.attributes('font-size'))).toBeCloseTo(45)
  })

  it('is inert by default', async () => {
    const wrapper = render()
    expect(wrapper.get('.venue-shape-layer').attributes('pointer-events')).toBe('none')
    const g = wrapper.get('[data-testid="venue-shape-room"]')
    expect(g.attributes('role')).toBeUndefined()
    expect(g.attributes('aria-hidden')).toBe('true')
    await g.trigger('click')
    await g.trigger('keydown', { key: 'Enter' })
    await g.trigger('pointerdown')
    const layer = wrapper.getComponent(VenueShapeLayer)
    expect(layer.emitted('select-shape')).toBeUndefined()
    expect(layer.emitted('shape-pointerdown')).toBeUndefined()
  })

  it('lets only linked areas be tapped in linked mode', async () => {
    const wrapper = render({ interactive: 'linked' })
    const layer = wrapper.getComponent(VenueShapeLayer)
    expect(wrapper.get('.venue-shape-layer').attributes('pointer-events')).toBeUndefined()

    const roomG = wrapper.get('[data-testid="venue-shape-room"]')
    expect(roomG.attributes('pointer-events')).toBe('visiblePainted')
    expect(roomG.classes()).toContain('vs-tappable')
    expect(roomG.find('.vs-hover').exists()).toBe(true)
    // Not focusable: the place's pill is the keyboard route.
    expect(roomG.attributes('tabindex')).toBeUndefined()
    expect(roomG.attributes('aria-hidden')).toBe('true')

    const pathG = wrapper.get('[data-testid="venue-shape-path"]')
    expect(pathG.attributes('pointer-events')).toBe('none')

    await roomG.trigger('click')
    await pathG.trigger('click')
    await roomG.trigger('keydown', { key: 'Enter' })
    await roomG.trigger('pointerdown')
    expect(layer.emitted('select-shape')!.map(([s]) => (s as RenderShape).id)).toEqual(['room'])
    expect(layer.emitted('shape-pointerdown')).toBeUndefined()
  })

  it('makes every shape a named button in editor mode', async () => {
    const wrapper = render({
      interactive: 'all',
      locationNames: { 'loc-meadow': 'Meadow' },
      selectedShapeIds: ['area'],
    })
    const layer = wrapper.getComponent(VenueShapeLayer)
    const g = (id: string) => wrapper.get(`[data-testid="venue-shape-${id}"]`)

    expect(g('room').attributes()).toMatchObject({ role: 'button', tabindex: '0' })
    expect(g('room').attributes('aria-label')).toBe('Room: Hall')
    expect(g('area').attributes('aria-label')).toBe('Area: Meadow')
    expect(g('wall').attributes('aria-label')).toBe('Wall: Rectangle')
    expect(g('area').attributes('aria-pressed')).toBe('true')
    expect(g('room').attributes('aria-pressed')).toBe('false')
    expect(g('area').find('.vs-sel-outer').exists()).toBe(true)
    expect(g('area').find('.vs-sel-inner').exists()).toBe(true)
    expect(g('area').attributes('data-selected')).toBe('true')
    // A text-only shape gets something to grab.
    expect(g('text').find('circle.vs-label-hit').attributes()).toMatchObject({
      cx: '500',
      cy: '700',
      r: '10',
    })

    await g('path').trigger('click')
    await g('wall').trigger('keydown', { key: ' ' })
    await g('wall').trigger('keydown', { key: 'Enter' })
    await g('wall').trigger('keydown', { key: 'x' })
    await g('text').trigger('pointerdown')
    expect(layer.emitted('select-shape')!.map(([s]) => (s as RenderShape).id)).toEqual([
      'path',
      'wall',
      'wall',
    ])
    expect(layer.emitted('shape-pointerdown')!.map(([s]) => (s as RenderShape).id)).toEqual([
      'text',
    ])
  })

  it('highlights the selected place strongly and "my" places dashed', () => {
    const wrapper = render({
      selectedLocationId: 'loc-hall',
      highlightLocationIds: ['loc-meadow', 'loc-hall'],
    })
    const roomG = wrapper.get('[data-testid="venue-shape-room"]')
    expect(roomG.attributes('data-selected-location')).toBe('true')
    expect(roomG.find('.vs-hl-selected').exists()).toBe(true)
    expect(roomG.find('.vs-hl-mine').exists()).toBe(true)

    const areaG = wrapper.get('[data-testid="venue-shape-area"]')
    expect(areaG.attributes('data-selected-location')).toBeUndefined()
    expect(areaG.attributes('data-highlighted')).toBe('true')
    expect(areaG.find('.vs-hl-selected').exists()).toBe(false)

    // Nothing selected: no strong highlight anywhere.
    expect(render().findAll('.vs-hl-selected')).toHaveLength(0)
  })

  it('skips a malformed rect', () => {
    const broken = shape({ id: 'broken', points: [[0.1, 0.1]] })
    const wrapper = mount(
      {
        render: () =>
          h('svg', [
            h(VenueShapeLayer, { shapes: [broken], width: 100, height: 100, unitsPerPixel: 1 }),
          ]),
      },
      { global: { plugins: [i18n] } },
    )
    expect(wrapper.get('[data-testid="venue-shape-broken"]').find('rect').exists()).toBe(false)
  })
})
