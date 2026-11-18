/**
 * Shared lists ("Geteilte Listen") as the organisers' screens show them: the
 * public link, the status pill, the fill level, what a list asks for, when it
 * closes and how long ago someone signed up.
 *
 * Every function returns data or i18n keys, never translated text, so the
 * views stay free to phrase and format; the keys live in `sharedLists.json`.
 */
import { isSwitchOn, useAppConfig } from '@/composables/useAppConfig'

import type { BadgeVariants } from '@/components/ui/badge'

import type { EventRead, SharedListRow, SharedListSignup } from '@/client/types.gen'
import { parseServerDate } from '@/lib/server-time'
import { type StaffingStatus, staffingStatus } from '@/lib/venue-map'

export type EffectiveStatus = SharedListRow['effective_status']
export type AskMode = 'required' | 'optional' | 'off'

/**
 * Whether the selected event offers the shared-lists page to this viewer: the
 * feature is switched on, and the viewer runs the event or is in charge of one
 * of its tasks. A demo shares too; its lists mail nobody and go with it. The
 * server decides per request; this keeps the navigation from offering a page
 * that would answer 403.
 */
export function canUseSharedLists(
  event: Pick<EventRead, 'can_manage' | 'managed_task_count'> | null | undefined,
): boolean {
  if (!event) return false
  if (!isSwitchOn(useAppConfig().SHARED_LISTS_ENABLED)) return false
  return event.can_manage || (event.managed_task_count ?? 0) > 0
}

/**
 * A person in charge whom the event admins stopped from sharing: the server
 * refuses their fixes to `list` (resume, extend), so none is offered.
 */
export function lockedForManager(
  list: Pick<SharedListRow, 'access'>,
  event: Pick<EventRead, 'managers_share_lists'> | null | undefined,
): boolean {
  return list.access === 'manager' && event?.managers_share_lists === false
}

/**
 * The link people open. `origin` defaults to this deployment's own, read at
 * call time, so the module stays importable where there is no `window`.
 */
export function sharedListUrl(code: string, origin: string = window.location.origin): string {
  return `${origin.replace(/\/+$/, '')}/l/${encodeURIComponent(code)}`
}

export interface StatusBadge {
  variant: NonNullable<BadgeVariants['variant']>
  /** `sharedLists.status.<status>` */
  labelKey: string
  /** A live list's dot pulses; the view keeps it still under `motion-reduce`. */
  pulse: boolean
}

const STATUS_VARIANTS: Record<EffectiveStatus, StatusBadge['variant']> = {
  live: 'default',
  paused: 'warning',
  expired: 'outline',
  ended: 'outline',
}

export function effectiveStatusBadge(status: EffectiveStatus): StatusBadge {
  return {
    variant: STATUS_VARIANTS[status],
    labelKey: `sharedLists.status.${status}`,
    pulse: status === 'live',
  }
}

/**
 * How full a list or task is, from its free places and capacity, on the same
 * scale (and with the same `bg-staff-*` colours) as the venue map: `full` once
 * every place is taken, `partial` from half, `short` below, `none` without
 * places.
 */
export function fillLevel(free: number, cap: number): StaffingStatus {
  return staffingStatus({ booked: cap - Math.max(0, free), capacity: cap })
}

/**
 * What the public form asks for, as `sharedLists.settings.ask.*` keys: the
 * name always, then the address and the phone number unless they are off.
 */
export function askedFieldKeys(askEmail: AskMode, askPhone: AskMode): string[] {
  const keys = ['sharedLists.settings.ask.name']
  if (askEmail !== 'off') keys.push(`sharedLists.settings.ask.email.${askEmail}`)
  if (askPhone !== 'off') keys.push(`sharedLists.settings.ask.phone.${askPhone}`)
  return keys
}

/** How the caller writes a date (`YYYY-MM-DD`) and a time of day (`HH:MM`). */
export interface DateTimeFormatters {
  date: (isoDate: string) => string
  time: (time: string) => string
}

export interface MessageRef {
  key: string
  params: Record<string, string>
}

/**
 * When the list closes, as a `sharedLists.settings.ends.*` key and its params:
 *
 * - `lastShift` ({date}, {time}): when its last shift starts, on the event's
 *   clock (`closes_at`);
 * - `lastShiftNone`: it closes with its last shift, and there is none ahead;
 * - `date` ({date}): at the end of `ends_on`;
 * - `manual`: when someone ends it.
 */
export function endsSummary(
  list: Pick<SharedListRow, 'ends_mode' | 'ends_on' | 'closes_at'>,
  format: DateTimeFormatters,
): MessageRef {
  if (list.ends_mode === 'manual') return { key: 'sharedLists.settings.ends.manual', params: {} }
  if (list.ends_mode === 'date' && list.ends_on) {
    return { key: 'sharedLists.settings.ends.date', params: { date: format.date(list.ends_on) } }
  }
  if (list.ends_mode === 'last_shift' && list.closes_at) {
    // A wall-clock time on the event's clock, `YYYY-MM-DDTHH:MM:SS`: read as
    // written, never through `Date`, which would move it into the browser's zone.
    return {
      key: 'sharedLists.settings.ends.lastShift',
      params: {
        date: format.date(list.closes_at.slice(0, 10)),
        time: format.time(list.closes_at.slice(11, 16)),
      },
    }
  }
  return { key: 'sharedLists.settings.ends.lastShiftNone', params: {} }
}

/** A sign-up younger than this reads "just now". */
export const JUST_NOW_MINUTES = 5

export interface RelativeTime {
  /** `sharedLists.signups.when.{justNow,today,yesterday,daysAgo}` */
  key: string
  /** Whole days ago, for `daysAgo`; pass it as the plural count. */
  count: number
}

const MS_PER_DAY = 86_400_000

function startOfDay(date: Date): number {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime()
}

/**
 * "gerade eben", "heute", "gestern" or "vor N Tagen" for a sign-up's
 * `created_at` (naive UTC), counted in the viewer's calendar days. `null` for a
 * value that cannot be read.
 */
export function relativeSignupTime(createdAt: string, now: Date = new Date()): RelativeTime | null {
  const created = parseServerDate(createdAt)
  if (!created) return null
  if (now.getTime() - created.getTime() < JUST_NOW_MINUTES * 60_000) {
    return { key: 'sharedLists.signups.when.justNow', count: 0 }
  }
  const days = Math.round((startOfDay(now) - startOfDay(created)) / MS_PER_DAY)
  if (days <= 0) return { key: 'sharedLists.signups.when.today', count: 0 }
  if (days === 1) return { key: 'sharedLists.signups.when.yesterday', count: 1 }
  return { key: 'sharedLists.signups.when.daysAgo', count: days }
}

/**
 * The sign-ups beyond `selected` that erasing their people's data takes along:
 * those pooled with them under a confirmed address, perhaps other people's.
 * The rows of one guest account share its address, and each says how many
 * others the account holds; a chain's rows count none.
 */
export function pooledBeyond(
  selected: readonly Pick<SharedListSignup, 'email' | 'pooled_signups'>[],
): number {
  const accounts = new Map<string, { others: number; picked: number }>()
  selected.forEach((row, index) => {
    if (row.pooled_signups === 0) return
    // Without an address to go by, a row counts alone: better to warn of too
    // many than of too few.
    const key = row.email ?? `#${index}`
    const account = accounts.get(key) ?? { others: row.pooled_signups, picked: 0 }
    account.picked += 1
    accounts.set(key, account)
  })
  let beyond = 0
  for (const { others, picked } of accounts.values()) beyond += Math.max(0, others + 1 - picked)
  return beyond
}
