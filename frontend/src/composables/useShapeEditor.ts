import { computed, onScopeDispose, ref, shallowRef, watch } from 'vue'

import type { ShapeCommand } from '@/composables/useShapeHistory'

import type { VenueShapeRead, VenueShapeUpdate } from '@/client/types.gen'
import {
  LINE_PRESETS,
  PROP_META,
  type PropType,
  ROTATION_STEP,
  clampPropScale,
  normaliseRotation,
} from '@/lib/venue-decor'
import {
  MIN_POINTS,
  PROP_STYLE,
  type Pt,
  type RectHandle,
  SNAP_RADIUS_PX,
  type ShapeKind,
  type ShapeOp,
  axisLock,
  clampPt,
  constrainAngle,
  dedupePoints,
  diffShape,
  duplicateShape,
  gridStep,
  insertVertex,
  moveShape,
  moveVertex,
  newShapeId,
  nextSortOrder,
  rectFromDrag,
  rectIsBigEnough,
  removeVertex,
  reorderOps,
  resizeRect,
  roundPoints,
  shapeToCreate,
  shapeVertices,
  snapPoint,
} from '@/lib/venue-shape-edit'
import { labelAnchor } from '@/lib/venue-shapes'

export type Tool = 'select' | 'rect' | 'polygon' | 'path' | 'label' | 'prop'
export type LinePresetKey = keyof typeof LINE_PRESETS
export type ShapeStyle = VenueShapeRead['style']

export type Draft =
  | { tool: 'rect'; start: Pt; current: Pt; points: Pt[] }
  | { tool: 'polygon' | 'path'; points: Pt[]; hover: Pt | null }
  | { tool: 'label'; at: Pt }

/** What a press landed on: a handle of the selected shape, a shape, or the ground. */
export type HandleTarget =
  | { kind: 'vertex'; index: number }
  | { kind: 'resize'; handle: RectHandle }
  | { kind: 'insert'; edgeIndex: number }
  | { kind: 'label' }
export type PressTarget =
  { type: 'handle'; handle: HandleTarget } | { type: 'shape'; id: string } | null

type Drag = {
  kind: 'move' | 'vertex' | 'resize' | 'label'
  pointerId: number
  id: string
  /** The shape as it was before the drag — what the command diffs against. */
  origin: VenueShapeRead
  /** What the drag modifies (the origin, or the origin with an inserted vertex). */
  base: VenueShapeRead
  index: number
  handle: RectHandle
  start: Pt
  startClient: { x: number; y: number }
  moved: boolean
  /** Commit even without movement (a vertex inserted by pressing "+"). */
  force: boolean
}

type Tap = { pointerId: number; startClient: { x: number; y: number }; moved: boolean }

/** Movement (CSS px) after which a press counts as a drag. */
export const DRAG_THRESHOLD = 4
/** A burst of arrow presses is one command. */
export const NUDGE_DELAY = 400

export const TOOL_KEYS: Record<string, Tool> = {
  v: 'select',
  r: 'rect',
  p: 'polygon',
  l: 'path',
  t: 'label',
  d: 'prop',
}

/** The style a new shape of each kind starts with (= `DEFAULT_STYLE` of the renderer). */
export const NEW_SHAPE_STYLE: Record<ShapeKind, ShapeStyle> = {
  rect: 'room',
  polygon: 'area',
  path: 'path',
  label: 'room',
  prop: 'green',
}

export const DEFAULT_PATH_WIDTH = 0.02
/** Q/E with Shift turn a decoration by this much instead of `ROTATION_STEP`. */
export const FINE_ROTATION_STEP = 1
/** `+`/`-` grow or shrink a decoration by this factor. */
export const SCALE_STEP = 1.1

export type PointerLike = Pick<
  PointerEvent,
  'clientX' | 'clientY' | 'pointerId' | 'pointerType' | 'button' | 'shiftKey' | 'altKey'
>

