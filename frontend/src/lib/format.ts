import i18n from '@/locales/i18n'

export function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString(i18n.global.locale.value)
}

/**
 * Minutes as decimal hours in the active locale: 450 → "7.5" / "7,5".
 *
 * Decimal rather than "7:30" because that is how the hours are summed and
 * exported; two fraction digits keep quarter hours exact.
 */
export function formatHours(minutes: number): string {
  return new Intl.NumberFormat(i18n.global.locale.value, {
    maximumFractionDigits: 2,
  }).format(minutes / 60)
}
