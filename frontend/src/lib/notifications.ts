/**
 * The inbox's notices in the browser: where one opens, which day it belongs
 * to, and how old it reads.
 *
 * Shared by the bell's dropdown and the inbox page, so a notice opens the
 * same place and reads the same age in both.
 */
import type { RouteLocationRaw } from 'vue-router'

import { parseServerDate } from '@/lib/server-time'

/** What a notice opens, which names its "Open …" link. */
export type NotificationTargetKind = 'invitation' | 'task' | 'team' | 'people' | 'event' | 'bookings'

export interface NotificationTarget {
  kind: NotificationTargetKind
  to: RouteLocationRaw
}

const text = (value: unknown): string | null =>
  typeof value === 'string' && value.length > 0 ? value : null

/**
 * Where a notice opens, from the ids its data carries; `null` when there is
 * nothing to open.
 *
 * An invitation opens the invitation itself, before its event: the event's
 * page is a 404 to someone not in a private event yet. Booking notices carry
 * their task too, and open the task.
 *
 * A notice about a person in an event (`event_id` and `user_id`, no team) is
 * a join request or an accepted invitation, and opens the event's People tab,
 * where the request is decided and the newcomer shows up. `public/sw.js` and
 * the backend's mail link (`channels/email.py`) follow the same rules.
 */
export function notificationTarget(
  data: Record<string, unknown> | null | undefined,
): NotificationTarget | null {
  if (!data) return null
  const token = text(data.token)
  if (token) return { kind: 'invitation', to: { name: 'invite-accept', params: { token } } }
  const taskId = text(data.task_id)
  // The task route's parameter is called `eventId`, but it is the task's id.
  if (taskId) return { kind: 'task', to: { name: 'task-detail', params: { eventId: taskId } } }
  const eventId = text(data.event_id)
  const teamId = text(data.team_id)
  // Team requests and decisions open the Teams page on that team.
  if (teamId && eventId)
    return {
      kind: 'team',
      to: { name: 'teams', params: { eventId }, query: { team: teamId } },
    }
  if (eventId && text(data.user_id))
    return {
      kind: 'people',
      to: { name: 'event-settings', params: { eventId }, query: { tab: 'people' } },
    }
  if (eventId) return { kind: 'event', to: { name: 'event-settings', params: { eventId } } }
  if (text(data.booking_id)) return { kind: 'bookings', to: { name: 'my-bookings' } }
  return null
}

export type DayGroup = 'today' | 'yesterday' | 'earlier'

/** Midnight before `d`, in the reader's own time zone. */
function startOfDay(d: Date): number {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime()
}

/** Which heading a notice sits under, by the reader's calendar day. */
export function dayGroup(date: Date, now: Date): DayGroup {
  const today = startOfDay(now)
  const day = startOfDay(date)
  if (day >= today) return 'today'
  // Not `today - 24h`: a day with a clock change is 23 or 25 hours long.
  const yesterday = startOfDay(new Date(now.getFullYear(), now.getMonth(), now.getDate() - 1))
  return day >= yesterday ? 'yesterday' : 'earlier'
}

/**
 * Notices under "Today", "Yesterday" and "Earlier", in the order they came
 * (newest first). Empty groups are left out; one without a readable date
 * counts as earlier.
 */
export function groupByDay<T extends { created_at: string }>(
  items: readonly T[],
  now: Date,
): { key: DayGroup; items: T[] }[] {
  const order: DayGroup[] = ['today', 'yesterday', 'earlier']
  const groups = new Map<DayGroup, T[]>()
  for (const item of items) {
    const date = parseServerDate(item.created_at)
    const key = date ? dayGroup(date, now) : 'earlier'
    const list = groups.get(key) ?? []
    list.push(item)
    groups.set(key, list)
  }
  return order.filter((key) => groups.has(key)).map((key) => ({ key, items: groups.get(key)! }))
}

type Translate = (key: string, named?: Record<string, unknown>) => string

/**
 * How old a notice reads: minutes or hours today ("5 min ago"), "Yesterday,
 * 18:40", then the date with its time. `hour12` is the reader's clock setting
 * (`useFormatters().hour12`); left out, the language decides.
 */
export function noticeTime(
  iso: string,
  now: Date,
  t: Translate,
  locale: string,
  hour12?: boolean,
): string {
  const date = parseServerDate(iso)
  if (!date) return ''
  const time = date.toLocaleTimeString(locale, { hour: '2-digit', minute: '2-digit', hour12 })
  switch (dayGroup(date, now)) {
    case 'today': {
      const minutes = Math.max(0, Math.floor((now.getTime() - date.getTime()) / 60_000))
      if (minutes < 1) return t('notifications.timeAgo.justNow')
      if (minutes < 60) return t('notifications.timeAgo.minutes', { n: minutes })
      return t('notifications.timeAgo.hours', { n: Math.floor(minutes / 60) })
    }
    case 'yesterday':
      return t('notifications.time.yesterday', { time })
    default:
      return date.toLocaleString(locale, {
        weekday: 'short',
        day: 'numeric',
        month: 'short',
        ...(date.getFullYear() === now.getFullYear() ? {} : { year: 'numeric' }),
        hour: '2-digit',
        minute: '2-digit',
        hour12,
      })
  }
}
