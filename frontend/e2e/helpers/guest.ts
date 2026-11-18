/**
 * Seeding for the guest pages: an event of its own, one published task with
 * shifts the day after tomorrow, and a shared list offering them.
 *
 * Node-side through `serverApi`, because the guest specs run as the anonymous
 * visitor who opens a link and have no signed-in page to call the API from.
 * Each test gets its own event and deletes it again, task first: a task
 * outlives its event, while the event takes the list and the guests' contact
 * rows with it. `POST /testing/reset` clears the guest accounts left behind on
 * the next run.
 */
import { serverApi, serverApiRaw } from '../fixtures.js'
import {
  type PublicSignupRequest,
  type PublicSignupResult,
  type SharedListCreate,
  type SharedListDetail,
  type ShiftRead,
  type TaskWithShifts,
  createSharedList,
  futureDate,
  publicSignup,
  uniqueName,
} from './api.js'

export interface GuestListSeed {
  eventId: string
  eventName: string
  taskId: string
  taskName: string
  /** The task's shifts, earliest first: 10:00–11:00 and 11:00–12:00. */
  shifts: ShiftRead[]
  list: SharedListDetail
  /** A second task of the event that takes vouchers (`seedVoucherGuestList`). */
  pointTask?: { id: string; name: string }
}

export interface GuestListOptions {
  /** Places per shift; 1 makes a shift easy to fill from the API. */
  peoplePerShift?: number
  /** Anything the list should set beyond its title and task. */
  list?: Partial<SharedListCreate>
  /**
   * Days from today the event starts; 2 by default, like its shifts. A test
   * that moves a shift into the past (to have it earn vouchers) starts the
   * event yesterday, so the moved shift stays inside it.
   */
  eventStartsIn?: number
}

/** A published event and task, and a live list offering the task's two shifts. */
export async function seedGuestList(
  email: string,
  options: GuestListOptions = {},
): Promise<GuestListSeed> {
  const day = futureDate(2)
  const event = await serverApi<{ id: string; name: string }>('POST', '/events/', email, {
    name: uniqueName('E2E Guest Event'),
    status: 'published',
    visibility: 'private',
    start_date: futureDate(options.eventStartsIn ?? 2),
    end_date: futureDate(3),
  })
  const taskName = uniqueName('E2E Guest Task')
  const created = await serverApi<TaskWithShifts>('POST', '/tasks/with-shifts', email, {
    name: taskName,
    description: null,
    start_date: day,
    end_date: day,
    status: 'published',
    location: 'Main Stage',
    location_id: null,
    category: null,
    event_id: event.id,
    schedule: {
      default_start_time: '10:00:00',
      default_end_time: '12:00:00',
      shift_duration_minutes: 60,
      people_per_shift: options.peoplePerShift ?? 2,
      remainder_mode: 'drop',
      overrides: [],
      excluded_shifts: [],
    },
  })
  const { items } = await serverApi<{ items: ShiftRead[] }>(
    'GET',
    `/shifts/?task_id=${created.task.id}&limit=200`,
    email,
  )
  const shifts = [...items].sort((a, b) =>
    `${a.date}${a.start_time}`.localeCompare(`${b.date}${b.start_time}`),
  )
  const list = await createSharedList(email, event.id, {
    title: uniqueName('E2E Helpers wanted'),
    task_ids: [created.task.id],
    ...options.list,
  })
  return {
    eventId: event.id,
    eventName: event.name,
    taskId: created.task.id,
    taskName,
    shifts,
    list,
  }
}

/**
 * A list whose task gives two vouchers a shift, in an event that started
 * yesterday, and a second task of the event that takes vouchers. Nobody can
 * sign up for a shift that is over, so a test signs a guest up for one still
 * ahead, then `endGuestShift` moves it to yesterday, where it has earned.
 */
export async function seedVoucherGuestList(email: string): Promise<GuestListSeed> {
  const seed = await seedGuestList(email, { eventStartsIn: -1 })
  await serverApi('PATCH', `/tasks/${seed.taskId}`, email, { vouchers_per_shift: 2 })
  const point = await serverApi<TaskWithShifts>('POST', '/tasks/with-shifts', email, {
    name: uniqueName('E2E Guest Food stand'),
    description: null,
    start_date: futureDate(2),
    end_date: futureDate(2),
    status: 'published',
    location: null,
    location_id: null,
    category: null,
    event_id: seed.eventId,
    schedule: {
      default_start_time: '10:00:00',
      default_end_time: '12:00:00',
      shift_duration_minutes: 120,
      people_per_shift: 1,
      remainder_mode: 'drop',
      overrides: [],
      excluded_shifts: [],
    },
  })
  await serverApi('PATCH', `/tasks/${point.task.id}`, email, { is_voucher_point: true })
  return { ...seed, pointTask: { id: point.task.id, name: point.task.name } }
}

/** Move a booked shift to yesterday, so it is over and has earned its vouchers. */
export async function endGuestShift(email: string, shiftId: string): Promise<void> {
  await serverApi('PATCH', `/shifts/${shiftId}`, email, { date: futureDate(-1) })
}

/** Remove a seeded task and event, and with them the list and everyone who signed up on it. */
export async function deleteGuestList(email: string, seed: GuestListSeed | undefined) {
  if (!seed) return
  // Tasks outlive their event, so they go first.
  if (seed.pointTask) await serverApiRaw('DELETE', `/tasks/${seed.pointTask.id}`, email)
  await serverApiRaw('DELETE', `/tasks/${seed.taskId}`, email)
  await serverApiRaw('DELETE', `/events/${seed.eventId}`, email)
}

/**
 * Sign a guest up through the public endpoint, as the page would, and hand back
 * the answer; its `guest_token` opens `/guest-signup#<token>`.
 */
export async function signUpGuest(
  seed: GuestListSeed,
  body: Partial<PublicSignupRequest> & { shift_id: string },
): Promise<PublicSignupResult> {
  const response = await publicSignup(seed.list.code, {
    name: 'Grace Guest',
    show_names: 'none',
    ...body,
  })
  if (response.status !== 201) {
    throw new Error(`Guest sign-up failed: ${response.status} ${JSON.stringify(response.body)}`)
  }
  return response.body as PublicSignupResult
}