export interface ShapeEditorOptions {
  /** The current (optimistic) shapes of the plan, in z order. */
  shapes: () => readonly VenueShapeRead[]
  /** The plan's effective size in plan units. */
  size: () => { W: number; H: number }
  /** Plan units per CSS pixel at the current zoom. */
  upp: () => number
  /** A client point → normalised plan coordinates (may lie outside 0..1). */
  toPoint: (clientX: number, clientY: number) => Pt
  execute: (command: ShapeCommand) => ShapeOp[] | null
  undo: () => void
  redo: () => void
  newId?: () => string
  /** A label was placed and waits for its text. */
  onLabelDraft?: () => void
  /** Random number in [0, 1) for the turn of a new tree or bush (tests pass their own). */
  random?: () => number
}

function roundScale(scale: number): number {
  return Math.round(scale * 1000) / 1000
}

function roundPt(p: Pt): Pt {
  return [Math.round(p[0] * 1e5) / 1e5, Math.round(p[1] * 1e5) / 1e5]
}

export function isEditableTarget(target: EventTarget | null): boolean {
  if (!target || typeof (target as Element).closest !== 'function') return false
  const el = target as HTMLElement
  if (el.isContentEditable) return true
  return !!el.closest('input, textarea, select, [contenteditable="true"]')
}

/**
 * The drawing tools of the venue map editor (#185 phase 2): which tool is
 * active, what is selected, the shape being drawn, drags of shapes and
 * handles, snapping, and the keyboard shortcuts.
 *
 * It does not save anything itself: every finished edit becomes one command
 * for `execute` (the history), so each step can be undone. While a drag or a
 * burst of arrow presses is still going on, the edited shape is shown from
 * `override` — `displayShapes` is what to render.
 *
 * Snapping (toggle `snapEnabled`, key G) goes to the vertices of other shapes
 * within 8 px first, else to a grid of 1% of the plan's shorter side. Alt
 * bypasses it; Shift constrains instead (45° segments, square rects, moves
 * along one axis).
 */
