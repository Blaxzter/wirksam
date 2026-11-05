/**
 * The time zones an event can be in: IANA names, as the backend stores them.
 *
 * Nothing here runs at module scope. The lists are only asked for on signed-in
 * pages, and some browsers cannot provide them at all.
 */

/** For a browser without `Intl.supportedValuesOf`: the common ones, by region. */
const COMMON_ZONES = [
  'Africa/Johannesburg',
  'Africa/Lagos',
  'America/Chicago',
  'America/Los_Angeles',
  'America/New_York',
  'America/Sao_Paulo',
  'Asia/Dubai',
  'Asia/Kolkata',
  'Asia/Shanghai',
  'Asia/Tokyo',
  'Australia/Sydney',
  'Europe/Berlin',
  'Europe/Lisbon',
  'Europe/London',
  'Europe/Paris',
]

/** The zone this device is set to. */
export function browserTimeZone(): string {
  return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'
}

/**
 * Every zone to choose from, sorted, with `include` among them: browsers leave
 * out `UTC`, and can name the device's own zone by a name they don't list.
 */
export function timeZoneNames(...include: string[]): string[] {
  const listed =
    typeof Intl.supportedValuesOf === 'function'
      ? Intl.supportedValuesOf('timeZone')
      : COMMON_ZONES
  return [...new Set([...listed, 'UTC', ...include])].sort()
}

/** How a zone is written for people: `America/New York`. */
export function timeZoneLabel(zone: string): string {
  return zone.replaceAll('_', ' ')
}

/** Whether `zone` is what someone searching for `query` is after. */
export function matchesTimeZone(zone: string, query: string): boolean {
  return timeZoneLabel(zone)
    .toLocaleLowerCase()
    .includes(query.trim().replaceAll('_', ' ').toLocaleLowerCase())
}

/** The browser's own name for a zone, or the name if it doesn't know it. */
function canonical(zone: string): string {
  try {
    return new Intl.DateTimeFormat('en', { timeZone: zone }).resolvedOptions().timeZone
  } catch {
    return zone
  }
}

/** The same zone, also under two names (`Asia/Calcutta` and `Asia/Kolkata`). */
export function isSameTimeZone(a: string, b: string): boolean {
  return a === b || canonical(a) === canonical(b)
}
