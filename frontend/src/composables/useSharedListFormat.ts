import { useI18n } from 'vue-i18n'

import { useFormatters } from '@/composables/useFormatters'

import { describeDays } from '@/lib/shared-list-share-message'

/**
 * How the shared-list wizard writes days and times, in the viewer's language
 * and clock preference. Dates are `YYYY-MM-DD` and times `HH:MM[:SS]`, read as
 * written: a shift's wall clock, never moved into the browser's zone.
 */
export function useSharedListFormat() {
  const { t, locale } = useI18n()
  const { formatDateLabel, formatDaySpan, formatTime, formatTimeRange } = useFormatters()

  /** "Sa., 6.12." */
  const shortDay = (date: string) =>
    formatDateLabel(date, { weekday: 'short', day: 'numeric', month: 'numeric' })

  /** "Samstag, 6. Dezember" */
  const longDay = (date: string) =>
    formatDateLabel(date, { weekday: 'long', day: 'numeric', month: 'long' })

  /** "A, B und C" */
  const list = (items: readonly string[]) =>
    new Intl.ListFormat(locale.value, { style: 'long', type: 'conjunction' }).format(items)

  /** The days a task or list runs on, as briefly as is still exact. */
  const daysText = (dates: readonly string[]) =>
    describeDays(dates, {
      span: formatDaySpan,
      day: shortDay,
      list,
      spread: (span, count) => t('sharedLists.text.daysWithin', { span, count }),
    })

  /** "10:00 – 12:00", or '' for a shift without times. */
  const timeRange = (start: string | null, end: string | null) => formatTimeRange(start, end)

  return { shortDay, longDay, list, daysText, timeRange, formatTime, formatDaySpan }
}