export function useShapeEditor(options: ShapeEditorOptions) {
  const newId = options.newId ?? newShapeId
  const random = options.random ?? Math.random

  const tool = ref<Tool>('select')
  const selectedId = ref<string | null>(null)
  const selectedVertex = ref<number | null>(null)
  const draft = ref<Draft | null>(null)
  const snapEnabled = ref(true)
  const snapHit = ref<{ point: Pt; kind: 'vertex' | 'grid' } | null>(null)
  const spaceHeld = ref(false)
  const override = shallowRef<VenueShapeRead | null>(null)
  const dragging = ref(false)
  /** The style each kind was last given, so the next one starts like it. */
  const lastStyle = ref<Record<ShapeKind, ShapeStyle>>({ ...NEW_SHAPE_STYLE })
  /** The decoration the Deko tool places. */
  const activeProp = ref<PropType>('tree')
  /** The size each kind of decoration was last given, so the next one matches. */
  const lastPropScale = ref<Partial<Record<PropType, number>>>({})
  /**
   * Width the Deko palette picked for the lines drawn next. One-shot: any
   * `setTool` clears it, after which a new line's width follows its style.
   */
  const pathPreset = ref<{ style: ShapeStyle; strokeWidth: number } | null>(null)
  /** Where the Deko tool would place, for its ghost preview (normalised). */
  const propHover = ref<Pt | null>(null)

  let drag: Drag | null = null
  let tap: Tap | null = null
  const down = new Set<number>()
  let nudge: { id: string; origin: VenueShapeRead } | null = null
  let nudgeTimer: ReturnType<typeof setTimeout> | undefined

  const displayShapes = computed<VenueShapeRead[]>(() => {
    const o = override.value
    const list = options.shapes()
    return o ? list.map((s) => (s.id === o.id ? o : s)) : [...list]
  })

  const selected = computed(
    () => displayShapes.value.find((s) => s.id === selectedId.value) ?? null,
  )

  const grid = computed(() => {
    const { W, H } = options.size()
    return gridStep(W, H)
  })

  // A shape that went away (undo, rollback, another plan) cannot stay selected.
  watch(
    () => !!selectedId.value && !options.shapes().some((s) => s.id === selectedId.value),
    (gone) => {
      if (gone && !override.value) select(null)
    },
  )

  // ── Commands ────────────────────────────────────────────────────────────
  function run(label: string, ops: ShapeOp[]) {
    flushNudge()
    return options.execute({ label, ops })
  }

  function select(id: string | null) {
    if (id !== selectedId.value) flushNudge()
    selectedId.value = id
    selectedVertex.value = null
  }

  function setTool(next: Tool) {
    flushNudge()
    cancelDraft()
    cancelDrag()
    propHover.value = null
    pathPreset.value = null
    tool.value = next
  }

  /** The Deko tool with `prop` ready to place. */
  function pickProp(prop: PropType) {
    if (tool.value !== 'prop') setTool('prop')
    activeProp.value = prop
  }

  /** The line tool, drawing a hedge, a fence, a stream or a path. */
  function pickLinePreset(key: LinePresetKey) {
    const preset = LINE_PRESETS[key]
    setTool('path')
    lastStyle.value = { ...lastStyle.value, path: preset.style }
    pathPreset.value = { style: preset.style, strokeWidth: preset.strokeWidth }
  }

  /** The shape tool, drawing an area of `style` (a sandpit). */
  function pickAreaPreset(style: Extract<ShapeStyle, 'sand'>) {
    setTool('polygon')
    lastStyle.value = { ...lastStyle.value, polygon: style }
  }

  function toggleSnap() {
    snapEnabled.value = !snapEnabled.value
  }

  function createShape(
    kind: ShapeKind,
    points: Pt[],
    extra: {
      label?: string | null
      label_size?: 'sm' | 'md' | 'lg'
      prop?: PropType
      rotation?: number
      scale?: number
    } = {},
  ) {
    const id = newId()
    const style = kind === 'prop' && extra.prop ? PROP_STYLE[extra.prop] : lastStyle.value[kind]
    const ops = run(`create-${kind}`, [
      {
        op: 'create',
        shape: {
          id,
          kind,
          style,
          points,
          ...(kind === 'path' ? { stroke_width: newLineWidth(style) } : {}),
          ...extra,
        },
      },
    ])
    if (ops) select(id)
    return ops ? id : null
  }

  /**
   * Width of a new line: the palette preset while it is active, else the
   * preset width of a decor line style (hedge, fence, stream), else the default.
   */
  function newLineWidth(style: ShapeStyle): number {
    if (pathPreset.value) return pathPreset.value.strokeWidth
    if (style !== 'path' && style in LINE_PRESETS)
      return LINE_PRESETS[style as LinePresetKey].strokeWidth
    return DEFAULT_PATH_WIDTH
  }

  /** Change fields of the selected shape as one undoable step. */
  function updateSelected(patch: VenueShapeUpdate, label = 'edit') {
    const shape = selected.value
    if (!shape) return false
    let next = { ...shape, ...patch } as VenueShapeRead
    if (shape.kind === 'label' && !next.label?.trim()) return false
    if (shape.kind === 'prop') {
      // A decoration's look follows its type; it keeps its place, turn and size.
      next = {
        ...next,
        style: next.prop ? PROP_STYLE[next.prop] : shape.style,
        rotation: normaliseRotation(next.rotation ?? 0),
        scale: roundScale(clampPropScale(next.scale ?? 1)),
      }
    }
    const diff = diffShape(shape, next)
    if (!diff) return false
    if (diff.style && shape.kind !== 'prop') {
      lastStyle.value = { ...lastStyle.value, [shape.kind]: diff.style }
    }
    run(label, [{ op: 'update', id: shape.id, patch: diff }])
    if (shape.kind === 'prop' && diff.scale != null && next.prop)
      rememberScale(next.prop, diff.scale)
    return true
  }

  function rememberScale(prop: PropType, scale: number) {
    lastPropScale.value = { ...lastPropScale.value, [prop]: scale }
  }

  /** Turn the selected decoration to `deg` degrees (clockwise), as one step. */
  function setSelectedRotation(deg: number) {
    if (selected.value?.kind !== 'prop') return false
    return updateSelected({ rotation: normaliseRotation(deg) }, 'rotate')
  }

  /** Give the selected decoration size factor `scale`, as one step. */
  function setSelectedScale(scale: number) {
    if (selected.value?.kind !== 'prop') return false
    return updateSelected({ scale: roundScale(clampPropScale(scale)) }, 'scale')
  }

  function deleteSelected() {
    const shape = selected.value
    if (!shape) return false
    run('delete', [{ op: 'delete', id: shape.id }])
    select(null)
    return true
  }

  function removeSelectedVertex() {
    const shape = selected.value
    const index = selectedVertex.value
    if (!shape || index == null) return false
    const next = removeVertex(shape, index)
    if (next === shape) return false
    run('remove-vertex', [
      { op: 'update', id: shape.id, patch: { points: roundPoints(next.points) } },
    ])
    selectedVertex.value = null
    return true
  }

  function duplicateSelected() {
    const shape = selected.value
    if (!shape) return null
    const id = newId()
    const { gx, gy } = grid.value
    const copy = duplicateShape(
      shape,
      id,
      { dx: gx * 4, dy: gy * 4 },
      nextSortOrder(options.shapes()),
    )
    run('duplicate', [{ op: 'create', shape: shapeToCreate(copy) }])
    select(id)
    return id
  }

  function reorderSelected(direction: 1 | -1) {
    const shape = selected.value
    if (!shape) return false
    const ops = reorderOps(options.shapes(), shape.id, direction)
    if (ops.length === 0) return false
    run('reorder', ops)
    return true
  }

  // ── History ─────────────────────────────────────────────────────────────
  /**
   * Undo/redo work on committed steps only: a pending arrow nudge is committed
   * first (so it is what gets undone), and a drag in flight is dropped, since
   * its origin would no longer match the shapes after the undo.
   */
  function settleTransient() {
    flushNudge()
    abortGesture()
  }

  function undo() {
    settleTransient()
    options.undo()
  }

  function redo() {
    settleTransient()
    options.redo()
  }

  // ── Nudging, turning, resizing by key ───────────────────────────────────
  /**
   * A transient edit of the selected shape: shown from `override` at once, and
   * committed as one command once the keys rest for `NUDGE_DELAY` (or anything
   * else happens). Moves, turns and size changes of one burst add up.
   */
  function editTransient(change: (shape: VenueShapeRead) => VenueShapeRead): boolean {
    const shape = selected.value
    if (!shape || drag) return false
    if (!nudge || nudge.id !== shape.id) {
      flushNudge()
      nudge = { id: shape.id, origin: shape }
    }
    override.value = change(override.value ?? shape)
    clearTimeout(nudgeTimer)
    nudgeTimer = setTimeout(flushNudge, NUDGE_DELAY)
    return true
  }

  function nudgeSelected(stepsX: number, stepsY: number) {
    const { gx, gy } = grid.value
    return editTransient((s) => moveShape(s, stepsX * gx, stepsY * gy))
  }

  /** Turn the selected decoration by `deltaDeg` (clockwise); a burst is one step. */
  function rotateSelected(deltaDeg: number) {
    if (selected.value?.kind !== 'prop') return false
    return editTransient((s) => ({
      ...s,
      rotation: normaliseRotation((s.rotation ?? 0) + deltaDeg),
    }))
  }

  /** Grow (`factor` > 1) or shrink the selected decoration; a burst is one step. */
  function scaleSelected(factor: number) {
    if (selected.value?.kind !== 'prop') return false
    return editTransient((s) => ({
      ...s,
      scale: roundScale(clampPropScale((s.scale ?? 1) * factor)),
    }))
  }

  function flushNudge() {
    clearTimeout(nudgeTimer)
    nudgeTimer = undefined
    const pending = nudge
    if (!pending) return
    nudge = null
    const moved = override.value
    override.value = null
    if (!moved) return
    const patch = diffShape(pending.origin, moved)
    if (!patch) return
    options.execute({ label: 'nudge', ops: [{ op: 'update', id: pending.id, patch }] })
    if (moved.kind === 'prop' && patch.scale != null && moved.prop) {
      rememberScale(moved.prop, patch.scale)
    }
  }

  // ── Snapping ────────────────────────────────────────────────────────────
  function vertexCandidates(excludeId: string | null, extra: Pt[] = []): Pt[] {
    const out: Pt[] = [...extra]
    for (const s of displayShapes.value) {
      if (s.id === excludeId || s.kind === 'label') continue
      out.push(...shapeVertices(s))
    }
    return out
  }

  function snap(p: Pt, alt: boolean, vertices: Pt[], useGrid = true): Pt {
    const clamped = clampPt(p)
    if (!snapEnabled.value || alt) {
      snapHit.value = null
      return clamped
    }
    const { W, H } = options.size()
    const res = snapPoint(clamped, {
      grid: useGrid ? grid.value : undefined,
      vertices,
      upp: options.upp(),
      W,
      H,
    })
    snapHit.value = res.snappedTo ? { point: res.point, kind: res.snappedTo } : null
    return res.point
  }

  function pointOf(e: PointerLike): Pt {
    return options.toPoint(e.clientX, e.clientY)
  }

  // ── Drafts ──────────────────────────────────────────────────────────────
  function cancelDraft() {
    draft.value = null
    tap = null
    snapHit.value = null
  }

  /** Finish the polygon or path being drawn; false while it has too few points. */
  function finishDraft(): boolean {
    const d = draft.value
    if (!d || (d.tool !== 'polygon' && d.tool !== 'path')) return false
    const points = dedupePoints(d.points)
    if (points.length < MIN_POINTS[d.tool]) return false
    draft.value = null
    snapHit.value = null
    createShape(d.tool, points)
    return true
  }

  function undoPoint(): boolean {
    const d = draft.value
    if (!d || (d.tool !== 'polygon' && d.tool !== 'path') || d.points.length === 0) return false
    const points = d.points.slice(0, -1)
    draft.value = points.length > 0 ? { ...d, points } : null
    return true
  }

  /** Text for a placed label; empty text drops it. */
  function commitLabel(text: string) {
    const d = draft.value
    if (!d || d.tool !== 'label') return null
    draft.value = null
    const label = text.trim()
    if (!label) return null
    return createShape('label', [d.at], { label })
  }

  function addDraftPoint(e: PointerLike) {
    const d = draft.value
    const { W, H } = options.size()
    const drawing = d && (d.tool === 'polygon' || d.tool === 'path') ? d.points : []
    let p = snap(pointOf(e), e.altKey, vertexCandidates(null, drawing))
    const last = drawing[drawing.length - 1]
    if (e.shiftKey && last) p = constrainAngle(last, p, W, H)

    const kind = tool.value as 'polygon' | 'path'
    const first = drawing[0]
    if (kind === 'polygon' && first && drawing.length >= 3) {
      const radius = SNAP_RADIUS_PX * options.upp()
      if (Math.hypot((p[0] - first[0]) * W, (p[1] - first[1]) * H) <= radius) {
        finishDraft()
        return
      }
    }
    if (drawing.length >= 500) return
    draft.value = { tool: kind, points: [...drawing, p], hover: null }
  }

  // ── Drags ───────────────────────────────────────────────────────────────
  function cancelDrag() {
    if (drag) override.value = null
    drag = null
    dragging.value = false
  }

  function abortGesture() {
    cancelDrag()
    tap = null
    if (draft.value?.tool === 'rect') draft.value = null
    snapHit.value = null
  }

  function armDrag(e: PointerLike, target: PressTarget, shape: VenueShapeRead) {
    const start = pointOf(e)
    let base = shape
    let kind: Drag['kind'] = 'move'
    let index = -1
    let handle: RectHandle = 'se'
    let force = false
    if (target?.type === 'handle') {
      const h = target.handle
      if (h.kind === 'vertex') {
        kind = 'vertex'
        index = h.index
        selectedVertex.value = h.index
      } else if (h.kind === 'resize') {
        kind = 'resize'
        handle = h.handle
      } else if (h.kind === 'insert') {
        kind = 'vertex'
        index = h.edgeIndex + 1
        base = insertVertex(shape, h.edgeIndex, clampPt(start))
        force = base !== shape
        selectedVertex.value = force ? index : null
        if (force) override.value = base
      } else {
        kind = 'label'
      }
    }
    drag = {
      kind,
      pointerId: e.pointerId,
      id: shape.id,
      origin: shape,
      base,
      index,
      handle,
      start,
      startClient: { x: e.clientX, y: e.clientY },
      moved: false,
      force,
    }
  }

  function dragTo(e: PointerLike) {
    if (!drag) return
    const { W, H } = options.size()
    const p = pointOf(e)
    const d = drag
    let next: VenueShapeRead
    if (d.kind === 'move') {
      const raw: [number, number] = [p[0] - d.start[0], p[1] - d.start[1]]
      const [lx, ly] = e.shiftKey ? axisLock(raw[0], raw[1], W, H) : raw
      if (d.origin.kind === 'prop') {
        // Decoration goes exactly where it is put: no snapping.
        override.value = moveShape(d.origin, lx, ly)
        return
      }
      // Snap the shape's first corner, and move the whole shape by as much.
      const anchor = shapeVertices(d.origin)[0]!
      const target = snap([anchor[0] + lx, anchor[1] + ly], e.altKey, vertexCandidates(d.id))
      const dx = e.shiftKey && lx === 0 ? 0 : target[0] - anchor[0]
      const dy = e.shiftKey && ly === 0 ? 0 : target[1] - anchor[1]
      next = moveShape(d.origin, dx, dy)
    } else if (d.kind === 'vertex') {
      const own = d.base.points.filter((_, i) => i !== d.index).map((q) => [q[0]!, q[1]!] as Pt)
      let q = snap(p, e.altKey, vertexCandidates(d.id, own))
      const prev = d.base.points[d.index - 1]
      if (e.shiftKey && prev) q = constrainAngle([prev[0]!, prev[1]!], q, W, H)
      next = moveVertex(d.base, d.index, q)
    } else if (d.kind === 'resize') {
      next = resizeRect(d.base, d.handle, snap(p, e.altKey, vertexCandidates(d.id)))
    } else {
      // The caption follows the pointer's movement, wherever its handle was grabbed.
      const a = labelAnchor(d.base, W, H)
      const q = snap([a.x + p[0] - d.start[0], a.y + p[1] - d.start[1]], e.altKey, [])
      next = { ...d.base, label_x: q[0], label_y: q[1] }
    }
    override.value = next
  }

  function commitDrag() {
    const d = drag
    drag = null
    dragging.value = false
    snapHit.value = null
    if (!d) return
    const result = override.value
    override.value = null
    if (!result || (!d.moved && !d.force)) return
    const patch = diffShape(d.origin, result)
    if (patch)
      options.execute({ label: `drag-${d.kind}`, ops: [{ op: 'update', id: d.id, patch }] })
  }

  // ── Pointer events ──────────────────────────────────────────────────────
  /**
   * Whether `usePanZoom` may pan for this press: the middle mouse button and
   * Space+drag always; with the select tool, a press on the ground. Drawing
   * tools draw with the first finger or the primary button instead.
   */
  function panFilter(e: PointerLike, target: PressTarget = null): boolean {
    if (e.pointerType === 'mouse' && e.button === 1) return true
    if (e.pointerType === 'mouse' && e.button !== 0) return false
    if (spaceHeld.value) return true
    // The Deko tool places with a tap, so a drag may pan — except on a decoration.
    if (tool.value === 'prop') return !isPropTarget(target)
    if (tool.value !== 'select') return false
    return target === null
  }

  function isPropTarget(target: PressTarget): boolean {
    if (target?.type !== 'shape') return false
    return displayShapes.value.some((s) => s.id === target.id && s.kind === 'prop')
  }

  function onPointerDown(e: PointerLike, target: PressTarget = null) {
    down.add(e.pointerId)
    if (down.size > 1) {
      // A second finger: this is a pinch, not an edit.
      abortGesture()
      return
    }
    if (e.pointerType === 'mouse' && e.button !== 0) return
    if (spaceHeld.value) return
    flushNudge()

    // With the Deko tool a press on a decoration picks it up, like the select tool.
    if (tool.value === 'select' || (tool.value === 'prop' && isPropTarget(target))) {
      if (!target) return
      const id = target.type === 'shape' ? target.id : selectedId.value
      const shape = displayShapes.value.find((s) => s.id === id)
      if (!shape) return
      if (target.type === 'shape' && id !== selectedId.value) select(id)
      if (target.type === 'shape') selectedVertex.value = null
      armDrag(e, target, shape)
      return
    }

    if (tool.value === 'rect') {
      const start = snap(pointOf(e), e.altKey, vertexCandidates(null))
      draft.value = { tool: 'rect', start, current: start, points: [start, start] }
      tap = { pointerId: e.pointerId, startClient: { x: e.clientX, y: e.clientY }, moved: false }
      return
    }
    tap = { pointerId: e.pointerId, startClient: { x: e.clientX, y: e.clientY }, moved: false }
  }

  function onPointerMove(e: PointerLike) {
    const { W, H } = options.size()
    if (drag && e.pointerId === drag.pointerId) {
      if (!drag.moved) {
        const dist = Math.hypot(e.clientX - drag.startClient.x, e.clientY - drag.startClient.y)
        if (dist <= DRAG_THRESHOLD) return
        drag.moved = true
        dragging.value = true
      }
      dragTo(e)
      return
    }
    if (tap && e.pointerId === tap.pointerId && !tap.moved) {
      const dist = Math.hypot(e.clientX - tap.startClient.x, e.clientY - tap.startClient.y)
      if (dist > DRAG_THRESHOLD) tap.moved = true
    }
    const d = draft.value
    if (d?.tool === 'rect') {
      if (!tap || e.pointerId !== tap.pointerId) return
      const current = snap(pointOf(e), e.altKey, vertexCandidates(null))
      draft.value = {
        ...d,
        current,
        points: rectFromDrag(d.start, current, { square: e.shiftKey, W, H }),
      }
      return
    }
    if (d && (d.tool === 'polygon' || d.tool === 'path')) {
      let hover = snap(pointOf(e), e.altKey, vertexCandidates(null, d.points))
      const last = d.points[d.points.length - 1]
      if (e.shiftKey && last) hover = constrainAngle(last, hover, W, H)
      draft.value = { ...d, hover }
      return
    }
    if (tool.value === 'prop') {
      if (down.size === 0) {
        const p = pointOf(e)
        propHover.value = isOnPlan(p) ? p : null
      }
      return
    }
    if (tool.value !== 'select' && down.size === 0) {
      // Hovering with a drawing tool: show where a click would snap to.
      snap(pointOf(e), e.altKey, vertexCandidates(null))
    }
  }

  function isOnPlan(p: Pt): boolean {
    return p[0] >= 0 && p[0] <= 1 && p[1] >= 0 && p[1] <= 1
  }

  /** Place the active decoration where the tap landed (no snapping). */
  function placeProp(e: PointerLike) {
    const p = pointOf(e)
    if (!isOnPlan(p)) return null
    const prop = activeProp.value
    const rotation = PROP_META[prop].randomRotation
      ? Math.floor(random() * (360 / ROTATION_STEP)) * ROTATION_STEP
      : 0
    const scale = lastPropScale.value[prop] ?? 1
    return createShape('prop', [roundPt(p)], { prop, rotation, scale })
  }

  function onPointerUp(e: PointerLike) {
    const wasDown = down.delete(e.pointerId)
    if (drag && e.pointerId === drag.pointerId) {
      commitDrag()
      return
    }
    if (!tap || e.pointerId !== tap.pointerId || !wasDown) return
    const t = tap
    tap = null
    const d = draft.value
    if (tool.value === 'rect' && d?.tool === 'rect') {
      draft.value = null
      snapHit.value = null
      const points = d.points
      if (rectIsBigEnough(points)) createShape('rect', points)
      return
    }
    if (t.moved) return
    if (tool.value === 'polygon' || tool.value === 'path') {
      addDraftPoint(e)
    } else if (tool.value === 'prop') {
      placeProp(e)
    } else if (tool.value === 'label') {
      draft.value = { tool: 'label', at: snap(pointOf(e), e.altKey, []) }
      snapHit.value = null
      options.onLabelDraft?.()
    }
  }

  function onPointerCancel(e: PointerLike) {
    down.delete(e.pointerId)
    if (drag && e.pointerId === drag.pointerId) cancelDrag()
    if (tap && e.pointerId === tap.pointerId) {
      tap = null
      if (draft.value?.tool === 'rect') draft.value = null
    }
  }

  function onDoubleClick() {
    if (tool.value === 'path' || tool.value === 'polygon') return finishDraft()
    return false
  }

  /** The pointer left the plan: no snap indicator, no rubber band to nowhere. */
  function onPointerLeave() {
    propHover.value = null
    if (!drag && !tap) snapHit.value = null
    const d = draft.value
    if (d && (d.tool === 'polygon' || d.tool === 'path') && d.hover) {
      draft.value = { ...d, hover: null }
    }
  }

  // ── Keyboard ────────────────────────────────────────────────────────────
  const ARROWS: Record<string, [number, number]> = {
    ArrowLeft: [-1, 0],
    ArrowRight: [1, 0],
    ArrowUp: [0, -1],
    ArrowDown: [0, 1],
  }

  /** Handle a key; returns true (and prevents the default) when it was a shortcut. */
  function onKeyDown(e: KeyboardEvent): boolean {
    if (e.defaultPrevented || isEditableTarget(e.target)) return false
    const handled = handleKey(e)
    if (handled) e.preventDefault()
    return handled
  }

  function handleKey(e: KeyboardEvent): boolean {
    const key = e.key
    const mod = e.ctrlKey || e.metaKey
    if (mod && !e.altKey) {
      const lower = key.toLowerCase()
      if (lower === 'z') {
        if (e.shiftKey) redo()
        else undo()
        return true
      }
      if (lower === 'y') {
        redo()
        return true
      }
      if (lower === 'd') return duplicateSelected() !== null
      return false
    }
    if (mod || e.altKey) return false

    if (key === ' ') {
      const el = e.target as Element | null
      if (el?.closest?.('button, [role="button"], a')) return false
      spaceHeld.value = true
      return true
    }
    if (selected.value?.kind === 'prop' && (tool.value === 'select' || tool.value === 'prop')) {
      const turn = ({ KeyQ: -1, KeyE: 1 } as Record<string, number>)[e.code]
      if (turn) return rotateSelected(turn * (e.shiftKey ? FINE_ROTATION_STEP : ROTATION_STEP))
      if (key === '+' || key === '=') return scaleSelected(SCALE_STEP)
      if (key === '-' || key === '_') return scaleSelected(1 / SCALE_STEP)
    }
    const toolKey = TOOL_KEYS[key.toLowerCase()]
    if (toolKey && key.length === 1) {
      setTool(toolKey)
      return true
    }
    if (key.toLowerCase() === 'g' && key.length === 1) {
      toggleSnap()
      return true
    }
    const d = draft.value
    if (key === 'Enter') {
      return finishDraft()
    }
    if (key === 'Escape') {
      if (d || drag) {
        cancelDraft()
        cancelDrag()
        return true
      }
      if (selectedVertex.value != null) {
        selectedVertex.value = null
        return true
      }
      // Esc ends a run of stamping, like tapping the arrow: one press leaves the Deko tool, and the
      // decoration placed last stays selected for the side panel.
      if (tool.value === 'prop') {
        setTool('select')
        return true
      }
      if (selectedId.value) {
        select(null)
        return true
      }
      return false
    }
    if (key === 'Backspace' && d && d.tool !== 'label' && d.tool !== 'rect') {
      return undoPoint()
    }
    if (key === 'Delete' || key === 'Backspace') {
      if (removeSelectedVertex()) return true
      return deleteSelected()
    }
    const arrow = ARROWS[key]
    if (arrow) {
      const step = e.shiftKey ? 4 : 1
      return nudgeSelected(arrow[0] * step, arrow[1] * step)
    }
    if (key === ']') return reorderSelected(1)
    if (key === '[') return reorderSelected(-1)
    return false
  }

  function onKeyUp(e: KeyboardEvent) {
    if (e.key === ' ') spaceHeld.value = false
  }

  function onBlur() {
    spaceHeld.value = false
  }

  onScopeDispose(flushNudge)

  return {
    tool,
    setTool,
    selectedId,
    selected,
    selectedVertex,
    select,
    draft,
    snapEnabled,
    toggleSnap,
    snapHit,
    spaceHeld,
    dragging,
    override,
    displayShapes,
    grid,
    lastStyle,
    activeProp,
    lastPropScale,
    pathPreset,
    propHover,
    pickProp,
    pickLinePreset,
    pickAreaPreset,
    panFilter,
    onPointerDown,
    onPointerMove,
    onPointerUp,
    onPointerCancel,
    onPointerLeave,
    onDoubleClick,
    onKeyDown,
    onKeyUp,
    onBlur,
    abortGesture,
    finishDraft,
    cancelDraft,
    undoPoint,
    commitLabel,
    updateSelected,
    deleteSelected,
    removeSelectedVertex,
    duplicateSelected,
    reorderSelected,
    nudgeSelected,
    rotateSelected,
    scaleSelected,
    setSelectedRotation,
    setSelectedScale,
    flushNudge,
    undo,
    redo,
  }
}

export type ShapeEditor = ReturnType<typeof useShapeEditor>
