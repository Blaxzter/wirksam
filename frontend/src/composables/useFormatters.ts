import { computed } from 'vue'

import { useI18n } from 'vue-i18n'

import { useAuthStore } from '@/stores/auth'

type TimeFormatPref = 'locale' | 'h12' | 'h24'

function parseClockTime(time: string): Date | null {
  // "HH:mm" or "HH:mm:ss" → today's Date with that wall-clock time
  const [h, m] = time.split(':').map(Number)
  if (Number.isNaN(h) || Number.isNaN(m)) return null
  const d = new Date()
  d.setHours(h, m, 0, 0)
  return d
}

export function useFormatters() {
  const { locale } = useI18n()
  const authStore = useAuthStore()

  const hour12 = computed<boolean | undefined>(() => {
    const pref = (authStore.profile?.time_format ?? 'locale') as TimeFormatPref
    if (pref === 'h12') return true
    if (pref === 'h24') return false
    return undefined
  })

  const formatTime = (time: string | null | undefined): string => {
    if (!time) return ''
    const d = parseClockTime(time)
    if (!d) return ''
    return d.toLocaleTimeString(locale.value, {
      hour: '2-digit',
      minute: '2-digit',
      hour12: hour12.value,
    })
  }

  const formatTimeRange = (
    start: string | null | undefined,
    end: string | null | undefined,
  ): string => {
    const s = start ? formatTime(start) : ''
    const e = end ? formatTime(end) : ''
    if (s && e) return `${s} – ${e}`
    if (s) return s
    if (e) return `– ${e}`
    return ''
  }

  const formatDateLabel = (
    dateStr: string,
    options: Intl.DateTimeFormatOptions = { weekday: 'short', month: 'short', day: 'numeric' },
  ): string => {
    const d = new Date(dateStr + 'T00:00:00')
    return d.toLocaleDateString(locale.value, options)
  }

  const formatDate = (dateStr: string): string => {
    return new Date(dateStr).toLocaleDateString(locale.value)
  }

  /**
   * "17.–19. Juli", "July 17 – August 2": the days something runs, for a
   * header line. The year only appears when either end is not in this year;
   * one day, or an end before the start, gives that one day.
   */
  const formatDaySpan = (start: string | null | undefined, end?: string | null): string => {
    if (!start) return ''
    const from = new Date(start + 'T00:00:00')
    const to = new Date((end || start) + 'T00:00:00')
    if (Number.isNaN(from.getTime()) || Number.isNaN(to.getTime())) return ''
    const thisYear = new Date().getFullYear()
    const options: Intl.DateTimeFormatOptions = { day: 'numeric', month: 'long' }
    if (from.getFullYear() !== thisYear || to.getFullYear() !== thisYear) options.year = 'numeric'
    const fmt = new Intl.DateTimeFormat(locale.value, options)
    return to > from ? fmt.formatRange(from, to) : fmt.format(from)
  }

  /**
   * "Today", "Tomorrow", "in 3 days" — and a plain date once that stops being
   * the useful answer.
   *
   * `Intl.RelativeTimeFormat` with `numeric: 'auto'` is what turns -1/0/1 into
   * words, in whichever language is loaded, so this needs no message keys of
   * its own. Beyond a week "in 9 days" is harder to act on than the date, so
   * that is where it hands over.
   */
  const formatRelativeDay = (
    dateStr: string,
    options: Intl.DateTimeFormatOptions = { weekday: 'short', month: 'short', day: 'numeric' },
  ): string => {
    const target = new Date(dateStr + 'T00:00:00')
    if (Number.isNaN(target.getTime())) return ''
    const today = new Date()
    today.setHours(0, 0, 0, 0)
    const days = Math.round((target.getTime() - today.getTime()) / 86_400_000)
    if (Math.abs(days) > 6) return formatDateLabel(dateStr, options)
    return new Intl.RelativeTimeFormat(locale.value, { numeric: 'auto' }).format(days, 'day')
  }

  const formatDateWithTime = (d: {
    slot_date: string
    start_time?: string | null
    end_time?: string | null
  }): string => {
    let label = formatDate(d.slot_date)
    if (d.start_time || d.end_time) {
      const parts = [
        d.start_time ? formatTime(d.start_time) : '',
        d.end_time ? formatTime(d.end_time) : '',
      ].filter(Boolean)
      label += ` (${parts.join(' – ')})`
    }
    return label
  }

  const formatDateTime = (
    isoStr: string,
    options: Intl.DateTimeFormatOptions = { month: 'short', day: 'numeric' },
  ): string => {
    return new Date(isoStr).toLocaleString(locale.value, {
      ...options,
      hour: '2-digit',
      minute: '2-digit',
      hour12: hour12.value,
    })
  }

  return {
    formatTime,
    formatTimeRange,
    formatDateLabel,
    formatDate,
    formatDaySpan,
    formatRelativeDay,
    formatDateWithTime,
    formatDateTime,
    hour12,
  }
}
