<script setup lang="ts">
/**
 * A guest's own page, behind the link in their confirmation mail or the one
 * the sign-up page showed them: `/guest-signup#<token>`.
 *
 * The token travels in the fragment, which no server and no referrer ever
 * sees. It is read once, kept in memory, and taken out of the address bar
 * straight away, so it is not left in the history, in a bookmark or on a
 * screen someone else is looking at. Reloading the page therefore asks for the
 * link again, which is the point.
 *
 * From here a guest takes their name off a shift, switches the reminder mail on
 * or off, or deletes their data. "Das war ich nicht" is offered only when the
 * page was opened from a mail (`can_reject`): whoever typed an address holds
 * the sign-up's own link, and must not be able to stop all mail to somebody
 * else.
 *
 * Opened from a mail, the page also offers to confirm the address ("Ja, das
 * bin ich"). Every sign-up confirmed with it for the event then shows here,
 * with one balance of vouchers. The vouchers have a card per event with the
 * code to show at a stand, which comes through the same link.
 */
import { computed, nextTick, onBeforeUnmount, onMounted, ref, useTemplateRef, watch } from 'vue'

import {
  CircleAlertIcon,
  CircleCheckIcon,
  LinkIcon,
  LoaderIcon,
  ShieldOffIcon,
  Trash2Icon,
} from '@lucide/vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { toast } from 'vue-sonner'

import { useGuestSignupStore } from '@/stores/guestSignup'

import { useDialog } from '@/composables/useDialog'
import { useFormatters } from '@/composables/useFormatters'

import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { Switch } from '@/components/ui/switch'

import EventZoneHint from '@/components/events/EventZoneHint.vue'
import GuestBookingCard from '@/components/guest/GuestBookingCard.vue'
import GuestConfirmCard from '@/components/guest/GuestConfirmCard.vue'
import GuestDemoNotice from '@/components/guest/GuestDemoNotice.vue'
import GuestStateMessage from '@/components/guest/GuestStateMessage.vue'
import GuestVouchersCard from '@/components/guest/GuestVouchersCard.vue'

import type { GuestSignupBooking } from '@/client/types.gen'
import { LONG_DAY, retentionVariant } from '@/lib/guest-signup'
import type { VoucherPassSource } from '@/lib/vouchers'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const { formatDateLabel, formatDaySpan } = useFormatters()

/** The day the data goes: "22 December 2026". */
const ERASE_DATE: Intl.DateTimeFormatOptions = { day: 'numeric', month: 'long', year: 'numeric' }
const { confirmDestructive } = useDialog()
const store = useGuestSignupStore()

/** The page that is left once the token stops working: deleted, "not me", or dead. */
const endState = useTemplateRef<InstanceType<typeof GuestStateMessage>>('endState')

/** The token from the fragment; kept for "try again", never written anywhere. */
let token = ''
const cancellingId = ref<string | null>(null)
const savingReminders = ref(false)
const finishing = ref<'erase' | 'notMe' | null>(null)
const confirming = ref(false)
/** "Das war ich nicht" left the address mailable: it has confirmed sign-ups elsewhere. */
const rejectKeptMail = ref(false)

const view = computed(() => store.manageView)

const eventLine = computed(() =>
  view.value
    ? t('guestSignup.manage.eventLine', {
        event: view.value.event.name,
        days: formatDaySpan(view.value.event.start_date, view.value.event.end_date),
      })
    : '',
)

/** The shifts a reminder could still be sent for. */
const upcoming = computed(() =>
  (view.value?.bookings ?? []).filter((b) => b.status === 'confirmed' && b.can_cancel),
)
const remindersOn = computed(() => upcoming.value.some((b) => b.reminder_on))

/** What has not been redeemed yet, over every event: it expires with the data. */
const unredeemed = computed(() =>
  (view.value?.vouchers ?? []).reduce((n, v) => n + v.account.summary.available, 0),
)

/**
 * When the data goes by itself, naming only what is stored: the address and
 * the phone number only where there are any. Unredeemed vouchers go with it.
 */
const retentionLine = computed(() => {
  const v = view.value
  if (!v) return ''
  const days = v.retention_days
  const line = t(
    `guestSignup.manage.retention.${retentionVariant(!!v.email, v.has_phone)}`,
    { date: formatDateLabel(v.erase_on, ERASE_DATE), days },
    days,
  )
  return v.vouchers.length > 0 ? `${line} ${t('guestSignup.manage.retention.vouchers')}` : line
})

