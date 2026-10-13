// @vitest-environment jsdom
import { effectScope, nextTick, ref } from 'vue'

import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  NUDGE_DELAY,
  type PointerLike,
  type PressTarget,
  isEditableTarget,
  useShapeEditor,
} from '@/composables/useShapeEditor'
import type { ShapeCommand } from '@/composables/useShapeHistory'

import type { VenueShapeRead } from '@/client/types.gen'
import { type ShapeOp, applyOps, materialiseOps } from '@/lib/venue-shape-edit'

/**
 * A 1000×1000 plan at one unit per pixel, so a client point (x, y) is the
 * normalised point (x/1000, y/1000) and the grid (1%) is 10 px.
 */
function shape(id: string, overrides: Partial<VenueShapeRead> = {}): VenueShapeRead {
  return {
    id,
    plan_id: 'p1',
    kind: 'rect',
    style: 'room',
    points: [
      [0.2, 0.2],
      [0.4, 0.4],
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

let scope: ReturnType<typeof effectScope>

function setup(initial: VenueShapeRead[] = []) {
  const shapes = ref<VenueShapeRead[]>(initial)
  const commands: ShapeCommand[] = []
  const undo = vi.fn()
  const redo = vi.fn()
  const onLabelDraft = vi.fn()
  let n = 0
  const newId = () => `n${++n}`
  scope = effectScope()
  const editor = scope.run(() =>
    useShapeEditor({
      shapes: () => shapes.value,
      size: () => ({ W: 1000, H: 1000 }),
      upp: () => 1,
      toPoint: (x, y) => [x / 1000, y / 1000],
      execute: (cmd) => {
        commands.push(cmd)
        const ops = materialiseOps(shapes.value, cmd.ops, newId)
        shapes.value = applyOps(shapes.value, ops, 'p1')
        return ops
      },
      undo,
      redo,
      newId,
      onLabelDraft,
    }),
  )!
  return { editor, shapes, commands, undo, redo, onLabelDraft }
}

afterEach(() => {
  scope?.stop()
  vi.useRealTimers()
})

function ev(x: number, y: number, extra: Partial<PointerLike> = {}): PointerLike {
  return {
    clientX: x,
    clientY: y,
    pointerId: 1,
    pointerType: 'mouse',
    button: 0,
    shiftKey: false,
    altKey: false,
    ...extra,
  }
}

type Editor = ReturnType<typeof setup>['editor']

function drag(
  editor: Editor,
  from: [number, number],
  to: [number, number],
  target: PressTarget = null,
  extra: Partial<PointerLike> = {},
) {
  editor.onPointerDown(ev(...from, extra), target)
  editor.onPointerMove(ev(...to, extra))
  editor.onPointerUp(ev(...to, extra))
}

function click(editor: Editor, x: number, y: number, extra: Partial<PointerLike> = {}) {
  editor.onPointerDown(ev(x, y, extra))
  editor.onPointerUp(ev(x, y, extra))
}

function key(editor: Editor, k: string, init: KeyboardEventInit = {}, target?: EventTarget) {
  const event = new KeyboardEvent('keydown', { key: k, cancelable: true, ...init })
  if (target) Object.defineProperty(event, 'target', { value: target })
  return editor.onKeyDown(event)
}

const lastOp = (commands: ShapeCommand[]): ShapeOp => commands.at(-1)!.ops.at(-1)!

describe('rect tool', () => {
  it('draws a rect by dragging, snapped to the grid, and selects it', () => {
    const { editor, commands, shapes } = setup()
    editor.setTool('rect')
    editor.onPointerDown(ev(101, 103))
    editor.onPointerMove(ev(250, 180))
    expect(editor.draft.value).toMatchObject({
      tool: 'rect',
      points: [
        [0.1, 0.1],
        [0.25, 0.18],
      ],
    })
    editor.onPointerMove(ev(298, 252))
    editor.onPointerUp(ev(298, 252))
    expect(lastOp(commands)).toMatchObject({
      op: 'create',
      shape: {
        id: 'n1',
        kind: 'rect',
        style: 'room',
        points: [
          [0.1, 0.1],
          [0.3, 0.25],
        ],
      },
    })
    expect(shapes.value).toHaveLength(1)
    expect(editor.selectedId.value).toBe('n1')
    expect(editor.tool.value).toBe('rect')
    expect(editor.draft.value).toBeNull()
  })

  it('discards a click without a drag', () => {
    const { editor, commands } = setup()
    editor.setTool('rect')
    click(editor, 100, 100)
    expect(commands).toHaveLength(0)
  })

  it('draws a square with Shift and skips snapping with Alt', () => {
    const { editor, commands } = setup()
    editor.setTool('rect')
    drag(editor, [100, 100], [300, 200], null, { shiftKey: true })
    expect(lastOp(commands)).toMatchObject({
      shape: {
        points: [
          [0.1, 0.1],
          [0.3, 0.3],
        ],
      },
    })
    drag(editor, [123, 456], [301, 502], null, { altKey: true })
    expect(lastOp(commands)).toMatchObject({
      shape: {
        points: [
          [0.123, 0.456],
          [0.301, 0.502],
        ],
      },
    })
  })

  it('snaps to the corner of another shape before the grid', () => {
    const { editor, commands } = setup([
      shape('a', {
        points: [
          [0.2, 0.2],
          [0.4037, 0.4037],
        ],
      }),
    ])
    editor.setTool('rect')
    drag(editor, [100, 100], [402, 401])
    expect(lastOp(commands)).toMatchObject({
      shape: {
        points: [
          [0.1, 0.1],
          [0.4037, 0.4037],
        ],
      },
    })
  })

  it('does not snap with snapping off', () => {
    const { editor, commands } = setup()
    expect(key(editor, 'g')).toBe(true)
    expect(editor.snapEnabled.value).toBe(false)
    editor.setTool('rect')
    drag(editor, [101, 101], [203, 203])
    expect(lastOp(commands)).toMatchObject({
      shape: {
        points: [
          [0.101, 0.101],
          [0.203, 0.203],
        ],
      },
    })
    editor.toggleSnap()
    expect(editor.snapEnabled.value).toBe(true)
  })

  it('aborts on a second finger (pinch), and on pointercancel', () => {
    const { editor, commands } = setup()
    editor.setTool('rect')
    editor.onPointerDown(ev(100, 100, { pointerType: 'touch' }))
    editor.onPointerMove(ev(200, 200, { pointerType: 'touch' }))
    editor.onPointerDown(ev(300, 300, { pointerType: 'touch', pointerId: 2 }))
    expect(editor.draft.value).toBeNull()
    editor.onPointerUp(ev(200, 200, { pointerType: 'touch' }))
    editor.onPointerUp(ev(300, 300, { pointerType: 'touch', pointerId: 2 }))
    expect(commands).toHaveLength(0)

    editor.onPointerDown(ev(100, 100))
    editor.onPointerMove(ev(200, 200))
    editor.onPointerCancel(ev(200, 200))
    expect(editor.draft.value).toBeNull()
    // A move from another pointer does nothing.
    editor.onPointerDown(ev(100, 100))
    editor.onPointerMove(ev(500, 500, { pointerId: 9 }))
    expect(editor.draft.value).toMatchObject({
      points: [
        [0.1, 0.1],
        [0.1, 0.1],
      ],
    })
  })

  it('ignores the right button and presses while Space is held', () => {
    const { editor } = setup()
    editor.setTool('rect')
    editor.onPointerDown(ev(100, 100, { button: 2 }))
    editor.onPointerUp(ev(100, 100, { button: 2 }))
    expect(editor.draft.value).toBeNull()
    key(editor, ' ')
    expect(editor.spaceHeld.value).toBe(true)
    editor.onPointerDown(ev(100, 100))
    expect(editor.draft.value).toBeNull()
    editor.onPointerUp(ev(100, 100))
    editor.onKeyUp(new KeyboardEvent('keyup', { key: ' ' }))
    expect(editor.spaceHeld.value).toBe(false)
    key(editor, ' ')
    editor.onBlur()
    expect(editor.spaceHeld.value).toBe(false)
    editor.onKeyUp(new KeyboardEvent('keyup', { key: 'a' }))
  })
})

describe('polygon and path tools', () => {
  it('adds a point per click and finishes with Enter', () => {
    const { editor, commands } = setup()
    editor.setTool('polygon')
    click(editor, 100, 100)
    click(editor, 300, 100)
    // Enter with two points does not finish a polygon.
    expect(key(editor, 'Enter')).toBe(false)
    editor.onPointerMove(ev(302, 297))
    expect(editor.draft.value).toMatchObject({ hover: [0.3, 0.3] })
    click(editor, 300, 300)
    click(editor, 100, 300)
    expect(key(editor, 'Enter')).toBe(true)
    expect(lastOp(commands)).toMatchObject({
      shape: {
        kind: 'polygon',
        style: 'area',
        points: [
          [0.1, 0.1],
          [0.3, 0.1],
          [0.3, 0.3],
          [0.1, 0.3],
        ],
      },
    })
    expect(editor.draft.value).toBeNull()
  })

  it('closes when the first point is clicked again', () => {
    const { editor, commands } = setup()
    editor.setTool('polygon')
    click(editor, 100, 100)
    click(editor, 300, 100)
    click(editor, 300, 300)
    click(editor, 104, 103)
    expect(lastOp(commands)).toMatchObject({ shape: { kind: 'polygon' } })
    expect((lastOp(commands) as { shape: { points: unknown[] } }).shape.points).toHaveLength(3)
  })

  it('undoes points with Backspace, cancels with Escape', () => {
    const { editor, commands } = setup()
    editor.setTool('polygon')
    click(editor, 100, 100)
    click(editor, 200, 100)
    expect(key(editor, 'Backspace')).toBe(true)
    expect(editor.draft.value).toMatchObject({ points: [[0.1, 0.1]] })
    expect(editor.undoPoint()).toBe(true)
    expect(editor.draft.value).toBeNull()
    expect(editor.undoPoint()).toBe(false)
    click(editor, 100, 100)
    expect(key(editor, 'Escape')).toBe(true)
    expect(editor.draft.value).toBeNull()
    expect(commands).toHaveLength(0)
  })

  it('does not add a point at the end of a drag', () => {
    const { editor } = setup()
    editor.setTool('polygon')
    editor.onPointerDown(ev(100, 100))
    editor.onPointerMove(ev(150, 150))
    editor.onPointerUp(ev(150, 150))
    expect(editor.draft.value).toBeNull()
  })

  it('constrains a segment to 45° with Shift', () => {
    const { editor } = setup()
    editor.setTool('path')
    click(editor, 100, 100)
    editor.onPointerMove(ev(300, 290, { shiftKey: true }))
    const hover = (editor.draft.value as { hover: number[] }).hover
    expect(hover[0]).toBeCloseTo(hover[1]!)
    click(editor, 300, 120, { shiftKey: true })
    const pts = (editor.draft.value as { points: number[][] }).points
    expect(pts[1]![1]).toBeCloseTo(0.1)
  })

  it('finishes a path with a double click (the doubled point counts once)', () => {
    const { editor, commands } = setup()
    editor.setTool('path')
    click(editor, 100, 100)
    expect(editor.onDoubleClick()).toBe(false)
    click(editor, 300, 100)
    click(editor, 300, 100)
    expect(editor.onDoubleClick()).toBe(true)
    expect(lastOp(commands)).toMatchObject({
      shape: {
        kind: 'path',
        style: 'path',
        stroke_width: 0.02,
        points: [
          [0.1, 0.1],
          [0.3, 0.1],
        ],
      },
    })
    // Not a drawing tool: a double click is nothing.
    editor.setTool('select')
    expect(editor.onDoubleClick()).toBe(false)
    expect(editor.finishDraft()).toBe(false)
  })

  it('hovering with a drawing tool shows the snap target; leaving clears it', () => {
    const { editor } = setup()
    editor.setTool('rect')
    editor.onPointerMove(ev(101, 99))
    expect(editor.snapHit.value).toEqual({ point: [0.1, 0.1], kind: 'grid' })
    editor.onPointerLeave()
    expect(editor.snapHit.value).toBeNull()
    editor.setTool('path')
    click(editor, 100, 100)
    editor.onPointerMove(ev(200, 200))
    editor.onPointerLeave()
    expect(editor.draft.value).toMatchObject({ hover: null })
    // Leaving without a hover point changes nothing.
    editor.onPointerLeave()
    // Alt: no indicator.
    editor.onPointerMove(ev(300, 300, { altKey: true }))
    expect(editor.snapHit.value).toBeNull()
  })

  it('stops adding points at 500', () => {
    const { editor } = setup()
    editor.setTool('path')
    click(editor, 0, 0)
    const d = editor.draft.value as { points: [number, number][] }
    editor.draft.value = {
      tool: 'path',
      hover: null,
      points: Array.from({ length: 500 }, (_, i) => [i / 1000, 0] as [number, number]),
    }
    expect(d.points).toHaveLength(1)
    click(editor, 900, 900, { altKey: true })
    expect((editor.draft.value as { points: unknown[] }).points).toHaveLength(500)
  })
})

describe('label tool', () => {
  it('places a label and creates it once it has text', () => {
    const { editor, commands, onLabelDraft } = setup()
    editor.setTool('label')
    click(editor, 502, 498)
    expect(editor.draft.value).toEqual({ tool: 'label', at: [0.5, 0.5] })
    expect(onLabelDraft).toHaveBeenCalled()
    expect(editor.commitLabel('  Bar  ')).toBe('n1')
    expect(lastOp(commands)).toMatchObject({
      shape: { kind: 'label', label: 'Bar', points: [[0.5, 0.5]] },
    })
    expect(editor.commitLabel('again')).toBeNull()
  })

  it('drops a label without text', () => {
    const { editor, commands } = setup()
    editor.setTool('label')
    click(editor, 500, 500)
    expect(editor.commitLabel('   ')).toBeNull()
    expect(editor.draft.value).toBeNull()
    expect(commands).toHaveLength(0)
  })
})

describe('select tool', () => {
  it('selects a shape on press, and moves it by dragging (snapped)', () => {
    const { editor, commands } = setup([shape('a')])
    editor.onPointerDown(ev(300, 300), { type: 'shape', id: 'a' })
    expect(editor.selectedId.value).toBe('a')
    editor.onPointerMove(ev(302, 301))
    expect(editor.override.value).toBeNull()
    editor.onPointerMove(ev(351, 324))
    expect(editor.dragging.value).toBe(true)
    expect(editor.displayShapes.value[0]!.points).toEqual([
      [0.25, 0.22],
      [0.45, 0.42],
    ])
    editor.onPointerUp(ev(351, 324))
    expect(lastOp(commands)).toEqual({
      op: 'update',
      id: 'a',
      patch: {
        points: [
          [0.25, 0.22],
          [0.45, 0.42],
        ],
      },
    })
    expect(editor.override.value).toBeNull()
    expect(editor.dragging.value).toBe(false)
  })

  it('moves along one axis with Shift', () => {
    const { editor, commands } = setup([shape('a')])
    drag(editor, [300, 300], [400, 330], { type: 'shape', id: 'a' }, { shiftKey: true })
    expect(lastOp(commands)).toMatchObject({
      patch: {
        points: [
          [0.3, 0.2],
          [0.5, 0.4],
        ],
      },
    })
    drag(editor, [300, 300], [320, 400], { type: 'shape', id: 'a' }, { shiftKey: true })
    expect(lastOp(commands)).toMatchObject({
      patch: {
        points: [
          [0.3, 0.3],
          [0.5, 0.5],
        ],
      },
    })
  })

  it('a tap only selects; a press on the ground does nothing', () => {
    const { editor, commands } = setup([shape('a')])
    click(editor, 300, 300)
    expect(editor.selectedId.value).toBeNull()
    editor.onPointerDown(ev(300, 300), { type: 'shape', id: 'a' })
    editor.onPointerUp(ev(300, 300))
    expect(editor.selectedId.value).toBe('a')
    expect(commands).toHaveLength(0)
    // Unknown shape id: nothing.
    editor.onPointerDown(ev(300, 300), { type: 'shape', id: 'zzz' })
    editor.onPointerUp(ev(300, 300))
    expect(editor.selectedId.value).toBe('a')
  })

  it('resizes a rect by a handle', () => {
    const { editor, commands } = setup([shape('a')])
    editor.select('a')
    drag(editor, [400, 400], [503, 451], {
      type: 'handle',
      handle: { kind: 'resize', handle: 'se' },
    })
    expect(lastOp(commands)).toMatchObject({
      patch: {
        points: [
          [0.2, 0.2],
          [0.5, 0.45],
        ],
      },
    })
  })

  it('drags a vertex, constrained with Shift; a cancelled drag puts it back', () => {
    const poly = shape('p', {
      kind: 'polygon',
      points: [
        [0.1, 0.1],
        [0.3, 0.1],
        [0.3, 0.3],
      ],
    })
    const { editor, commands } = setup([poly])
    editor.select('p')
    drag(
      editor,
      [300, 100],
      [500, 120],
      { type: 'handle', handle: { kind: 'vertex', index: 1 } },
      {
        shiftKey: true,
      },
    )
    expect(editor.selectedVertex.value).toBe(1)
    expect(lastOp(commands)).toMatchObject({
      patch: {
        points: [
          [0.1, 0.1],
          [0.5, 0.1],
          [0.3, 0.3],
        ],
      },
    })

    editor.onPointerDown(ev(300, 300), { type: 'handle', handle: { kind: 'vertex', index: 2 } })
    editor.onPointerMove(ev(600, 600))
    expect(editor.override.value).not.toBeNull()
    editor.onPointerCancel(ev(600, 600))
    expect(editor.override.value).toBeNull()
    expect(commands).toHaveLength(1)
  })

  it('inserts a vertex from a "+" handle, even without moving it, as one step', () => {
    const path = shape('l', {
      kind: 'path',
      points: [
        [0.1, 0.1],
        [0.5, 0.1],
      ],
      stroke_width: 0.02,
    })
    const { editor, commands } = setup([path])
    editor.select('l')
    editor.onPointerDown(ev(300, 100), { type: 'handle', handle: { kind: 'insert', edgeIndex: 0 } })
    editor.onPointerUp(ev(300, 100))
    expect(commands).toHaveLength(1)
    expect(lastOp(commands)).toMatchObject({
      patch: {
        points: [
          [0.1, 0.1],
          [0.3, 0.1],
          [0.5, 0.1],
        ],
      },
    })
    expect(editor.selectedVertex.value).toBe(1)
    drag(editor, [300, 100], [300, 200], {
      type: 'handle',
      handle: { kind: 'insert', edgeIndex: 0 },
    })
    expect(lastOp(commands)).toMatchObject({
      patch: {
        points: [
          [0.1, 0.1],
          [0.3, 0.2],
          [0.3, 0.1],
          [0.5, 0.1],
        ],
      },
    })
  })

  it('moves the label anchor by its handle', () => {
    const { editor, commands } = setup([shape('a', { label: 'Hall' })])
    editor.select('a')
    drag(editor, [300, 300], [352, 251], { type: 'handle', handle: { kind: 'label' } })
    expect(lastOp(commands)).toMatchObject({ patch: { label_x: 0.35, label_y: 0.25 } })
  })

  it('a handle press without a selection does nothing', () => {
    const { editor } = setup([shape('a')])
    editor.onPointerDown(ev(300, 300), { type: 'handle', handle: { kind: 'label' } })
    editor.onPointerMove(ev(400, 400))
    expect(editor.override.value).toBeNull()
  })

  it('drops the selection when its shape goes away', async () => {
    const { editor, shapes } = setup([shape('a')])
    editor.select('a')
    shapes.value = []
    await nextTick()
    expect(editor.selectedId.value).toBeNull()
  })
})

describe('panFilter', () => {
  it('pans with the middle button and Space always, and on the ground with select', () => {
    const { editor } = setup()
    expect(editor.panFilter(ev(0, 0, { button: 1 }))).toBe(true)
    expect(editor.panFilter(ev(0, 0, { button: 2 }))).toBe(false)
    expect(editor.panFilter(ev(0, 0))).toBe(true)
    expect(editor.panFilter(ev(0, 0), { type: 'shape', id: 'a' })).toBe(false)
    editor.setTool('rect')
    expect(editor.panFilter(ev(0, 0, { pointerType: 'touch' }))).toBe(false)
    key(editor, ' ')
    expect(editor.panFilter(ev(0, 0))).toBe(true)
  })
})

describe('inspector actions', () => {
  it('updates the selection as one step and remembers the style for new shapes', () => {
    const { editor, commands } = setup([shape('a')])
    expect(editor.updateSelected({ style: 'stage' })).toBe(false)
    editor.select('a')
    expect(editor.updateSelected({ style: 'stage', label: 'Bühne' })).toBe(true)
    expect(lastOp(commands)).toEqual({
      op: 'update',
      id: 'a',
      patch: { style: 'stage', label: 'Bühne' },
    })
    expect(editor.updateSelected({ style: 'stage' })).toBe(false)
    expect(editor.lastStyle.value.rect).toBe('stage')
  })

  it('never empties a text label', () => {
    const { editor } = setup([shape('t', { kind: 'label', points: [[0.5, 0.5]], label: 'Bar' })])
    editor.select('t')
    expect(editor.updateSelected({ label: '' })).toBe(false)
  })

  it('duplicates, reorders and deletes', () => {
    const { editor, commands, shapes } = setup([shape('a'), shape('b', { sort_order: 1 })])
    expect(editor.duplicateSelected()).toBeNull()
    expect(editor.deleteSelected()).toBe(false)
    expect(editor.reorderSelected(1)).toBe(false)
    editor.select('a')
    expect(key(editor, 'd', { ctrlKey: true })).toBe(true)
    expect(editor.selectedId.value).toBe('n1')
    expect(shapes.value.find((s) => s.id === 'n1')).toMatchObject({
      sort_order: 2,
      points: [
        [0.24, 0.24],
        [0.44, 0.44],
      ],
    })
    expect(key(editor, '[')).toBe(true)
    expect(shapes.value.map((s) => s.id)).toEqual(['a', 'n1', 'b'])
    expect(key(editor, ']')).toBe(true)
    expect(key(editor, ']')).toBe(false)
    expect(key(editor, 'Delete')).toBe(true)
    expect(shapes.value.map((s) => s.id)).toEqual(['a', 'b'])
    expect(editor.selectedId.value).toBeNull()
    expect(commands.map((c) => c.label)).toEqual(['duplicate', 'reorder', 'reorder', 'delete'])
  })

  it('removes the selected vertex, but not below the minimum', () => {
    const poly = shape('p', {
      kind: 'polygon',
      points: [
        [0.1, 0.1],
        [0.3, 0.1],
        [0.3, 0.3],
        [0.1, 0.3],
      ],
    })
    const { editor, shapes } = setup([poly])
    expect(editor.removeSelectedVertex()).toBe(false)
    editor.select('p')
    editor.selectedVertex.value = 0
    expect(key(editor, 'Backspace')).toBe(true)
    expect(shapes.value[0]!.points).toHaveLength(3)
    expect(editor.selectedVertex.value).toBeNull()
    editor.selectedVertex.value = 0
    // At the minimum, Delete removes the whole shape instead.
    expect(key(editor, 'Delete')).toBe(true)
    expect(shapes.value).toHaveLength(0)
  })
})

describe('keyboard', () => {
  it('switches tools and ignores keys typed into fields', () => {
    const { editor } = setup()
    for (const [k, tool] of [
      ['r', 'rect'],
      ['P', 'polygon'],
      ['l', 'path'],
      ['t', 'label'],
      ['v', 'select'],
    ] as const) {
      expect(key(editor, k)).toBe(true)
      expect(editor.tool.value).toBe(tool)
    }
    const input = document.createElement('input')
    expect(key(editor, 'r', {}, input)).toBe(false)
    expect(editor.tool.value).toBe('select')
    const prevented = new KeyboardEvent('keydown', { key: 'r', cancelable: true })
    prevented.preventDefault()
    expect(editor.onKeyDown(prevented)).toBe(false)
    // Unknown keys and other modifier combinations are left alone.
    expect(key(editor, 'x')).toBe(false)
    expect(key(editor, 'Tab')).toBe(false)
    expect(key(editor, 'r', { altKey: true })).toBe(false)
    expect(key(editor, 's', { ctrlKey: true })).toBe(false)
  })

  it('undoes and redoes', () => {
    const { editor, undo, redo } = setup()
    key(editor, 'z', { ctrlKey: true })
    key(editor, 'Z', { metaKey: true, shiftKey: true })
    key(editor, 'y', { ctrlKey: true })
    expect(undo).toHaveBeenCalledTimes(1)
    expect(redo).toHaveBeenCalledTimes(2)
  })

  it('commits a pending nudge before undoing, so the nudge is what gets undone', () => {
    vi.useFakeTimers()
    const { editor, commands, undo, redo } = setup([shape('a')])
    editor.select('a')
    key(editor, 'ArrowRight')
    const order: string[] = []
    undo.mockImplementation(() => order.push(`undo after ${commands.length}`))
    key(editor, 'z', { ctrlKey: true })
    expect(commands.map((c) => c.label)).toEqual(['nudge'])
    expect(order).toEqual(['undo after 1'])
    // Nothing left to commit later, which would wipe the redo stack.
    vi.advanceTimersByTime(NUDGE_DELAY + 10)
    expect(commands).toHaveLength(1)
    expect(editor.override.value).toBeNull()

    // The toolbar goes through the same path.
    key(editor, 'ArrowLeft')
    editor.redo()
    expect(commands.map((c) => c.label)).toEqual(['nudge', 'nudge'])
    expect(redo).toHaveBeenCalledTimes(1)
  })

  it('drops a drag in flight before undoing', () => {
    const { editor, commands, undo } = setup([shape('a')])
    editor.onPointerDown(ev(300, 300), { type: 'shape', id: 'a' })
    editor.onPointerMove(ev(400, 400))
    expect(editor.dragging.value).toBe(true)
    editor.undo()
    expect(undo).toHaveBeenCalledTimes(1)
    expect(editor.dragging.value).toBe(false)
    editor.onPointerUp(ev(400, 400))
    expect(commands).toHaveLength(0)
  })

  it('Space on a button is the button’s', () => {
    const { editor } = setup()
    const button = document.createElement('button')
    expect(key(editor, ' ', {}, button)).toBe(false)
  })

  it('nudges by grid steps, saving one burst as one step', () => {
    vi.useFakeTimers()
    const { editor, commands } = setup([shape('a')])
    expect(key(editor, 'ArrowRight')).toBe(false)
    editor.select('a')
    key(editor, 'ArrowRight')
    key(editor, 'ArrowDown', { shiftKey: true })
    expect(commands).toHaveLength(0)
    expect(editor.displayShapes.value[0]!.points[0]).toEqual([0.21, 0.24])
    vi.advanceTimersByTime(NUDGE_DELAY + 10)
    expect(commands).toHaveLength(1)
    expect(lastOp(commands)).toMatchObject({
      patch: {
        points: [
          [0.21, 0.24],
          [0.41, 0.44],
        ],
      },
    })

    // A burst is flushed before any other command, and when the selection changes.
    key(editor, 'ArrowLeft')
    editor.updateSelected({ label: 'x' })
    expect(commands.map((c) => c.label)).toEqual(['nudge', 'nudge', 'edit'])
    key(editor, 'ArrowUp')
    editor.select(null)
    expect(commands).toHaveLength(4)
    editor.flushNudge()
    expect(commands).toHaveLength(4)
  })

  it('Escape cancels a draft, then the vertex, then the selection', () => {
    const { editor } = setup([shape('a')])
    editor.select('a')
    editor.selectedVertex.value = 1
    expect(key(editor, 'Escape')).toBe(true)
    expect(editor.selectedVertex.value).toBeNull()
    expect(key(editor, 'Escape')).toBe(true)
    expect(editor.selectedId.value).toBeNull()
    expect(key(editor, 'Escape')).toBe(false)
  })

  it('Escape also ends a drag', () => {
    const { editor, commands } = setup([shape('a')])
    editor.onPointerDown(ev(300, 300), { type: 'shape', id: 'a' })
    editor.onPointerMove(ev(400, 400))
    expect(key(editor, 'Escape')).toBe(true)
    editor.onPointerUp(ev(400, 400))
    expect(commands).toHaveLength(0)
    // A nudge waits while dragging.
    editor.select('a')
    editor.onPointerDown(ev(300, 300), { type: 'shape', id: 'a' })
    expect(editor.nudgeSelected(1, 0)).toBe(false)
  })
})

describe('isEditableTarget', () => {
  it('recognises fields', () => {
    expect(isEditableTarget(null)).toBe(false)
    expect(isEditableTarget(window)).toBe(false)
    expect(isEditableTarget(document.createElement('textarea'))).toBe(true)
    const div = document.createElement('div')
    Object.defineProperty(div, 'isContentEditable', { value: true })
    expect(isEditableTarget(div)).toBe(true)
    expect(isEditableTarget(document.createElement('div'))).toBe(false)
  })
})
