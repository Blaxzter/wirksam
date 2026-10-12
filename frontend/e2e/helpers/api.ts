/**
 * Shared E2E API helpers — used by both single-user and multi-user test files.
 */
import type { Page } from '@playwright/test'
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import type {
  BookingRead,
  EventRead,
  LocationCreate,
  LocationRead,
  ShiftRead,
  TaskCreateWithShiftsResponse,
  TaskRead,
  VenueMarkerCreate,
  VenueMarkerRead,
  VenuePlanRead,
} from '../../src/client/types.gen.js'

export type {
  BookingRead,
  ShiftRead,
  EventRead,
  TaskRead,
  LocationRead,
  VenueMarkerRead,
  VenuePlanRead,
}
export type TaskWithShifts = TaskCreateWithShiftsResponse

export const API = process.env.VITE_API_URL ?? 'http://localhost:8787/api/v1'

/** Return a unique test name to avoid collisions between parallel workers. */
export function uniqueName(prefix: string): string {
  return `${prefix} ${Date.now()}-${Math.random().toString(36).slice(2, 6)}`
}

/** Return an ISO date string (YYYY-MM-DD) offset from today by `daysFromNow`. */
export function futureDate(daysFromNow: number): string {
  const d = new Date()
  d.setDate(d.getDate() + daysFromNow)
  return d.toISOString().slice(0, 10)
}

/**
 * Make an API call as the page's own user, from inside the browser context.
 *
 * There is no token to attach. Identity comes from the `X-Test-User-Email`
 * header that `fixtures.ts::setupApiInterception` adds to every `/api/v1/**`
 * request the page makes, and the backend's TESTING branch answers to that
 * header before it ever looks at `Authorization`. This helper used to send a
 * bearer token as well; it was the string `'fake-test-token'`, read back out of
 * the Auth0 SDK's localStorage cache, and it authenticated nothing — the header
 * was already doing the work.
 *
 * The corollary: this only works on a page built by one of the `*Page`
 * fixtures. A bare `page` makes anonymous calls.
 */
export async function api<T = unknown>(
  page: Page,
  method: string,
  path: string,
  body?: object,
): Promise<T> {
  const result = await page.evaluate(
    async ({ url, method, body }) => {
      const res = await fetch(url, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: body ? JSON.stringify(body) : undefined,
      })
      if (res.status === 204) return { __status: 204, __ok: true, __body: null }
      const json = await res.json()
      return { __status: res.status, __ok: res.ok, __body: json }
    },
    { url: `${API}${path}`, method, body },
  )
  if (!result.__ok) {
    const detail =
      typeof result.__body === 'object' && result.__body !== null
        ? JSON.stringify(result.__body)
        : String(result.__body)
    throw new Error(`API ${method} ${path} failed with ${result.__status}: ${detail}`)
  }
  return result.__body as T
}

/**
 * Like `api`, but resolves with the HTTP status instead of throwing.
 *
 * Permission tests care about *which* refusal they got — 403 for "not allowed
 * here" versus 404 for "you cannot even see this" — and that distinction is
 * lost once the error is a thrown string.
 */
export async function apiStatus(
  page: Page,
  method: string,
  path: string,
  body?: object,
): Promise<number> {
  return page.evaluate(
    async ({ url, method, body }) => {
      const res = await fetch(url, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: body ? JSON.stringify(body) : undefined,
      })
      return res.status
    },
    { url: `${API}${path}`, method, body },
  )
}

/** Create an event (draft or published). Admin token required. */
export async function createEvent(
  page: Page,
  name: string,
  status: 'draft' | 'published' = 'published',
  visibility: 'public' | 'private' = 'public',
  /** ISO dates; defaults to a five-day event a month from now. */
  dates: { start: string; end: string } = { start: futureDate(30), end: futureDate(34) },
): Promise<EventRead> {
  return api<EventRead>(page, 'POST', '/events/', {
    name,
    status,
    visibility,
    start_date: dates.start,
    end_date: dates.end,
  })
}

/**
 * Invite someone into an event and accept on their behalf.
 *
 * Takes both pages because an invitation is created by an organiser and
 * redeemed by the invitee — the two halves authenticate as different users.
 */
export async function addMember(
  inviterPage: Page,
  inviteePage: Page,
  eventId: string,
  inviteeEmail: string,
  role: 'admin' | 'member' = 'member',
): Promise<void> {
  const invitation = await api<{ token: string }>(
    inviterPage,
    'POST',
    `/events/${eventId}/invitations`,
    { email: inviteeEmail, role },
  )
  await api(inviteePage, 'POST', `/invitations/${invitation.token}/accept`)
}

