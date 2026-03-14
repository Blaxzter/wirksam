/**
 * Shared E2E API helpers — used by both single-user and multi-user test files.
 */

import type { Page } from '@playwright/test'

export const API = process.env.VITE_API_URL ?? 'http://localhost:8000/api/v1'

/** Extract the Auth0 access token from localStorage. */
export async function getToken(page: Page): Promise<string> {
  return page.evaluate(() => {
    const key = Object.keys(localStorage).find((k) => k.startsWith('@@auth0spajs@@'))
    if (!key) return ''
    try {
      const raw = JSON.parse(localStorage.getItem(key) ?? '{}')
      return (raw as { body?: { access_token?: string } })?.body?.access_token ?? ''
    } catch {
      return ''
    }
  })
}

/** Make an authenticated API call inside the browser context. */
export async function api<T = unknown>(page: Page, method: string, path: string, body?: object): Promise<T> {
  const token = await getToken(page)
  return page.evaluate(
    async ({ url, method, body, token }) => {
      const res = await fetch(url, {
        method,
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: body ? JSON.stringify(body) : undefined,
      })
      if (res.status === 204) return null
      return res.json()
    },
    { url: `${API}${path}`, method, body, token },
  ) as Promise<T>
}

export interface EventGroupRead {
  id: string
  name: string
  status: string
  start_date: string
  end_date: string
}

/** Create an event group (draft or published). Admin token required. */
export async function createGroup(
  page: Page,
  name: string,
  status: 'draft' | 'published' = 'published',
): Promise<EventGroupRead> {
  const draft = await api<EventGroupRead>(page, 'POST', '/event-groups/', {
    name,
    start_date: '2026-06-10',
    end_date: '2026-06-14',
  })
  if (status === 'draft') return draft
  return api<EventGroupRead>(page, 'PATCH', `/event-groups/${draft.id}`, { status: 'published' })
}

/** Delete an event group. Admin token required. */
export async function deleteGroup(page: Page, id: string): Promise<void> {
  if (!id || id === 'undefined') return
  await api(page, 'DELETE', `/event-groups/${id}`)
}

/** Remove the current user's availability for a group (best-effort). */
export async function clearAvailability(page: Page, groupId: string): Promise<void> {
  if (!groupId || groupId === 'undefined') return
  await api(page, 'DELETE', `/event-groups/${groupId}/availability/me`)
}

// ── Event helpers ──────────────────────────────────────────────────────────────

export interface EventRead {
  id: string
  name: string
  description: string | null
  status: string
  start_date: string
  end_date: string
  location: string | null
  category: string | null
  event_group_id: string | null
}

export interface EventWithSlots {
  event: EventRead
  duty_slots_created: number
}

export interface DutySlotRead {
  id: string
  title: string
  date: string
  start_time: string | null
  end_time: string | null
  location: string | null
  category: string | null
  max_bookings: number
  current_bookings: number
  event_id: string
}

export interface BookingRead {
  id: string
  duty_slot_id: string
  user_id: string
  status: string
}

/** Create an event with auto-generated slots via the /events/with-slots endpoint. */
export async function createEventWithSlots(
  page: Page,
  opts: {
    name: string
    description?: string
    startDate?: string
    endDate?: string
    location?: string
    category?: string
    eventGroupId?: string
    startTime?: string
    endTime?: string
    slotDuration?: number
    peoplePerSlot?: number
  },
): Promise<EventWithSlots> {
  const startDate = opts.startDate ?? '2026-07-01'
  const endDate = opts.endDate ?? '2026-07-01'
  return api<EventWithSlots>(page, 'POST', '/events/with-slots', {
    name: opts.name,
    description: opts.description ?? null,
    start_date: startDate,
    end_date: endDate,
    location: opts.location ?? null,
    category: opts.category ?? null,
    event_group_id: opts.eventGroupId ?? null,
    schedule: {
      default_start_time: (opts.startTime ?? '10:00') + ':00',
      default_end_time: (opts.endTime ?? '12:00') + ':00',
      slot_duration_minutes: opts.slotDuration ?? 60,
      people_per_slot: opts.peoplePerSlot ?? 2,
      remainder_mode: 'drop',
      overrides: [],
      excluded_slots: [],
    },
  })
}

/** Delete an event. Admin token required. */
export async function deleteEvent(page: Page, id: string): Promise<void> {
  if (!id || id === 'undefined') return
  await api(page, 'DELETE', `/events/${id}`)
}

/** Publish an event (set status to published). */
export async function publishEvent(page: Page, id: string): Promise<EventRead> {
  return api<EventRead>(page, 'PATCH', `/events/${id}`, { status: 'published' })
}

/** List duty slots for an event. */
export async function listSlots(page: Page, eventId: string): Promise<DutySlotRead[]> {
  const res = await api<{ items: DutySlotRead[] }>(page, 'GET', `/duty-slots/?event_id=${eventId}&limit=200`)
  return res.items
}

/** Book a duty slot. */
export async function bookSlot(page: Page, slotId: string): Promise<BookingRead> {
  return api<BookingRead>(page, 'POST', '/bookings/', { duty_slot_id: slotId })
}

/** Cancel a booking. */
export async function cancelBooking(page: Page, bookingId: string): Promise<void> {
  await api(page, 'DELETE', `/bookings/${bookingId}`)
}
