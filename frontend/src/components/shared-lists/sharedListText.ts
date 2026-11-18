import { useI18n } from 'vue-i18n'

import { useFormatters } from '@/composables/useFormatters'
import { useSharedListFormat } from '@/composables/useSharedListFormat'

import type { SharedListRow, SharedListSignup } from '@/client/types.gen'
import { endsSummary, relativeSignupTime } from '@/lib/shared-lists'

/**
 * The wording the shared-list screens share, in the active language: task
 * names in quotes, the days something runs, "today / tomorrow / in 3 days",
 * when a list closes, and the name of a guest whose data was erased.
 */
export function useSharedListText() {
  const { t } = useI18n()
  const { formatDateLabel, formatTime, formatTimeRange } = useFormatters()
  // "a, b and c" and the days something runs on, worded as in the wizard.
  const { list: joinList, daysText } = useSharedListFormat()

  /**
   * „Bar“ und „Kasse“, or „Bar“, „Kasse“ und 3 weitere when `total` says
   * there are more than the names given (the server sends the first two).
   */
  function quotedNames(names: readonly string[], total: number = names.length): string {
    const quoted = names.map((name) => t('sharedLists.text.quoted', { name }))
    const more = total - quoted.length
    if (more <= 0) return joinList(quoted)
    return t('sharedLists.text.andMore', { names: quoted.join(', '), count: more }, more)
  }

  /** "today", "tomorrow" or "in 3 days", for a number of days ahead. */
  function inDays(days: number): string {
    const ahead = Math.max(0, days)
    return t('sharedLists.text.inDays', { count: ahead }, ahead)
  }

  /** How the settings summary says when a list closes. */
  function endsText(list: Pick<SharedListRow, 'ends_mode' | 'ends_on' | 'closes_at'>): string {
    const { key, params } = endsSummary(list, {
      date: (iso) => formatDateLabel(iso, { weekday: 'short', day: 'numeric', month: 'long' }),
      time: formatTime,
    })
    return t(key, params)
  }

  /** The "Open until" column: the moment it closes, or how it closes when there is none. */
  function closesText(
    row: Pick<SharedListRow, 'effective_status' | 'ends_mode' | 'ends_on' | 'closes_at'>,
  ): string {
    if (row.effective_status === 'ended') return t('sharedLists.rows.closesEnded')
    if (row.ends_mode === 'manual') return t('sharedLists.rows.closesManual')
    const short = { weekday: 'short', day: 'numeric', month: 'short' } as const
    if (row.ends_mode === 'date' && row.ends_on) return formatDateLabel(row.ends_on, short)
    if (!row.closes_at) return t('sharedLists.rows.closesNone')
    return t('sharedLists.rows.closesAt', {
      date: formatDateLabel(row.closes_at.slice(0, 10), short),
      time: formatTime(row.closes_at.slice(11, 16)),
    })
  }

  /** "Sa., 12. Juli, 10:00 – 12:00": when a shift is, on its event's clock. */
  function shiftText(date: string, start?: string | null, end?: string | null): string {
    const day = formatDateLabel(date, { weekday: 'short', day: 'numeric', month: 'short' })
    const time = formatTimeRange(start, end)
    return time ? `${day}, ${time}` : day
  }

  /** "just now", "yesterday", "3 days ago" for when someone signed up. */
  function signedUpWhen(createdAt: string): string {
    const when = relativeSignupTime(createdAt)
    return when ? t(when.key, { count: when.count }, when.count) : ''
  }

  /** A guest's name, or "Guest (deleted)" once their data is gone. */
  function personName(name: string | null | undefined, isGuest: boolean, fallback = '?'): string {
    if (name) return name
    return isGuest ? t('sharedLists.guest.erased') : fallback
  }

  /**
   * One sign-up as a screen reader tells it apart from the others of the same
   * person: "Lena Gast (Aufräumen, Do., 19. Nov., 18:00 – 20:00)".
   */
  function signupLabel(
    signup: Pick<SharedListSignup, 'name' | 'task_name' | 'shift_date' | 'start_time' | 'end_time'>,
  ): string {
    return t('sharedLists.signups.rowLabel', {
      name: personName(signup.name, true),
      task: signup.task_name,
      when: shiftText(signup.shift_date, signup.start_time, signup.end_time),
    })
  }

  return {
    joinList,
    quotedNames,
    daysText,
    inDays,
    endsText,
    closesText,
    shiftText,
    signedUpWhen,
    personName,
    signupLabel,
  }
}
