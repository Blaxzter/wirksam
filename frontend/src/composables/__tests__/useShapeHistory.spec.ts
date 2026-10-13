import { flushPromises } from '@vue/test-utils'

import { describe, expect, it, vi } from 'vitest'

import { REVISION_CONFLICT, useShapeHistory } from '@/composables/useShapeHistory'

import type { VenuePlanShapesRead, VenueShapeRead } from '@/client/types.gen'
import { type ShapeOp, applyOps } from '@/lib/venue-shape-edit'

function shape(id: string, overrides: Partial<VenueShapeRead> = {}): VenueShapeRead {
  return {
    id,
    plan_id: 'p1',
    kind: 'rect',
    style: 'room',
    points: [
      [0.1, 0.1],
      [0.3, 0.3],
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

const createOp = (id?: string): ShapeOp => ({
  op: 'create',
  shape: {
    ...(id ? { id } : {}),
    kind: 'rect',
    style: 'stage',
    points: [
      [0.5, 0.5],
      [0.6, 0.6],
    ],
  },
})

function apiError(status: number, code?: string) {
  return Object.assign(new Error('fail'), {
    isAxiosError: true,
    response: { status, data: { status, title: 'x', code } },
  })
}

/** A fake server that keeps its own list and revision and applies batches for real. */
function fakeServer(initial: VenueShapeRead[] = []) {
  const state = { shapes: initial, revision: 3 }
  const calls: { planId: string; ops: ShapeOp[]; rev: number }[] = []
  let failNext: unknown = null
  let gate: Promise<void> | null = null
  const send = vi.fn(
    async (planId: string, ops: ShapeOp[], rev: number): Promise<VenuePlanShapesRead> => {
      calls.push({ planId, ops, rev })
      if (gate) await gate
      if (failNext) {
        const error = failNext
        failNext = null
        throw error
      }
      state.shapes = applyOps(state.shapes, ops, planId)
      state.revision += 1
      return { plan_id: planId, revision: state.revision, shapes: state.shapes }
    },
  )
  return {
    state,
    calls,
    send,
    fail(error: unknown) {
      failNext = error
    },
    hold() {
      let release!: () => void
      gate = new Promise((r) => (release = r))
      return () => {
        gate = null
        release()
      }
    },
  }
}

function setup(initial: VenueShapeRead[] = [], extra: { limit?: number } = {}) {
  const server = fakeServer(initial)
  const onConflict = vi.fn()
  const onError = vi.fn()
  const onSaved = vi.fn()
  let n = 0
  const history = useShapeHistory({
    send: server.send,
    onConflict,
    onError,
    onSaved,
    newId: () => `new${++n}`,
    ...extra,
  })
  history.reset('p1', initial, 3)
  return { history, server, onConflict, onError, onSaved }
}

describe('useShapeHistory', () => {
  it('applies a command optimistically and sends it with the revision', async () => {
    const { history, server, onSaved } = setup([shape('a')])
    const ops = history.execute({ label: 'draw', ops: [createOp()] })
    expect(ops?.[0]).toMatchObject({ op: 'create', shape: { id: 'new1', sort_order: 1 } })
    // Before the server answered.
    expect(history.shapes.value.map((s) => s.id)).toEqual(['a', 'new1'])
    expect(history.pending.value).toBe(1)
    await history.flush()
    expect(server.calls[0]).toMatchObject({ planId: 'p1', rev: 3 })
    expect(history.revision.value).toBe(4)
    expect(history.pending.value).toBe(0)
    expect(onSaved).toHaveBeenCalledTimes(1)
    expect(history.canUndo.value).toBe(true)
  })

  it('sends commands one at a time, each with the newest revision', async () => {
    const { history, server } = setup()
    const release = server.hold()
    history.execute({ label: 'a', ops: [createOp('x')] })
    history.execute({ label: 'b', ops: [{ op: 'update', id: 'x', patch: { label: 'Hi' } }] })
    await flushPromises()
    expect(server.send).toHaveBeenCalledTimes(1)
    expect(history.shapes.value[0]!.label).toBe('Hi')
    release()
    await history.flush()
    expect(server.calls.map((c) => c.rev)).toEqual([3, 4])
    expect(server.state.shapes[0]!.label).toBe('Hi')
  })

  it('ignores empty commands and commands without a plan', () => {
    const { history } = setup()
    expect(history.execute({ label: 'x', ops: [] })).toBeNull()
    history.reset(null, [], 0)
    expect(history.execute({ label: 'x', ops: [createOp()] })).toBeNull()
    expect(history.undo()).toBe(false)
    expect(history.redo()).toBe(false)
  })

  it('undoes and redoes a create, an update and a delete with the same ids', async () => {
    const { history, server } = setup([shape('a', { label: 'Hall' })])
    history.execute({ label: 'create', ops: [createOp()] })
    history.execute({
      label: 'update',
      ops: [{ op: 'update', id: 'a', patch: { label: 'Stage' } }],
    })
    history.execute({ label: 'delete', ops: [{ op: 'delete', id: 'a' }] })
    await history.flush()
    expect(server.state.shapes.map((s) => s.id)).toEqual(['new1'])

    history.undo() // delete → 'a' comes back with its id
    await history.flush()
    expect(server.state.shapes.find((s) => s.id === 'a')?.label).toBe('Stage')
    history.undo() // update
    await history.flush()
    expect(server.state.shapes.find((s) => s.id === 'a')?.label).toBe('Hall')
    history.undo() // create
    await history.flush()
    expect(server.state.shapes.map((s) => s.id)).toEqual(['a'])
    expect(history.canUndo.value).toBe(false)
    expect(history.canRedo.value).toBe(true)

    history.redo()
    history.redo()
    history.redo()
    await history.flush()
    expect(server.state.shapes.map((s) => s.id)).toEqual(['new1'])
    expect(history.shapes.value).toEqual(server.state.shapes)
    // A new command clears the redo stack.
    history.undo()
    history.execute({ label: 'x', ops: [createOp()] })
    expect(history.canRedo.value).toBe(false)
    await history.flush()
  })

  it('drops a failed command, everything queued after it and their history', async () => {
    const { history, server, onError } = setup()
    history.execute({ label: 'ok', ops: [createOp('ok')] })
    await history.flush()

    const release = server.hold()
    server.fail(apiError(422, 'venue_shape.too_small'))
    history.execute({ label: 'bad', ops: [createOp('bad')] })
    history.execute({
      label: 'dependent',
      ops: [{ op: 'update', id: 'bad', patch: { label: 'x' } }],
    })
    expect(history.shapes.value.map((s) => s.id)).toEqual(['ok', 'bad'])
    release()
    await history.flush()
    expect(onError).toHaveBeenCalledTimes(1)
    // Rolled back to what the server has.
    expect(history.shapes.value.map((s) => s.id)).toEqual(['ok'])
    expect(history.pending.value).toBe(0)
    // Only the successful step is left to undo.
    history.undo()
    expect(history.canUndo.value).toBe(false)
    await history.flush()
    expect(server.state.shapes).toEqual([])
  })

  it('drops a failed undo from the redo stack too', async () => {
    const { history, server } = setup()
    history.execute({ label: 'a', ops: [createOp('a')] })
    await history.flush()
    server.fail(new Error('Network Error'))
    history.undo()
    await history.flush()
    expect(history.canUndo.value).toBe(false)
    expect(history.canRedo.value).toBe(false)
    expect(history.shapes.value.map((s) => s.id)).toEqual(['a'])
  })

  it('works without an error handler', async () => {
    const server = fakeServer()
    const history = useShapeHistory({ send: server.send, onConflict: () => {} })
    history.reset('p1', [], 0)
    server.fail(new Error('boom'))
    const ops = history.execute({ label: 'a', ops: [createOp()] })
    // A real UUID by default.
    expect(ops?.[0]?.op === 'create' && ops[0].shape.id).toMatch(/^[0-9a-f-]{36}$/)
    await history.flush()
    expect(history.shapes.value).toEqual([])
  })

  it('on a revision conflict clears everything and asks for a reload', async () => {
    const { history, server, onConflict, onError } = setup()
    onConflict.mockImplementation(async () => {
      history.reset('p1', [shape('theirs')], 10)
    })
    server.fail(apiError(409, REVISION_CONFLICT))
    history.execute({ label: 'a', ops: [createOp('mine')] })
    history.execute({ label: 'b', ops: [createOp('mine2')] })
    await history.flush()
    expect(onConflict).toHaveBeenCalledTimes(1)
    expect(onError).not.toHaveBeenCalled()
    expect(history.shapes.value.map((s) => s.id)).toEqual(['theirs'])
    expect(history.revision.value).toBe(10)
    expect(history.canUndo.value).toBe(false)
    expect(history.canRedo.value).toBe(false)
    expect(server.send).toHaveBeenCalledTimes(1)
  })

  it('ignores the answer for a plan it has left', async () => {
    const { history, server, onSaved } = setup()
    const release = server.hold()
    history.execute({ label: 'a', ops: [createOp('a')] })
    await flushPromises()
    history.reset('p2', [shape('other', { plan_id: 'p2' })], 7)
    release()
    await flushPromises()
    expect(onSaved).not.toHaveBeenCalled()
    expect(history.shapes.value.map((s) => s.id)).toEqual(['other'])
    expect(history.revision.value).toBe(7)
    // The same for a failure.
    const release2 = server.hold()
    server.fail(new Error('x'))
    history.execute({ label: 'b', ops: [createOp('b')] })
    await flushPromises()
    history.reset('p2', [], 8)
    release2()
    await flushPromises()
    expect(history.revision.value).toBe(8)
  })

  it('caps the undo stack', async () => {
    const { history } = setup([], { limit: 3 })
    for (let i = 0; i < 5; i++) history.execute({ label: 'x', ops: [createOp(`s${i}`)] })
    await history.flush()
    let steps = 0
    while (history.undo()) steps++
    expect(steps).toBe(3)
    // Redo is capped the same way when it moves entries back.
    while (history.redo()) steps--
    expect(steps).toBe(0)
    await history.flush()
  })

  it('flush resolves straight away when idle', async () => {
    const { history } = setup()
    await expect(history.flush()).resolves.toBeUndefined()
  })
})
