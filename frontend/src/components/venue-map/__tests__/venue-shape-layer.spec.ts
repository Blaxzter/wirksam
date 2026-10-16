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
    expect(layers).toEqual(['shapes', 'props', 'shape-labels'])
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
  it('renders the pre-existing styles as before, plus a building cast', () => {
    const styles = [
      'building',
      'room',
      'area',
      'stage',
      'furniture',
      'green',
      'water',
      'parking',
      'path',
      'wall',
    ] as const
    const shapes = styles.flatMap((style) => [
      shape({ id: `${style}-rect`, style }),
      shape({
        id: `${style}-path`,
        kind: 'path',
        style,
        points: [
          [0, 0],
          [1, 1],
        ],
        stroke_width: 0.02,
      }),
    ])
    const wrapper = mount(
      {
        render: () =>
          h('svg', [h(VenueShapeLayer, { shapes, width: 1000, height: 1000, unitsPerPixel: 1 })]),
      },
      { global: { plugins: [i18n] } },
    )
    const tags = (id: string) =>
      wrapper
        .get(`[data-testid="venue-shape-${id}"]`)
        .findAll('*')
        .map((el) => `${el.element.tagName}.${el.classes().join('.')}`)
    for (const style of styles) {
      expect([style, tags(`${style}-rect`)]).toEqual([
        style,
        style === 'building' ? ['rect.vs-cast', 'rect.vs-body'] : ['rect.vs-body'],
      ])
      expect([style, tags(`${style}-path`)]).toEqual([
        style,
        style === 'water' ? ['polyline.vs-body', 'polyline.vs-ripple'] : ['polyline.vs-body'],
      ])
    }
    const cast = wrapper.get('[data-testid="venue-shape-building-rect"] .vs-cast')
    expect(cast.attributes('transform')).toBe('translate(4 6)')
  })

  it('textures water, hedges and fences in plan units', () => {
    const line = (id: string, style: RenderShape['style']) =>
      shape({
        id,
        kind: 'path',
        style,
        points: [
          [0, 0.5],
          [1, 0.5],
        ],
        stroke_width: 0.01,
      })
    const wrapper = render({
      shapes: [
        line('stream', 'water'),
        line('hedge', 'hedge'),
        line('fence', 'fence'),
        shape({ id: 'hedge-block', style: 'hedge' }),
        shape({ id: 'pen', style: 'fence', location_id: 'loc-pen' }),
        shape({
          id: 'pit',
          kind: 'polygon',
          style: 'sand',
          points: [
            [0.1, 0.1],
            [0.2, 0.1],
            [0.15, 0.2],
          ],
        }),
      ],
    })
    const g = (id: string) => wrapper.get(`[data-testid="venue-shape-${id}"]`)
    // sw = 0.01 · 1000 = 10 plan units.
    expect(g('stream').get('.vs-ripple').attributes('style')).toContain('stroke-dasharray: 8 15')
    expect(g('hedge').get('polyline.vs-hedge-dots').attributes('style')).toContain(
      'stroke-width: 4.5px',
    )
    expect(g('hedge-block').get('polygon.vs-hedge-dots').attributes('points')).toBe(
      '100,100 500,100 500,500 100,500',
    )
    // The rail thins out and gets square posts every max(4·sw, 12) = 40 units.
    expect(g('fence').get('.vs-body').attributes('style')).toContain('stroke-width: 3.5px')
    const posts = g('fence').get('path.vs-fence-posts').attributes('d')!
    expect(posts.match(/M/g)).toHaveLength(26)
    // A fenced area: outline and posts all round (perimeter 1600 / 30 → 53).
    expect(g('pen').get('.vs-body').attributes('style')).toContain('stroke-width: 3px')
    expect(g('pen').get('.vs-fence-posts').attributes('d')!.match(/M/g)).toHaveLength(53)
    expect(g('pit').classes()).toContain('vs-sand')
    expect(g('pit').findAll('*').map((el) => el.element.tagName)).toEqual(['polygon'])
  })
})

