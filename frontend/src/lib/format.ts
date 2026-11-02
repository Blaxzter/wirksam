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

/**
 * A `tel:` link for a phone number as people type it, or null when there is
 * nothing to dial. Phone numbers are free text, and a `tel:` URI allows no
 * spaces, slashes or brackets, so only the digits and a leading "+" are kept:
 * "0171 / 123 45 67" → "tel:01711234567". The "(0)" in "+49 (0)171 …" is the
 * national prefix, which must not be dialled after a country code, so it goes
 * too; without a country code a "(0…)" keeps its zero.
 */
export function telHref(phone: string | null | undefined): string | null {
  const raw = (phone ?? '').trim()
  const international = raw.startsWith('+') || raw.startsWith('00')
  const digits = (international ? raw.replace(/\(\s*0\s*\)/g, '') : raw).replace(/\D/g, '')
  if (!digits) return null
  return `tel:${raw.startsWith('+') ? '+' : ''}${digits}`
}

/**
 * First word of a name, skipping a "[DEMO]" style prefix: "Approve Carla",
 * "Good morning, Carla". Falls back to the whole (trimmed) name when there is
 * no word to take.
 */
export function firstName(name: string): string {
  const words = name
    .replace(/^\s*\[[^\]]*\]\s*/, '')
    .trim()
    .split(/\s+/)
  return words[0] || name.trim()
}

/** Two letters for an avatar fallback, skipping a "[DEMO]" style prefix. */
export function initials(name: string | null | undefined): string {
  const words = (name ?? '')
    .replace(/^\[[^\]]*\]\s*/, '')
    .split(/[\s@.]+/)
    .filter(Boolean)
  if (words.length === 0) return '?'
  const first = words[0]!.charAt(0)
  const second = words.length > 1 ? words[1]!.charAt(0) : words[0]!.charAt(1)
  return (first + second).toUpperCase()
}
