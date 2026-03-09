import i18n from '@/locales/i18n'

export function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString(i18n.global.locale.value)
}

export function formatDateWithTime(d: {
  slot_date: string
  start_time?: string | null
  end_time?: string | null
}): string {
  let label = formatDate(d.slot_date)
  if (d.start_time || d.end_time) {
    const parts = [d.start_time ?? '', d.end_time ?? ''].filter(Boolean)
    label += ` (${parts.join(' – ')})`
  }
  return label
}