/** One source of codes per event, kept so the code screens keep theirs. */
const sources = new Map<string, VoucherPassSource>()
function sourceFor(eventId: string): VoucherPassSource {
  let source = sources.get(eventId)
  if (!source) {
    source = store.passSource(eventId)
    sources.set(eventId, source)
  }
  return source
}

/**
 * After an action that removes the button it was started from, focus goes to
 * `target` rather than to <body>: now, if the confirmation has closed already
 * and handed focus back to that button, or else once it closes
 * (`focusInstead`).
 */
async function settleFocus(target: () => void): Promise<void> {
  await nextTick()
  if (document.activeElement === document.body) target()
}

/** The link died under an action: the page now says so, and focus goes there. */
async function focusIfDead(): Promise<void> {
  if (store.manageState !== 'missing') return
  await nextTick()
  endState.value?.focus()
}

async function cancel(booking: GuestSignupBooking): Promise<void> {
  // The shift's name, which then reads as taken off.
  const focusShift = () => document.getElementById(`guest-booking-${booking.booking_id}`)?.focus()
  const confirmed = await confirmDestructive({
    title: t('guestSignup.manage.bookings.cancelConfirm.title'),
    text: t('guestSignup.manage.bookings.cancelConfirm.text', {
      task: booking.task_name,
      date: formatDateLabel(booking.date, LONG_DAY),
    }),
    confirmText: t('guestSignup.manage.bookings.cancelConfirm.confirm'),
    cancelText: t('common.actions.cancel'),
    focusInstead: focusShift,
  })
  if (!confirmed) return
  cancellingId.value = booking.booking_id
  const done = await store.cancel(booking.booking_id)
  cancellingId.value = null
  if (!done) return
  toast.success(t('guestSignup.manage.bookings.cancelled'))
  await settleFocus(focusShift)
}

async function setReminders(enabled: boolean): Promise<void> {
  if (savingReminders.value) return
  savingReminders.value = true
  await store.setReminders(enabled)
  savingReminders.value = false
}

/**
 * What the confirmation says: the erase names the vouchers that expire, and on
 * a confirmed address that it erases only what this page shows; "not me" says
 * whether mail to the address stops.
 */
function finishText(action: 'erase' | 'notMe'): string {
  const v = view.value
  if (action === 'notMe') {
    return v && !v.reject_suppresses
      ? t('guestSignup.manage.notMe.keepsMail')
      : t('guestSignup.manage.notMe.confirm.text')
  }
  const parts = [t('guestSignup.manage.erase.confirm.text')]
  const lost = unredeemed.value
  if (lost > 0) parts.push(t('guestSignup.manage.erase.vouchersLost', { n: lost }, lost))
  if (v?.confirmed) parts.push(t('guestSignup.manage.erase.scopeAccount'))
  return parts.join(' ')
}

/**
 * Deleting the data or "Das war ich nicht": the page ends on its own message.
 * "Das war ich nicht" on sign-ups confirmed meanwhile in another tab is
 * refused, and the page then shows them as confirmed, without the card whose
 * button was pressed: focus goes to the line that says so.
 */
async function finish(action: 'erase' | 'notMe'): Promise<void> {
  if (finishing.value || confirming.value) return
  const focusEnd = () => {
    if (endState.value) endState.value.focus()
    else document.getElementById('guest-manage-confirmed')?.focus()
  }
  const confirmed = await confirmDestructive({
    title: t(`guestSignup.manage.${action}.confirm.title`),
    text: finishText(action),
    confirmText: t(`guestSignup.manage.${action}.confirm.confirm`),
    cancelText: t('common.actions.cancel'),
    focusInstead: focusEnd,
  })
  if (!confirmed) return
  rejectKeptMail.value = action === 'notMe' && view.value?.reject_suppresses === false
  finishing.value = action
  await (action === 'erase' ? store.erase() : store.notMe())
  finishing.value = null
  await settleFocus(focusEnd)
}

/**
 * "Ja, das bin ich". The card goes once it is done, with the button that was
 * pressed, so focus moves to the line that now says the address is confirmed.
 */
