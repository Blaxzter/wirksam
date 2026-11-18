/**
 * An event of its own for the shared-list specs: published, with published
 * tasks whose shifts are two days ahead, so a list can offer them and a guest
 * can sign up. The worker's event never gains a list (that would put lists on
 * every later test's pages).
 */
import type { Page } from '@playwright/test'

import {
  type EventRead,
  type ShiftRead,
  type TaskRead,
  createEvent,
  createTaskWithShifts,
  deleteEvent,
  deleteTask,
  futureDate,
  listShifts,
  uniqueName,
} from './api.js'

export interface SharedListEvent {
  event: EventRead
  tasks: { task: TaskRead; shifts: ShiftRead[] }[]
}

/** The event, with `taskNames.length` published tasks of four one-hour shifts each. */
export async function seedSharedListEvent(
  page: Page,
  prefix: string,
  taskNames: string[] = ['Kuchen'],
): Promise<SharedListEvent> {
  const event = await createEvent(page, uniqueName(prefix), 'published', 'private', {
    start: futureDate(1),
    end: futureDate(4),
  })
  const tasks: SharedListEvent['tasks'] = []
  for (const name of taskNames) {
    const { task } = await createTaskWithShifts(page, {
      name: uniqueName(`${prefix} ${name}`),
      eventId: event.id,
      status: 'published',
      startDate: futureDate(2),
      endDate: futureDate(2),
      startTime: '10:00',
      endTime: '14:00',
      slotDuration: 60,
      peoplePerShift: 3,
    })
    tasks.push({ task, shifts: await listShifts(page, task.id) })
  }
  return { event, tasks }
}

/** Tasks outlive their event, so they go first; the event takes its lists with it. */
export async function removeSharedListEvent(page: Page, seeded: SharedListEvent | undefined) {
  if (!seeded) return
  for (const { task } of seeded.tasks) await deleteTask(page, task.id).catch(() => {})
  await deleteEvent(page, seeded.event.id).catch(() => {})
}

/** A unique address for a guest, so no two sign-ups share a chain by accident. */
export function guestEmail(label: string): string {
  return `${uniqueName(label).replace(/\W+/g, '-').toLowerCase()}@example.org`
}