/** Remove someone from an event. */
export async function removeMember(page: Page, eventId: string, userId: string): Promise<void> {
  await api(page, 'DELETE', `/events/${eventId}/members/${userId}`)
}

/** Delete an event. Admin token required. */
export async function deleteEvent(page: Page, id: string): Promise<void> {
  if (!id || id === 'undefined') return
  await api(page, 'DELETE', `/events/${id}`)
}

/** Remove the current user's availability for an event (best-effort). */
export async function clearAvailability(page: Page, eventId: string): Promise<void> {
  if (!eventId || eventId === 'undefined') return
  await api(page, 'DELETE', `/events/${eventId}/availability/me`)
}

/** Point the current user's `selected_event_id` at a given event. */
export async function setSelectedEvent(page: Page, eventId: string | null): Promise<void> {
  await api(page, 'PUT', '/users/me/selected-event', { selected_event_id: eventId })
}

/** Look up a seeded test user's UUID by email (admin-only endpoint). */
export async function getUserIdByEmail(adminPage: Page, email: string): Promise<string> {
  const res = await api<{ items: { id: string; email: string }[] }>(
    adminPage,
    'GET',
    '/users/?limit=200',
  )
  const user = res.items.find((u) => u.email === email)
  if (!user) throw new Error(`User ${email} not found`)
  return user.id
}

// ── Task helpers ──────────────────────────────────────────────────────────────

/** Create a task with auto-generated shifts via the /tasks/with-shifts endpoint.
 *
 * `eventId` defaults to the current user's `selected_event_id` so created tasks
 * show up under the user's dashboard scope. Pass `eventId: null` to create an
 * orphan task (rarely what you want under the new scoped-UI model).
 */
export async function createTaskWithShifts(
  page: Page,
  opts: {
    name: string
    description?: string
    startDate?: string
    endDate?: string
    status?: 'draft' | 'published' | 'archived'
    location?: string
    /** Link a location of the event; the server fills `location` with its name. */
    locationId?: string | null
    category?: string
    eventId?: string | null
    startTime?: string
    endTime?: string
    slotDuration?: number
    peoplePerShift?: number
  },
): Promise<TaskCreateWithShiftsResponse> {
  // Use tomorrow to avoid the backend's future_shifts_cutoff filtering out past-time shifts
  const defaultDate = futureDate(1)
  const startDate = opts.startDate ?? defaultDate
  const endDate = opts.endDate ?? defaultDate

  let eventId: string | null
  if (opts.eventId !== undefined) {
    eventId = opts.eventId
  } else {
    const profile = await api<{ selected_event_id: string | null }>(page, 'GET', '/users/me')
    eventId = profile.selected_event_id ?? null
  }

  return api<TaskCreateWithShiftsResponse>(page, 'POST', '/tasks/with-shifts', {
    name: opts.name,
    description: opts.description ?? null,
    start_date: startDate,
    end_date: endDate,
    status: opts.status ?? 'draft',
    location: opts.location ?? null,
    location_id: opts.locationId ?? null,
    category: opts.category ?? null,
    event_id: eventId,
    schedule: {
      default_start_time: (opts.startTime ?? '10:00') + ':00',
      default_end_time: (opts.endTime ?? '12:00') + ':00',
      shift_duration_minutes: opts.slotDuration ?? 60,
      people_per_shift: opts.peoplePerShift ?? 2,
      remainder_mode: 'drop',
      overrides: [],
      excluded_shifts: [],
    },
  })
}

/** Delete a task. Admin token required. */
export async function deleteTask(page: Page, id: string): Promise<void> {
  if (!id || id === 'undefined') return
  await api(page, 'DELETE', `/tasks/${id}`)
}

/** Publish a task (set status to published). */
export async function publishTask(page: Page, id: string): Promise<TaskRead> {
  return api<TaskRead>(page, 'PATCH', `/tasks/${id}`, { status: 'published' })
}

/** List duty shifts for a task. */
export async function listShifts(page: Page, eventId: string): Promise<ShiftRead[]> {
  const res = await api<{ items: ShiftRead[] }>(
    page,
    'GET',
    `/shifts/?task_id=${eventId}&limit=200`,
  )
  return res.items
}

/** Book a duty shift. */
export async function bookShift(page: Page, slotId: string): Promise<BookingRead> {
  return api<BookingRead>(page, 'POST', '/bookings/', { shift_id: slotId })
}

