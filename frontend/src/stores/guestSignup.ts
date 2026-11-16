import { computed, reactive, ref } from 'vue'

import { defineStore } from 'pinia'

import { client } from '@/client/client.gen'
import type {
  GuestConfirmResult,
  GuestSignupManage,
  PublicSharedList,
  PublicShift,
  PublicSignupRequest,
  PublicSignupResult,
  VoucherPassRead,
  VoucherPassStatus,
} from '@/client/types.gen'
import { type NormalizedApiError, normalizeApiError, toastApiError } from '@/lib/api-errors'
import { type GuestField, type GuestFields, rejectedField } from '@/lib/guest-signup'
import { PassSourceGone, type VoucherPassSource } from '@/lib/vouchers'
import i18n from '@/locales/i18n'

/**
 * The pages a shared list's guests open: the list behind `/l/<code>`, and the
 * page behind the link that manages their sign-ups (`/guest-signup#<token>`).
 *
 * Every call goes through the *anonymous* client. Whoever opens these pages has
 * no account, and if one is signed in on the device, its bearer has no business
 * riding along on a stranger's sign-up.
 *
 * Nothing here is written to browser storage. The token that continues a
 * sign-up chain, undoes it or opens the manage page lives only in this store,
 * and `reset()` (the "next person" button on a shared device) and `clear()`
 * (leaving the page) drop it with everything the guest typed.
 *
 * The manage page is also a guest's wallet: the codes they show at a stand
 * come through the same token (`passSource`). Confirming the address from a
 * mail link ("Ja, das bin ich", `confirm`) may hand back another token, the
 * one of the account the sign-ups now belong to, and every later call uses it.
 */

/** Where a page's data stands: `missing` is a link that does not (or no longer) work. */
export type LoadState = 'idle' | 'loading' | 'ready' | 'missing' | 'failed'

/** The manage page, plus the two ends a guest can bring it to. */
export type ManageState = LoadState | 'erased' | 'rejected'

/** What the form needs to send besides the fields: the shift and what it showed. */
export interface SignupInput {
  shiftId: string
  /** The list's `show_names` as the form showed it; the server stores it as consent. */
  showNames: PublicSharedList['show_names']
  /** Omitted from the request when empty, so it looks as it did without Turnstile. */
  turnstileToken: string | null
}

/** Why a sign-up was refused, in words, and the field it concerns if it is one. */
export interface SignupFailure {
  message: string
  field?: GuestField
}

export type SignupOutcome =
  { ok: true; result: PublicSignupResult } | ({ ok: false } & SignupFailure)

/** The sign-up chain, from its first sign-up: who it is and how they get back. */
interface Chain {
  token: string
  /** The address the first sign-up's confirmation went to, if one went. */
  mailedTo: string | null
  /** The first sign-up got no mail, so the page shows the manage link instead. */
  showsLink: boolean
}

/** Refusals after which the list on screen is out of date. */
const STALE_LIST = new Set([
  'booking.slot_full',
  'shared_list.shift_not_offered',
  'shared_list.shift_started',
  'shared_list.paused',
  'shared_list.closed',
  'shared_list.not_found',
  'shared_list.disabled',
])

const emptyFields = (): GuestFields => ({ name: '', email: '', phone: '', remind: true })

const t = (key: string, params: Record<string, unknown> = {}, plural?: number) =>
  plural === undefined ? i18n.global.t(key, params) : i18n.global.t(key, params, plural)

/** The language the guest's mails are written in: whatever the page is in now. */
function currentLanguage(): 'en' | 'de' {
  return i18n.global.locale.value === 'de' ? 'de' : 'en'
}

/** A list that took a sign-up: that shift as the server now counts it. */
function withShift(list: PublicSharedList, shift: PublicShift): PublicSharedList {
  return {
    ...list,
    days: list.days.map((day) => ({
      ...day,
      shifts: day.shifts.map((s) => (s.id === shift.id ? shift : s)),
    })),
  }
}

