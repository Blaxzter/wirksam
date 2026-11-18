import { ref, shallowRef } from 'vue'

import { useAuthenticatedClient } from '@/composables/useAuthenticatedClient'
import { useSharedListWizardApi } from '@/composables/useSharedListWizardApi'

import type {
  EventRead,
  SharedListReusable,
  SharedListRow,
  ShiftRead,
  TaskRead,
} from '@/client/types.gen'
import { normalizeApiError, toastApiError } from '@/lib/api-errors'
import {
  type EventProblem,
  type LeftOutTask,
  type OfferProblem,
  noticeListBody,
  planEventPrint,
  planTaskPrint,
} from '@/lib/shared-list-print'

/** No list to reuse holds these tasks: create one with the defaults? */
interface CreateAsk {
  kind: 'create'
  eventId: string
  title: string
  taskIds: string[]
  leftOut: LeftOutTask[]
  /** A whole event's print, whose list may hold more tasks than these. */
  covering: boolean
}

/** What `SharedListPrintDialog` asks or explains. */
export type NoticeDialog =
  | CreateAsk
  /** The task cannot be offered on a list: its sheet goes without a QR code. */
  | { kind: 'task'; problem: OfferProblem }
  /** No task of the event goes on a list. */
  | { kind: 'event'; reason: EventProblem; offered: number; leftOut: LeftOutTask[] }

/** Where a print goes on: a list's sheet, the sheet without QR code, or the dialog asks first. */
export type NoticeOutcome =
  { kind: 'list'; listId: string } | { kind: 'plain' } | { kind: 'asking' }

/**
 * The way from "Drucken" to a notice with a shared list's QR code: reuse the
 * list of exactly the printed tasks (for a whole event, one holding them all),
 * or ask once and create one with the wizard's defaults. A paused or expired
 * list is reused too: its notice offers to resume it. Whoever cannot share
 * the tasks gets the sheet without QR code, and so does anyone the server
 * turns away when it looks the list up.
 */
export function useSharedListPrint() {
  const { get } = useAuthenticatedClient()
  const { fetchEvent, create } = useSharedListWizardApi()

  const dialog = shallowRef<NoticeDialog | null>(null)
  const creating = ref(false)

  async function reusable(ask: CreateAsk): Promise<SharedListRow | null> {
    const query = ask.covering ? { task_id: ask.taskIds, covering: true } : { task_id: ask.taskIds }
    const res = await get<{ data: SharedListReusable }>({
      url: `/events/${ask.eventId}/shared-lists/reusable`,
      query,
    })
    return res.data.list
  }

  async function offer(ask: CreateAsk): Promise<NoticeOutcome> {
    let found: SharedListRow | null
    try {
      found = await reusable(ask)
    } catch (error) {
      const { status } = normalizeApiError(error)
      if (status === 403 || status === 404) return { kind: 'plain' }
      throw error
    }
    if (found) return { kind: 'list', listId: found.id }
    dialog.value = ask
    return { kind: 'asking' }
  }

  /** Printing one task, with the shifts its page has loaded. */
  async function startTask(
    task: Pick<TaskRead, 'id' | 'name' | 'status' | 'team_id' | 'can_manage' | 'event_id'>,
    shifts: readonly ShiftRead[],
  ): Promise<NoticeOutcome> {
    // Neither an organiser nor in charge of it: no list to make, nothing to ask.
    if (!task.can_manage || !task.event_id) return { kind: 'plain' }
    const event = await fetchEvent(task.event_id)
    const plan = planTaskPrint(event, task, shifts)
    if (plan.kind === 'plain') return plan
    if (plan.kind === 'explain') {
      dialog.value = { kind: 'task', problem: plan.problem }
      return { kind: 'asking' }
    }
    const { taskIds, title } = plan
    return offer({
      kind: 'create',
      eventId: event.id,
      title,
      taskIds,
      leftOut: [],
      covering: false,
    })
  }

  /** Printing every task of `event`, each with its shifts; `title` names a new list. */
  async function startEvent(
    event: EventRead,
    tasks: readonly TaskRead[],
    shiftsOf: (taskId: string) => readonly ShiftRead[],
    title: string,
  ): Promise<NoticeOutcome> {
    const plan = planEventPrint(event, tasks, shiftsOf)
    if (plan.kind === 'plain') return plan
    if (plan.kind === 'explain') {
      const { reason, offered, leftOut } = plan
      dialog.value = { kind: 'event', reason, offered, leftOut }
      return { kind: 'asking' }
    }
    const { taskIds, leftOut } = plan
    return offer({ kind: 'create', eventId: event.id, title, taskIds, leftOut, covering: true })
  }

  /**
   * Create the list the dialog asks about, unless one turned up while it
   * stood open. Resolves to the list's id, or null if refused (and said why).
   */
  async function createList(): Promise<string | null> {
    const ask = dialog.value
    if (ask?.kind !== 'create' || creating.value) return null
    creating.value = true
    try {
      const list =
        (await reusable(ask)) ?? (await create(ask.eventId, noticeListBody(ask.title, ask.taskIds)))
      dialog.value = null
      return list.id
    } catch (error) {
      toastApiError(error)
      return null
    } finally {
      creating.value = false
    }
  }

  /** The wizard with the dialog's tasks picked, to change the defaults first. */
  function wizardRoute() {
    const ask = dialog.value
    if (ask?.kind !== 'create') return null
    return {
      name: 'shared-list-create',
      params: { eventId: ask.eventId },
      query: { tasks: ask.taskIds.join(',') },
    }
  }

  function close() {
    dialog.value = null
  }

  return { dialog, creating, startTask, startEvent, createList, wizardRoute, close }
}