async function confirmAddress(): Promise<void> {
  if (confirming.value || finishing.value) return
  confirming.value = true
  const done = await store.confirm()
  confirming.value = false
  if (!done) {
    await focusIfDead()
    return
  }
  toast.success(t('guestSignup.manage.confirm.done', { event: view.value?.event.name ?? '' }))
  await nextTick()
  document.getElementById('guest-manage-confirmed')?.focus()
}

/** A code screen closed on a link that no longer works: the whole page has stopped working. */
async function linkGone(): Promise<void> {
  await store.reloadManage()
  await focusIfDead()
}

/**
 * Takes the token out of the address bar, then opens it. Through the router,
 * which keeps its own record of the entry and would otherwise write the token
 * into the next page's `history.state.back`.
 */
function openLink(): void {
  token = route.hash.slice(1)
  if (route.hash) void router.replace({ name: 'guest-signup-manage', query: route.query })
  void store.manage(token)
}

onMounted(openLink)

/**
 * Another link opened in this tab changes only the fragment: the browser
 * reloads nothing and the page stays mounted, so it reads the new one here.
 */
watch(
  () => route.hash,
  (hash) => {
    // Leaving for another page with a fragment is no new link.
    if (route.name === 'guest-signup-manage' && hash.length > 1) openLink()
  },
)

onBeforeUnmount(() => store.clear())
</script>

