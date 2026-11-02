/**
 * Volunteer vouchers in the browser: reading and showing the six-character
 * codes, counting a code down, and putting a balance's history in order.
 *
 * The server is the authority on every one of these. What lives here is what
 * the screens need before a request is worth sending: whether something typed
 * or scanned can be a code at all, and how to show one.
 */
import type { VoucherAccount, VoucherEntryRead, VoucherShift } from '@/client/types.gen'
import { parseServerDate } from '@/lib/server-time'

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null

/** The server's alphabet (`app/logic/vouchers.py`): no 0, O, 1, I or L. */
export const VOUCHER_CODE_ALPHABET = '23456789ABCDEFGHJKMNPQRSTUVWXYZ'
export const VOUCHER_CODE_LENGTH = 6
/** What the QR code holds in front of the code. */
export const VOUCHER_QR_PREFIX = 'WV1:'

const CODE_PATTERN = new RegExp(`^[${VOUCHER_CODE_ALPHABET}]{${VOUCHER_CODE_LENGTH}}$`)

/**
 * A typed or pasted code in the form the server stores, or `null` when it
 * cannot be one. Forgives what people type: lower case, the dash the screen
 * shows, spaces, and the QR prefix if someone pastes the scanned text.
 */
export function normalizeVoucherCode(input: string | null | undefined): string | null {
  if (!input) return null
  let code = input.trim().toUpperCase()
  if (code.startsWith(VOUCHER_QR_PREFIX)) code = code.slice(VOUCHER_QR_PREFIX.length)
  code = code.replace(/[\s-]/g, '')
  return CODE_PATTERN.test(code) ? code : null
}

/**
 * The code inside a scanned QR code, or `null` for any other QR code (a URL on
 * a poster, a ticket). Stricter than typing: only exactly what our own codes
 * hold, so a stray code in front of the camera is never sent as a guess.
 */
export function parseVoucherPayload(text: string | null | undefined): string | null {
  if (!text) return null
  const trimmed = text.trim()
  if (!trimmed.startsWith(VOUCHER_QR_PREFIX)) return null
  const code = trimmed.slice(VOUCHER_QR_PREFIX.length)
  return CODE_PATTERN.test(code) ? code : null
}

/** `K7M4QX` → `K7M-4QX`, the way it is shown and read out. */
export function formatVoucherCode(code: string): string {
  if (code.length !== VOUCHER_CODE_LENGTH) return code
  return `${code.slice(0, 3)}-${code.slice(3)}`
}

/**
 * Whole seconds a code has left, counted from when its response arrived rather
 * than from `expires_at`, so a phone whose clock is off still counts right.
 */
export function secondsLeft(receivedAtMs: number, ttlSeconds: number, nowMs: number): number {
  const left = ttlSeconds - (nowMs - receivedAtMs) / 1000
  return Math.max(0, Math.ceil(left))
}

export type VoucherHistoryItem =
  | { kind: 'shift'; key: string; shift: VoucherShift }
  | { kind: 'entry'; key: string; entry: VoucherEntryRead }

/**
 * Where one item sits on the history's time line, in milliseconds. Shifts sort
 * by their end and entries by when they were made; both arrive as naive UTC, so
 * both go through `parseServerDate`. Unreadable times sort last.
 */
export function historySortKey(item: VoucherHistoryItem): number {
  const iso = item.kind === 'shift' ? item.shift.ends_at : item.entry.created_at
  return parseServerDate(iso)?.getTime() ?? Number.NEGATIVE_INFINITY
}

/**
 * The most a correction may take away, so that the person is not left with
 * less than nothing; the server refuses more (`409
 * voucher.correction_exceeds_available`). An edit replaces the correction's
 * own amount, which is given back first: changing a −1 can take one more than
 * `available`, changing a +2 two fewer.
 */
export function correctionTakeAwayMax(available: number, currentAmount = 0): number {
  return Math.max(0, available - currentAmount)
}

/**
 * The least an edited correction may add. Lowering an earlier addition takes
 * vouchers away too, and is held to the same limit: changing a +5 with 2 left
 * takes 3 back at most, so it must stay at +3 or more. 1 for a new correction,
 * and whenever what is left covers the old amount.
 */
export function correctionAddMin(available: number, currentAmount = 0): number {
  return Math.max(1, currentAmount - available)
}

/**
 * The shifts that earned vouchers and every redemption and correction, newest
 * first. Shifts still to come are left out: they have earned nothing yet. A
 * settled shift (frozen before its task or shift changed, or went) is listed
 * like any other earned one, from its snapshot; its `shift_id` and `task_id`
 * are null once those are gone.
 */