/** Cancel a booking. */
export async function cancelBooking(page: Page, bookingId: string): Promise<void> {
  await api(page, 'DELETE', `/bookings/${bookingId}`)
}

// ── Location and venue map helpers ──────────────────────────────────────────

/** A small committed floor plan (800×500 PNG) for the venue map specs. */
export const FLOORPLAN_PATH = resolve(
  dirname(fileURLToPath(import.meta.url)),
  '../fixtures/floorplan.png',
)

/** Create a location in an event. Event admin required. */
export async function createLocation(
  page: Page,
  eventId: string,
  body: LocationCreate,
): Promise<LocationRead> {
  return api<LocationRead>(page, 'POST', `/events/${eventId}/locations`, body)
}

/** Create an (image-less) venue plan in an event. Event admin required. */
export async function createVenuePlan(
  page: Page,
  eventId: string,
  name: string,
): Promise<VenuePlanRead> {
  return api<VenuePlanRead>(page, 'POST', `/events/${eventId}/venue-plans`, { name })
}

/**
 * Upload a picture for a venue plan (multipart), `floorplan.png` by default.
 *
 * Sent from inside the page, like `api()`, so the fixture's header bypass
 * names the caller. The bytes travel as base64 because `page.evaluate` only
 * carries JSON.
 */
export async function uploadPlanImage(
  page: Page,
  planId: string,
  filePath: string = FLOORPLAN_PATH,
): Promise<VenuePlanRead> {
  const base64 = readFileSync(filePath).toString('base64')
  const result = await page.evaluate(
    async ({ url, base64 }) => {
      const bytes = Uint8Array.from(atob(base64), (c) => c.charCodeAt(0))
      const form = new FormData()
      form.append('file', new Blob([bytes], { type: 'image/png' }), 'floorplan.png')
      const res = await fetch(url, { method: 'PUT', body: form })
      return { status: res.status, ok: res.ok, body: await res.json().catch(() => null) }
    },
    { url: `${API}/venue-plans/${planId}/image`, base64 },
  )
  if (!result.ok) {
    throw new Error(
      `API PUT /venue-plans/${planId}/image failed with ${result.status}: ` +
        JSON.stringify(result.body),
    )
  }
  return result.body as VenuePlanRead
}

/** Put a marker on a venue plan. Event admin required. */
export async function createMarker(
  page: Page,
  planId: string,
  body: VenueMarkerCreate,
): Promise<VenueMarkerRead> {
  return api<VenueMarkerRead>(page, 'POST', `/venue-plans/${planId}/markers`, body)
}

export interface MappedEvent {
  event: EventRead
  location: LocationRead
  plan: VenuePlanRead
  marker: VenueMarkerRead
  task: TaskRead
  shift: ShiftRead
}

/**
 * Seed an event with everything the venue map shows: a location with a
 * Markdown description, a plan with `floorplan.png`, a pin for the location and
 * a published task with one shift there.
 *
 * The event starts tomorrow, so the map opens on that day (its first) and the
 * shift is never cut off as already past, whatever the time of day the suite
 * runs. Delete the task before the event: tasks outlive their event.
 */
export async function seedMappedEvent(
  page: Page,
  opts: { name?: string; visibility?: 'public' | 'private' } = {},
): Promise<MappedEvent> {
  const event = await createEvent(
    page,
    opts.name ?? uniqueName('E2E Venue Map'),
    'published',
    opts.visibility ?? 'private',
    { start: futureDate(1), end: futureDate(3) },
  )
  const location = await createLocation(page, event.id, {
    name: uniqueName('Kitchen Tent'),
    description: 'Enter through the **back door**.',
  })
  const created = await createVenuePlan(page, event.id, 'Grounds')
  const plan = await uploadPlanImage(page, created.id)
  const marker = await createMarker(page, plan.id, {
    kind: 'location',
    location_id: location.id,
    x: 0.4,
    y: 0.5,
  })
  const { task } = await createTaskWithShifts(page, {
    name: uniqueName('E2E Map Task'),
    eventId: event.id,
    status: 'published',
    locationId: location.id,
    startDate: futureDate(1),
    endDate: futureDate(1),
    startTime: '10:00',
    endTime: '11:00',
    slotDuration: 60,
    peoplePerShift: 2,
  })
  const [shift] = await listShifts(page, task.id)
  return { event, location, plan, marker, task, shift }
}
