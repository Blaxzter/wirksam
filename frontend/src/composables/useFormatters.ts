import { useI18n } from 'vue-i18n'

export function useFormatters() {
  const { locale } = useI18n()

  const formatTime = (time: string | null | undefined): string => {
    if (!time) return ''
    return time.substring(0, 5)
  }

  const formatDateLabel = (
    dateStr: string,
    options: Intl.DateTimeFormatOptions = { weekday: 'short', month: 'short', day: 'numeric' },
  ): string => {
    const d = new Date(dateStr + 'T00:00:00')
    return d.toLocaleDateString(locale.value, options)
  }

  return { formatTime, formatDateLabel }
}