export function voucherHistory(account: Pick<VoucherAccount, 'shifts' | 'entries'>) {
  const items: VoucherHistoryItem[] = [
    ...account.shifts
      .filter((s) => s.completed)
      .map((shift) => ({ kind: 'shift' as const, key: `shift-${shift.booking_id}`, shift })),
    ...account.entries.map((entry) => ({ kind: 'entry' as const, key: `entry-${entry.id}`, entry })),
  ]
  return items.sort((a, b) => historySortKey(b) - historySortKey(a))
}

type RandomSource = {
  randomUUID?: () => string
  getRandomValues: (array: Uint8Array<ArrayBuffer>) => Uint8Array<ArrayBuffer>
}

/**
 * A fresh idempotency key for one redemption. `crypto.randomUUID` exists only
 * in a secure context, and a stand's phone on the venue Wi-Fi may not be one,
 * so this falls back to building a version 4 UUID from random bytes.
 */
export function newRequestId(source: RandomSource = crypto): string {
  if (typeof source.randomUUID === 'function') return source.randomUUID()
  const bytes = source.getRandomValues(new Uint8Array(16))
  bytes[6] = (bytes[6] & 0x0f) | 0x40
  bytes[8] = (bytes[8] & 0x3f) | 0x80
  const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('')
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`
}

/** How long a code that was just handled must be out of view before it counts again. */
export const SAME_CODE_IGNORE_MS = 10_000

/**
 * Decides which scanner detections are worth acting on. The scanner reports a
 * code on every frame it reads, so the code just redeemed would otherwise be
 * checked again the moment the confirm closes, while it is still in front of
 * the camera. A code is ignored once handled until a different one has been
 * seen, or until it has been out of view for `SAME_CODE_IGNORE_MS`: every
 * sighting of it starts that wait again.
 */
export function createDetectionGate(ignoreMs = SAME_CODE_IGNORE_MS) {
  let last: { code: string; at: number } | null = null
  return {
    /** Whether to act on `code`; remembers it when the answer is yes. */
    accept(code: string, nowMs: number): boolean {
      if (last && last.code === code && nowMs - last.at < ignoreMs) {
        last.at = nowMs
        return false
      }
      last = { code, at: nowMs }
      return true
    },
    /** Count `code` as handled just now, e.g. when the confirm for it closes. */
    remember(code: string, nowMs: number) {
      last = { code, at: nowMs }
    },
    /** Forget the last code, so even the same one is accepted again. */
    reset() {
      last = null
    },
  }
}

/** Why the camera could not be used, as the redeem page tells it. */
export type CameraProblem = 'denied' | 'no-camera' | 'other'

const DENIED_ERRORS = new Set(['NotAllowedError', 'SecurityError', 'PermissionDeniedError'])
const NO_CAMERA_ERRORS = new Set(['NotFoundError', 'OverconstrainedError', 'DevicesNotFoundError'])

/**
 * What went wrong when the scanner would not start. `qr-scanner` swallows the
 * browser's own error and throws `'Camera not found.'` for everything, a
 * refused permission included, so the permission's state (from the
 * Permissions API, when the browser has one) decides first: a refusal is by
 * far the most common reason at a stand, and the one the redeemer can fix.
 */
export function classifyCameraError(
  error: unknown,
  permission: PermissionState | null = null,
): CameraProblem {
  if (permission === 'denied') return 'denied'
  if (error === 'Camera not found.') return 'no-camera'
  const name = isRecord(error) && typeof error.name === 'string' ? error.name : ''
  if (DENIED_ERRORS.has(name)) return 'denied'
  if (NO_CAMERA_ERRORS.has(name)) return 'no-camera'
  return 'other'
}

export type CodeUsedDetails = {
  amount: number | null
  taskName: string | null
  actorName: string | null
  usedAt: Date | null
}

/**
 * What a `409 voucher.code_used` answer says about the earlier redemption, so
 * the redeemer reads "Already redeemed: 2 at Bar, 14:03" instead of an error.
 * `null` for any other error, or one without those details.
 */
export function codeUsedDetails(error: unknown): CodeUsedDetails | null {
  if (!isRecord(error) || !isRecord(error.response)) return null
  const data = error.response.data
  if (!isRecord(data)) return null
  const code = typeof data.code === 'string' ? data.code : undefined
  const typeCode =
    typeof data.type === 'string' && data.type.startsWith('urn:problem:')
      ? data.type.slice('urn:problem:'.length)
      : undefined
  if ((code ?? typeCode) !== 'voucher.code_used') return null
  if (typeof data.amount !== 'number' || typeof data.task_name !== 'string') return null
  return {
    amount: data.amount,
    taskName: data.task_name,
    actorName: typeof data.actor_name === 'string' ? data.actor_name : null,
    usedAt: typeof data.used_at === 'string' ? parseServerDate(data.used_at) : null,
  }
}