<template>
  <div>
    <div
      v-if="store.manageState === 'idle' || store.manageState === 'loading'"
      class="space-y-4"
      role="status"
      data-testid="guest-manage-loading"
    >
      <span class="sr-only">{{ t('utils.loading') }}</span>
      <Skeleton class="h-16 w-full rounded-xl" />
      <Skeleton class="h-28 w-full rounded-xl" />
      <Skeleton class="h-28 w-full rounded-xl" />
    </div>

    <GuestStateMessage
      v-else-if="store.manageState === 'missing'"
      ref="endState"
      :icon="LinkIcon"
      heading-tag="h1"
      :title="t('guestSignup.manage.notFound.title')"
      :text="t('guestSignup.manage.notFound.text')"
      data-testid="guest-manage-not-found"
    />

    <GuestStateMessage
      v-else-if="store.manageState === 'erased'"
      ref="endState"
      :icon="CircleCheckIcon"
      heading-tag="h1"
      :title="t('guestSignup.manage.erase.done.title')"
      :text="t('guestSignup.manage.erase.done.text')"
      data-testid="guest-manage-erased"
    />

    <GuestStateMessage
      v-else-if="store.manageState === 'rejected'"
      ref="endState"
      :icon="CircleCheckIcon"
      heading-tag="h1"
      :title="t('guestSignup.manage.notMe.done.title')"
      :text="
        rejectKeptMail
          ? t('guestSignup.manage.notMe.done.textKeepsMail')
          : t('guestSignup.manage.notMe.done.text')
      "
      data-testid="guest-manage-rejected"
    />

    <GuestStateMessage
      v-else-if="store.manageState === 'failed' || !view"
      :icon="CircleAlertIcon"
      heading-tag="h1"
      :title="t('guestSignup.manage.error.title')"
      data-testid="guest-manage-error"
    >
      <Button variant="outline" class="h-11" @click="store.manage(token)">
        {{ t('guestSignup.manage.error.retry') }}
      </Button>
    </GuestStateMessage>

    <div v-else class="space-y-6" data-testid="guest-manage-page">
      <header class="space-y-1">
        <p class="text-sm font-semibold text-muted-foreground">{{ eventLine }}</p>
        <h1 class="text-2xl font-bold tracking-tight" data-testid="page-heading">
          {{ t('guestSignup.manage.title') }}
        </h1>
        <p v-if="view.name" class="text-sm break-words" data-testid="guest-manage-who">
          {{ t('guestSignup.manage.signedUpAs', { name: view.name }) }}
          <span v-if="view.email" class="text-muted-foreground"> · {{ view.email }}</span>
        </p>
        <!-- Focus lands here once "Ja, das bin ich" is done and its card has gone. -->
        <p
          v-if="view.confirmed"
          id="guest-manage-confirmed"
          tabindex="-1"
          class="flex items-center gap-1.5 text-sm font-medium text-primary focus:outline-none"
          data-testid="guest-manage-confirmed"
        >
          <CircleCheckIcon class="size-4 shrink-0" aria-hidden="true" />
          {{ t('guestSignup.manage.confirm.confirmed') }}
        </p>
      </header>

      <GuestDemoNotice v-if="view.event.is_sandbox" />

      <GuestConfirmCard
        :view="view"
        :confirming="confirming"
        :busy="confirming || finishing !== null"
        @confirm="confirmAddress"
        @not-me="finish('notMe')"
      />

      <EventZoneHint :zone="view.event.timezone" />

      <GuestVouchersCard
        v-for="voucher in view.vouchers"
        :key="voucher.event_id"
        :voucher="voucher"
        :source="sourceFor(voucher.event_id)"
        :named="view.vouchers.length > 1"
        @redeemed="store.reloadManage()"
        @gone="linkGone"
      />

      <section class="space-y-3" aria-labelledby="guest-manage-shifts">
        <h2 id="guest-manage-shifts" class="text-lg font-semibold">
          {{ t('guestSignup.manage.bookings.title') }}
        </h2>
        <ul v-if="view.bookings.length > 0" class="space-y-3">
          <GuestBookingCard
            v-for="booking in view.bookings"
            :key="booking.booking_id"
            :booking="booking"
            :event-name="view.event.name"
            :holder-name="view.name"
            :cancelling="cancellingId === booking.booking_id"
            @cancel="cancel"
          />
        </ul>
        <p v-else class="text-sm text-muted-foreground" data-testid="guest-manage-empty">
          {{ t('guestSignup.manage.bookings.empty') }}
        </p>
      </section>

      <section
        v-if="view.can_set_reminders && upcoming.length > 0"
        class="flex items-start justify-between gap-4 rounded-xl border p-4"
      >
        <div class="space-y-1">
          <Label for="guest-reminders" class="font-semibold">
            {{ t('guestSignup.manage.reminders.label') }}
          </Label>
          <p id="guest-reminders-hint" class="text-sm text-muted-foreground">
            {{ t('guestSignup.manage.reminders.hint') }}
          </p>
        </div>
        <Switch
          id="guest-reminders"
          :model-value="remindersOn"
          :aria-disabled="savingReminders || undefined"
          aria-describedby="guest-reminders-hint"
          class="mt-0.5 aria-disabled:opacity-50"
          data-testid="guest-reminders-switch"
          @update:model-value="(value: boolean) => setReminders(value)"
        />
      </section>

      <section class="space-y-3 rounded-xl border p-4" aria-labelledby="guest-manage-erase">
        <h2 id="guest-manage-erase" class="font-semibold">
          {{ t('guestSignup.manage.erase.title') }}
        </h2>
        <p class="text-sm text-muted-foreground" data-testid="guest-manage-retention">
          {{ retentionLine }}
        </p>
        <p class="text-sm text-muted-foreground">{{ t('guestSignup.manage.erase.text') }}</p>
        <Button
          variant="destructive"
          class="h-11 w-full aria-disabled:opacity-50 sm:w-auto"
          :aria-disabled="finishing !== null || undefined"
          data-testid="btn-guest-erase"
          @click="finish('erase')"
        >
          <LoaderIcon v-if="finishing === 'erase'" class="size-4 animate-spin" aria-hidden="true" />
          <Trash2Icon v-else class="size-4" aria-hidden="true" />
          {{ t('guestSignup.manage.erase.button') }}
        </Button>
      </section>

      <!-- With an address to confirm, "Das war ich nicht" sits on the confirm card. -->
      <section
        v-if="view.can_reject && !view.can_confirm"
        class="space-y-3 rounded-xl border p-4"
        aria-labelledby="guest-manage-not-me"
        data-testid="guest-manage-not-me"
      >
        <h2 id="guest-manage-not-me" class="font-semibold">
          {{ t('guestSignup.manage.notMe.title') }}
        </h2>
        <p class="text-sm text-muted-foreground">
          {{
            view.reject_suppresses
              ? t('guestSignup.manage.notMe.text')
              : t('guestSignup.manage.notMe.textKeepsMail')
          }}
        </p>
        <Button
          variant="outline"
          class="h-11 w-full aria-disabled:opacity-50 sm:w-auto"
          :aria-disabled="finishing !== null || undefined"
          data-testid="btn-guest-not-me"
          @click="finish('notMe')"
        >
          <LoaderIcon v-if="finishing === 'notMe'" class="size-4 animate-spin" aria-hidden="true" />
          <ShieldOffIcon v-else class="size-4" aria-hidden="true" />
          {{ t('guestSignup.manage.notMe.button') }}
        </Button>
      </section>
    </div>
  </div>
</template>
