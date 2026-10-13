import { type ComputedRef, type Ref, computed, ref, shallowRef } from 'vue'

import type { VenuePlanShapesRead, VenueShapeRead } from '@/client/types.gen'
import { normalizeApiError } from '@/lib/api-errors'
import {
  type ShapeOp,
  applyOps,
  invertOps,
  materialiseOps,
  newShapeId,
} from '@/lib/venue-shape-edit'

/** How many steps Ctrl+Z can go back. */
export const HISTORY_LIMIT = 100
export const REVISION_CONFLICT = 'venue_shape.revision_conflict'

export type ShapeCommand = { label: string; ops: ShapeOp[] }

type Entry = { label: string; ops: ShapeOp[]; inverse: ShapeOp[] }
type Queued = { planId: string; ops: ShapeOp[]; entry: Entry | null }

export interface ShapeHistoryOptions {
  /** POST the ops as one batch; resolves with the plan's new shapes and revision. */
  send: (planId: string, ops: ShapeOp[], expectedRevision: number) => Promise<VenuePlanShapesRead>
  /**
   * Someone else saved in the meantime (409). The queue and both stacks are
   * already cleared; reload the plan and call `reset` with what came back.
   */
  onConflict: () => Promise<void> | void
  /** Any other failure; the failed command and everything queued after it are dropped. */
  onError?: (error: unknown) => void
  /** A batch was saved. */
  onSaved?: (result: VenuePlanShapesRead, previous: VenueShapeRead[]) => void
  /** Ids for new shapes (tests pass a counter). */
  newId?: () => string
  limit?: number
}

export interface ShapeHistory {
  /** The optimistic view: the last saved list with every unsaved command applied. */
  shapes: ComputedRef<VenueShapeRead[]>
  revision: Ref<number>
  planId: Ref<string | null>
  canUndo: ComputedRef<boolean>
  canRedo: ComputedRef<boolean>
  /** Commands not yet acknowledged by the server. */
  pending: ComputedRef<number>
  execute: (command: ShapeCommand) => ShapeOp[] | null
  undo: () => boolean
  redo: () => boolean
  reset: (planId: string | null, shapes: readonly VenueShapeRead[], revision: number) => void
  /** Resolves once every queued command has been answered. */
  flush: () => Promise<void>
}

/**
 * Undo/redo for drawing on a plan, with optimistic saving (#185 phase 2).
 *
 * The state is never mutated in place: `confirmed` is the last list the
 * server sent, `queue` the commands it has not answered yet, and `shapes`
 * is always derived as `confirmed` + `queue`. Rolling back after a failure is
 * therefore just dropping commands from the queue.
 *
 * - `execute` records the command with its inverse (computed against the
 *   current optimistic shapes) on the undo stack and queues it;
 * - `undo` queues the inverse of the newest entry and moves it to the redo
 *   stack; `redo` queues the entry again. Every step is plain ops: undoing a
 *   delete re-creates the shape under its old id;
 * - one command is in flight at a time, sent with the revision the last
 *   answer carried. A 409 conflict clears everything and calls `onConflict`;
 *   any other error drops the failed command and all after it (they may
 *   depend on it) together with their history entries.
 */
export function useShapeHistory(options: ShapeHistoryOptions): ShapeHistory {
  const limit = options.limit ?? HISTORY_LIMIT
  const newId = options.newId ?? newShapeId

  const planId = ref<string | null>(null)
  const confirmed = shallowRef<VenueShapeRead[]>([])
  const revision = ref(0)
  const queue = shallowRef<Queued[]>([])
  const undoStack = shallowRef<Entry[]>([])
  const redoStack = shallowRef<Entry[]>([])
  let sending = false
  // Bumped by `reset`, so an answer for a plan we have left is ignored.
  let generation = 0
  let waiters: (() => void)[] = []

  const shapes = computed(() =>
    applyOps(
      confirmed.value,
      queue.value.flatMap((q) => q.ops),
      planId.value ?? '',
    ),
  )
  const canUndo = computed(() => undoStack.value.length > 0)
  const canRedo = computed(() => redoStack.value.length > 0)
  const pending = computed(() => queue.value.length)

  function settle() {
    if (queue.value.length > 0 || sending) return
    const done = waiters
    waiters = []
    for (const resolve of done) resolve()
  }

  function enqueue(ops: ShapeOp[], entry: Entry | null) {
    if (!planId.value) return
    queue.value = [...queue.value, { planId: planId.value, ops, entry }]
    void pump()
  }

  async function pump() {
    if (sending) return
    const item = queue.value[0]
    if (!item) {
      settle()
      return
    }
    sending = true
    const gen = generation
    const previous = confirmed.value
    try {
      const result = await options.send(item.planId, item.ops, revision.value)
      if (gen !== generation) return
      confirmed.value = result.shapes
      revision.value = result.revision
      queue.value = queue.value.slice(1)
      options.onSaved?.(result, previous)
    } catch (error) {
      if (gen !== generation) return
      const { code } = normalizeApiError(error)
      if (code === REVISION_CONFLICT) {
        clearAll()
        sending = false
        await options.onConflict()
        settle()
        return
      }
      const dropped = new Set(queue.value.map((q) => q.entry).filter((e): e is Entry => !!e))
      queue.value = []
      undoStack.value = undoStack.value.filter((e) => !dropped.has(e))
      redoStack.value = redoStack.value.filter((e) => !dropped.has(e))
      options.onError?.(error)
    } finally {
      if (gen === generation) sending = false
    }
    void pump()
  }

  function clearAll() {
    generation++
    queue.value = []
    undoStack.value = []
    redoStack.value = []
  }

  function execute(command: ShapeCommand): ShapeOp[] | null {
    if (!planId.value || command.ops.length === 0) return null
    const current = shapes.value
    const ops = materialiseOps(current, command.ops, newId)
    const inverse = invertOps(ops, new Map(current.map((s) => [s.id, s])))
    const entry: Entry = { label: command.label, ops, inverse }
    undoStack.value = [...undoStack.value, entry].slice(-limit)
    redoStack.value = []
    enqueue(ops, entry)
    return ops
  }

  function undo(): boolean {
    const entry = undoStack.value.at(-1)
    if (!entry) return false
    undoStack.value = undoStack.value.slice(0, -1)
    redoStack.value = [...redoStack.value, entry]
    enqueue(entry.inverse, entry)
    return true
  }

  function redo(): boolean {
    const entry = redoStack.value.at(-1)
    if (!entry) return false
    redoStack.value = redoStack.value.slice(0, -1)
    undoStack.value = [...undoStack.value, entry].slice(-limit)
    enqueue(entry.ops, entry)
    return true
  }

  function reset(nextPlanId: string | null, nextShapes: readonly VenueShapeRead[], rev: number) {
    clearAll()
    sending = false
    planId.value = nextPlanId
    confirmed.value = [...nextShapes]
    revision.value = rev
    settle()
  }

  function flush(): Promise<void> {
    if (queue.value.length === 0 && !sending) return Promise.resolve()
    return new Promise((resolve) => waiters.push(resolve))
  }

  return { shapes, revision, planId, canUndo, canRedo, pending, execute, undo, redo, reset, flush }
}
