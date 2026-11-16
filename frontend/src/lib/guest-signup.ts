/**
 * The public sign-up form of a shared list: what it checks before sending
 * anything, how it reads the server's own refusal of a field, and the link a
 * guest keeps to manage their sign-ups.
 *
 * Every check mirrors `backend/app/logic/shared_lists/normalize.py`, which has
 * the last word. Doing them here first only saves a round trip and lets the
 * form point at the field; the messages are i18n keys, so the view phrases them.
 */
import type { PublicSharedList, ValidationErrorItem } from '@/client/types.gen'
import { looksLikeEmail } from '@/lib/email'

export type GuestField = 'name' | 'email' | 'phone'

/** What the guest typed. Kept across a chain, so the next shift needs no retyping. */
export interface GuestFields {
  name: string
  email: string
  phone: string
  /** The reminder the day before; sent only together with an address. */
  remind: boolean
}

export type AskMode = PublicSharedList['ask_email']

/** A field that failed, mapped to the `guestSignup.validation.*` key saying why. */
export type FieldProblems = Partial<Record<GuestField, string>>

/**
 * How long the done step waits for a touch before it starts over for the next
 * person: long enough to read it and copy a link, short enough that a tablet
 * left at the stand does not keep showing someone's address.
 */
export const IDLE_RESET_MS = 120_000

/** How the guest pages name a shift's day: "Friday, 20 November". */
export const LONG_DAY: Intl.DateTimeFormatOptions = {
  weekday: 'long',
  day: 'numeric',
  month: 'long',
}

/** "Friday, 20 November, 10:00 – 12:00", leaving out a part that is empty. */
export function dayAndTime(day: string, time: string): string {
  return [day, time].filter(Boolean).join(', ')
}

/** `normalize_name`: at least two characters once the spaces are collapsed. */
const NAME_MIN_LENGTH = 2

/** `normalize_phone`: digits, spaces and `+ ( ) / - .`, 5 to 30 characters. */
const PHONE_PATTERN = /^[0-9+()/. -]{5,30}$/

/** What each field says when the server refuses its format. */
const INVALID: Record<GuestField, string> = {
  name: 'guestSignup.validation.name',
  email: 'guestSignup.validation.emailInvalid',
  phone: 'guestSignup.validation.phoneInvalid',
}

/** An empty field is fine unless the list asks for it; a filled one must look right. */
function checkAsked(
  value: string,
  mode: AskMode,
  valid: (value: string) => boolean,
  keys: { required: string; invalid: string },
): string | undefined {
  if (mode === 'off') return undefined
  if (!value) return mode === 'required' ? keys.required : undefined
  return valid(value) ? undefined : keys.invalid
}

/** Every field that would be refused, in the order the form lays them out. */
export function checkGuestFields(
  fields: GuestFields,
  askEmail: AskMode,
  askPhone: AskMode,
): FieldProblems {
  const problems: FieldProblems = {}
  if (fields.name.trim().replace(/\s+/g, ' ').length < NAME_MIN_LENGTH) {
    problems.name = INVALID.name
  }
  const email = checkAsked(fields.email.trim(), askEmail, looksLikeEmail, {
    required: 'guestSignup.validation.emailRequired',
    invalid: INVALID.email,
  })
  if (email) problems.email = email
  const phone = checkAsked(fields.phone.trim(), askPhone, (v) => PHONE_PATTERN.test(v), {
    required: 'guestSignup.validation.phoneRequired',
    invalid: INVALID.phone,
  })
  if (phone) problems.phone = phone
  return problems
}

const isGuestField = (value: unknown): value is GuestField =>
  value === 'name' || value === 'email' || value === 'phone'

/**
 * The field a 422 from the server names, with what to say about it, or `null`
 * when it names none of them. The body's own error text is pydantic's English,
 * which a guest should never have to read.
 */
export function rejectedField(
  errors: readonly ValidationErrorItem[] | undefined,
): { field: GuestField; key: string } | null {
  for (const item of errors ?? []) {
    const [where, field] = item.loc
    if (where === 'body' && isGuestField(field)) return { field, key: INVALID[field] }
  }
  return null
}

/** Which `retention.*` sentence names what is kept: never data that was not asked for. */
export type RetentionVariant = 'name' | 'nameEmail' | 'namePhone' | 'all'

/**
 * The retention sentence for what a guest's sign-ups store: always the name,
 * and the address and the phone number only where there are any (the form and
 * the done page go by what the list asks, the manage page by what is stored).
 */
export function retentionVariant(email: boolean, phone: boolean): RetentionVariant {
  if (email && phone) return 'all'
  if (email) return 'nameEmail'
  return phone ? 'namePhone' : 'name'
}

/**
 * The page a guest manages their sign-ups on. The token rides in the
 * fragment, which no server log or referrer ever sees; `origin` is read at
 * call time, so the module loads where there is no `window`.
 */
export function guestManageUrl(token: string, origin: string = window.location.origin): string {
  return `${origin.replace(/\/+$/, '')}/guest-signup#${token}`
}