export const useGuestSignupStore = defineStore('guestSignup', () => {
  // ── The public list ────────────────────────────────────────────────────────

  const code = ref<string | null>(null)
  const list = ref<PublicSharedList | null>(null)
  const listState = ref<LoadState>('idle')
  const fields = reactive<GuestFields>(emptyFields())
  /** The sign-up the done step shows. */
  const last = ref<PublicSignupResult | null>(null)
  const chain = ref<Chain | null>(null)

  /** The manage token, while the done step should show it as a link to keep. */
  const linkToKeep = computed(() => (chain.value?.showsLink ? chain.value.token : null))
  const mailedTo = computed(() => chain.value?.mailedTo ?? null)

  /**
   * Fetch the list behind `listCode`. A different code starts afresh: nothing a
   * guest typed on one list carries over to another. `silent` keeps the page on
   * screen while it refreshes, and keeps it if the refresh fails for any reason
   * other than the list being gone.
   */
  async function load(listCode: string, { silent = false } = {}): Promise<void> {
    if (code.value !== listCode) {
      clearSignup()
      list.value = null
      code.value = listCode
    }
    if (!silent) listState.value = 'loading'
    try {
      const response = await client.get<{ data: PublicSharedList }, unknown, true>({
        url: `/public/shared-lists/${encodeURIComponent(listCode)}`,
        throwOnError: true,
      })
      if (code.value !== listCode) return
      list.value = response.data
      listState.value = 'ready'
    } catch (error) {
      if (code.value !== listCode) return
      if (normalizeApiError(error).status === 404) {
        list.value = null
        listState.value = 'missing'
      } else if (!silent || !list.value) {
        listState.value = 'failed'
      }
    }
  }

  function refresh(): Promise<void> {
    return code.value ? load(code.value, { silent: true }) : Promise.resolve()
  }

  /** What to tell the guest about a refused sign-up, and which field it concerns. */
  function failure(problem: NormalizedApiError): SignupFailure {
    switch (problem.code) {
      case 'booking.slot_full':
        return { message: t('guestSignup.form.errors.slotFull') }
      case 'shared_list.max_per_person': {
        const max = list.value?.max_per_person
        return max
          ? { message: t('guestSignup.form.errors.maxPerPerson', { count: max }, max) }
          : { message: problem.message }
      }
      case 'shared_list.email_required':
        return { field: 'email', message: t('guestSignup.validation.emailRequired') }
      case 'shared_list.phone_required':
        return { field: 'phone', message: t('guestSignup.validation.phoneRequired') }
    }
    const rejected = problem.status === 422 ? rejectedField(problem.errors) : null
    if (rejected) return { field: rejected.field, message: t(rejected.key) }
    return { message: problem.message }
  }

  async function signUp(input: SignupInput): Promise<SignupOutcome> {
    const current = list.value
    if (!code.value || !current) return { ok: false, message: t('common.errors.api.default') }
    const email = current.ask_email === 'off' ? '' : fields.email.trim()
    const phone = current.ask_phone === 'off' ? '' : fields.phone.trim()
    const body: PublicSignupRequest = {
      shift_id: input.shiftId,
      name: fields.name.trim(),
      email: email || null,
      phone: phone || null,
      remind: Boolean(email) && fields.remind,
      language: currentLanguage(),
      show_names: input.showNames,
      ...(chain.value ? { guest_token: chain.value.token } : {}),
      ...(input.turnstileToken ? { turnstile_token: input.turnstileToken } : {}),
    }
    try {
      const response = await client.post<{ data: PublicSignupResult }, unknown, true>({
        url: `/public/shared-lists/${encodeURIComponent(code.value)}/signups`,
        body,
        throwOnError: true,
      })
      const result = response.data
      // An answer with another token than the one sent started a new chain:
      // on the first sign-up, or because the chain sent was confirmed from
      // its mail meanwhile, which retired its token. Later sign-ups go on
      // with the new one.
      if (chain.value?.token !== result.guest_token) {
        chain.value = {
          token: result.guest_token,
          mailedTo: result.mail_queued ? (result.email ?? null) : null,
          showsLink: result.show_manage_link,
        }
      }
      last.value = result
      // The answer carries the shift as it is now, so the list needs no refetch
      // (which would count as another view of the page).
      if (list.value) list.value = withShift(list.value, result.shift)
      return { ok: true, result }
    } catch (error) {
      const problem = normalizeApiError(error)
      // A chain that no longer resolves (erased in the meantime) cannot be
      // continued; the next attempt starts a new one.
      if (problem.code === 'shared_list.guest_token_invalid') chain.value = null
      if (problem.code && STALE_LIST.has(problem.code)) void refresh()
      return { ok: false, ...failure(problem) }
    }
  }

  /**
   * Take back the sign-up just made ("Eintragung zurücknehmen"), with the
   * token that answered it. The fields and the chain stay, since whoever
   * undoes a sign-up usually meant another shift.
   */
  async function undo(): Promise<boolean> {
    if (!last.value) return false
    try {
      await client.post({
        url: '/public/guest-signups/cancel',
        body: { token: last.value.guest_token, booking_id: last.value.booking_id },
        throwOnError: true,
      })
      last.value = null
      void refresh()
      return true
    } catch (error) {
      toastApiError(error)
      return false
    }
  }

  function clearSignup(): void {
    Object.assign(fields, emptyFields())
    last.value = null
    chain.value = null
  }

  /**
   * "Fertig – nächste Person", and the idle timeout on the done step: forget
   * the guest entirely, so a tablet at the stand hands the next person neither
   * their address nor their undo button, and show the list as it is now.
   */
  function reset(): void {
    clearSignup()
    void refresh()
  }

  // ── The manage page ────────────────────────────────────────────────────────

  const manageView = ref<GuestSignupManage | null>(null)
  const manageState = ref<ManageState>('idle')
  /** Read from the URL fragment once; never put back into the address bar. */
  let manageToken: string | null = null

  async function manageCall<T>(url: string, body: Record<string, unknown> = {}): Promise<T> {
    const response = await client.post<{ data: T }, unknown, true>({
      url: `/public/guest-signups/${url}`,
      body: { token: manageToken, ...body },
      throwOnError: true,
    })
    return response.data
  }

  /** Every token failure is the same 404, so the page shows one "link does not work". */
  function manageFailed(error: unknown): void {
    const problem = normalizeApiError(error)
    if (problem.code === 'guest_signup.not_found') {
      manageView.value = null
      manageState.value = 'missing'
    } else {
      toastApiError(error)
    }
  }

  async function manage(token: string): Promise<void> {
    manageToken = token || null
    manageView.value = null
    if (!manageToken) {
      manageState.value = 'missing'
      return
    }
    manageState.value = 'loading'
    try {
      manageView.value = await manageCall<GuestSignupManage>('manage')
      manageState.value = 'ready'
    } catch (error) {
      manageState.value = normalizeApiError(error).status === 404 ? 'missing' : 'failed'
    }
  }

  /** The two actions that answer with the page as it is now. */
  async function update(url: string, body: Record<string, unknown>): Promise<boolean> {
    try {
      manageView.value = await manageCall<GuestSignupManage>(url, body)
      return true
    } catch (error) {
      manageFailed(error)
      return false
    }
  }

  const cancel = (bookingId: string) => update('cancel', { booking_id: bookingId })
  const setReminders = (enabled: boolean) => update('reminders', { enabled })

  /**
   * The page as it is now, e.g. once a code was redeemed at a stand. Quietly:
   * what is on screen stays if the call fails for any other reason than the
   * link no longer working.
   */
  async function reloadManage(): Promise<void> {
    if (!manageToken) return
    try {
      manageView.value = await manageCall<GuestSignupManage>('manage')
    } catch (error) {
      if (normalizeApiError(error).code === 'guest_signup.not_found') manageFailed(error)
    }
  }

  /**
   * "Ja, das bin ich": confirm the address from the link in its mail. The
   * answer carries the token of the account the sign-ups now belong to (the
   * same one when this was the address's first confirmation), and the page
   * goes on with that one.
   */
  async function confirm(): Promise<boolean> {
    try {
      const result = await manageCall<GuestConfirmResult>('confirm')
      manageToken = result.token
      manageView.value = result.manage
      return true
    } catch (error) {
      manageFailed(error)
      return false
    }
  }

  /**
   * Where a guest's code screen gets its codes in `eventId`: through the link
   * that opened the page, whichever token it holds by the time it asks. A link
   * that stopped working is final (`PassSourceGone`); a code that was replaced
   * or is gone (`voucher.pass_not_found`) is passed on as it came, and the
   * screen shows a new code.
   */
  function passSource(eventId: string): VoucherPassSource {
    async function call<T>(url: string, body: Record<string, unknown> = {}): Promise<T> {
      if (!manageToken) throw new PassSourceGone()
      try {
        return await manageCall<T>(url, { event_id: eventId, ...body })
      } catch (error) {
        if (normalizeApiError(error).code === 'guest_signup.not_found') throw new PassSourceGone()
        throw error
      }
    }
    return {
      issue: () => call<VoucherPassRead>('vouchers/pass'),
      status: (passId) => call<VoucherPassStatus>('vouchers/pass-status', { pass_id: passId }),
      // Read when shown, so it follows the page's language.
      get goneMessage() {
        return t('guestSignup.manage.vouchers.linkGone')
      },
    }
  }

  /** The two actions after which the token stops working, ending on their own page. */
  async function finish(url: 'erase' | 'not-me', state: 'erased' | 'rejected'): Promise<boolean> {
    try {
      await manageCall<unknown>(url)
      manageToken = null
      manageView.value = null
      manageState.value = state
      return true
    } catch (error) {
      manageFailed(error)
      // "Das war ich nicht" on sign-ups confirmed meanwhile, in another tab:
      // the page shows them as confirmed now, without the card that offered it.
      if (normalizeApiError(error).code === 'guest_signup.reject_confirmed') await reloadManage()
      return false
    }
  }

  const erase = () => finish('erase', 'erased')
  /** "Das war ich nicht": only offered on the link from a mail (`can_reject`). */
  const notMe = () => finish('not-me', 'rejected')

  /** Leaving a guest page: nothing of the guest stays in memory. */
  function clear(): void {
    clearSignup()
    code.value = null
    list.value = null
    listState.value = 'idle'
    manageToken = null
    manageView.value = null
    manageState.value = 'idle'
  }

  return {
    list,
    listState,
    fields,
    last,
    linkToKeep,
    mailedTo,
    load,
    signUp,
    undo,
    reset,
    manageView,
    manageState,
    manage,
    cancel,
    setReminders,
    reloadManage,
    confirm,
    passSource,
    erase,
    notMe,
    clear,
  }
})