describe('VenueShapeLayer decoration', () => {
  const prop = (
    id: string,
    kind: NonNullable<RenderShape['prop']>,
    overrides: Partial<RenderShape> = {},
  ) =>
    shape({
      id,
      kind: 'prop',
      style: 'green',
      prop: kind,
      rotation: 0,
      scale: 1,
      points: [[0.5, 0.5]],
      ...overrides,
    })
  // The tent comes first in sort_order but is tall, so it is drawn after the bench.
  const decor = [
    prop('tent', 'tent', { sort_order: 0, style: 'area', rotation: 30 }),
    prop('bench', 'bench', { sort_order: 9, style: 'furniture', label: 'Rest' }),
    prop('oak', 'tree', { sort_order: 1, scale: 2 }),
  ]

  function renderDecor(props: Partial<Props> = {}) {
    return render({ shapes: [room, ...decor], ...props })
  }

  it('draws props in their own layer, ground tier before tall', () => {
    const wrapper = renderDecor()
    const layer = wrapper.get('[data-layer="props"]')
    expect(layer.attributes('pointer-events')).toBe('none')
    expect(layer.findAll('.venue-prop-shape').map((g) => g.attributes('data-shape-id'))).toEqual([
      'bench',
      'tent',
      'oak',
    ])
    // Not in the ground layer.
    expect(wrapper.get('[data-layer="shapes"]').find('[data-kind="prop"]').exists()).toBe(false)
    const tent = wrapper.get('[data-testid="venue-shape-tent"]')
    expect(tent.attributes()).toMatchObject({
      'data-kind': 'prop',
      'data-prop': 'tent',
      'data-rotation': '30',
      'data-scale': '1',
      'aria-hidden': 'true',
    })
    expect(tent.attributes('role')).toBeUndefined()
    expect(tent.find('.vs-prop-hit').exists()).toBe(false)
    // Shadow, then body, each with its transform.
    const groups = tent.findAll('.venue-prop > g')
    expect(groups[0]!.classes()).toContain('vp-shadows')
    expect(groups[1]!.attributes('transform')).toMatch(/^translate\(500 500\) rotate\(30\) scale/)
    expect(tent.find('.vp-fabric').exists()).toBe(true)
  })

  it('stays inert in linked mode', async () => {
    const wrapper = renderDecor({ interactive: 'linked' })
    expect(wrapper.get('[data-layer="props"]').attributes('pointer-events')).toBe('none')
    await wrapper.get('[data-testid="venue-shape-oak"]').trigger('click')
    await wrapper.get('[data-testid="venue-shape-oak"]').trigger('pointerdown')
    const layer = wrapper.getComponent(VenueShapeLayer)
    expect(layer.emitted('select-shape')).toBeUndefined()
    expect(layer.emitted('shape-pointerdown')).toBeUndefined()
  })

  it('captions a prop below its glyph, on the ground', () => {
    const wrapper = renderDecor()
    const caption = wrapper.get('[data-testid="venue-shape-label-bench"]')
    expect(caption.text()).toBe('Rest')
    expect(caption.classes()).toEqual(expect.arrayContaining(['vs-furniture', 'vs-label-kind']))
    expect(Number(caption.attributes('y'))).toBeGreaterThan(500)
  })

  it('makes props named, focusable buttons in the editor', async () => {
    const wrapper = renderDecor({ interactive: 'all', selectedShapeIds: ['oak'] })
    expect(wrapper.get('[data-layer="props"]').attributes('pointer-events')).toBeUndefined()
    const oak = wrapper.get('[data-testid="venue-shape-oak"]')
    expect(oak.attributes()).toMatchObject({
      role: 'button',
      tabindex: '0',
      'aria-label': 'Decoration: Tree',
      'aria-pressed': 'true',
    })
    expect(wrapper.get('[data-testid="venue-shape-bench"]').attributes('aria-label')).toBe(
      'Decoration: Rest',
    )
    // tree radius 24 · k (0.055 · 1000 · 2 / 48) = 55 units; the ring sits 4px further out.
    expect(Number(oak.get('.vs-prop-hit').attributes('r'))).toBeCloseTo(55)
    expect(Number(oak.get('.vs-sel-outer').attributes('r'))).toBeCloseTo(59)
    expect(oak.find('.vs-sel-inner').exists()).toBe(true)
    expect(wrapper.get('[data-testid="venue-shape-bench"]').find('.vs-sel-outer').exists()).toBe(
      false,
    )

    await oak.trigger('pointerdown')
    await oak.trigger('click')
    await oak.trigger('keydown', { key: 'Enter' })
    const layer = wrapper.getComponent(VenueShapeLayer)
    expect(layer.emitted('shape-pointerdown')![0]![0]).toMatchObject({ id: 'oak' })
    expect(layer.emitted('select-shape')!.map(([s]) => (s as RenderShape).id)).toEqual([
      'oak',
      'oak',
    ])

    i18n.global.locale.value = 'de'
    await wrapper.vm.$nextTick()
    expect(oak.attributes('aria-label')).toBe('Deko: Laubbaum')
  })

  it('gives a tiny prop a finger-sized hit area', () => {
    const wrapper = render({
      shapes: [prop('bin', 'bin', { style: 'furniture' })],
      interactive: 'all',
      unitsPerPixel: 3,
    })
    expect(wrapper.get('.vs-prop-hit').attributes('r')).toBe('30')
  })
})
