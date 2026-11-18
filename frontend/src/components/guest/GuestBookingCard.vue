<script setup lang="ts">
/**
 * One shift on a guest's manage page: what, when and where, whether it still
 * stands, and the button to take their name off while that is allowed.
 *
 * Each sign-up keeps its own person. Once an address was confirmed, one page
 * may hold the sign-ups of a family that shares it, so a shift signed up for
 * under another name than the page's says whose it is.
 */
import { computed } from 'vue'

import { LoaderIcon, Ticket } from '@lucide/vue'
import { useI18n } from 'vue-i18n'

import { useFormatters } from '@/composables/useFormatters'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'

import type { GuestSignupBooking } from '@/client/types.gen'
import { LONG_DAY, dayAndTime } from '@/lib/guest-signup'

const props = defineProps<{
  booking: GuestSignupBooking
  /** The event of the list the guest signed up on. */
  eventName: string
  /** The name the page is under (the first confirmed sign-up's, on an account). */
  holderName?: string | null
  cancelling: boolean
}>()

const emit = defineEmits<{ cancel: [booking: GuestSignupBooking] }>()

const { t } = useI18n()
const { formatDateLabel, formatTimeRange } = useFormatters()

const when = computed(() =>
  dayAndTime(
    formatDateLabel(props.booking.date, LONG_DAY),
    formatTimeRange(props.booking.start_time, props.booking.end_time),
  ),
)

const cancelled = computed(() => props.booking.status === 'cancelled')
const over = computed(() => !cancelled.value && !props.booking.can_cancel)
/** Signed up under another name than the page's, after a family's sign-ups were pooled. */
const otherName = computed(() =>
  props.booking.name && props.booking.name !== props.holderName ? props.booking.name : null,
)
/** What the shift earns, while the sign-up stands. */
const vouchers = computed(() => (cancelled.value ? 0 : (props.booking.vouchers ?? 0)))

/** A task moved to another event takes its bookings along. */
const movedTo = computed(() =>
  props.booking.event_name && props.booking.event_name !== props.eventName
    ? props.booking.event_name
    : null,
)
</script>

<template>
  <li
    class="space-y-3 rounded-xl border bg-card p-4"
    data-testid="guest-manage-booking"
    :data-booking-id="booking.booking_id"
    :data-status="booking.status"
  >
    <div class="flex items-start justify-between gap-3">
      <div class="min-w-0 space-y-0.5">
        <!-- Focus lands here once the name is taken off and its button has gone. -->
        <h3
          :id="`guest-booking-${booking.booking_id}`"
          tabindex="-1"
          class="font-semibold break-words focus:outline-none"
          :class="cancelled && 'line-through'"
        >
          {{ booking.task_name }}
        </h3>
        <p class="text-sm">{{ when }}</p>
        <p v-if="booking.location" class="text-sm break-words text-muted-foreground">
          {{ booking.location }}
        </p>
        <p v-if="movedTo" class="text-sm text-muted-foreground">
          {{ t('guestSignup.manage.bookings.otherEvent', { event: movedTo }) }}
        </p>
        <p
          v-if="otherName"
          class="text-sm break-words text-muted-foreground"
          data-testid="guest-booking-name"
        >
          {{ t('guestSignup.manage.signedUpAs', { name: otherName }) }}
        </p>
        <!-- Lists show only shifts still to come, so an over one names nobody. -->
        <p
          v-if="!cancelled && !over && booking.show_first_name"
          class="text-sm text-muted-foreground"
          data-testid="guest-booking-first-name"
        >
          {{ t('guestSignup.manage.bookings.firstNamePublic') }}
        </p>
        <Badge
          v-if="vouchers > 0"
          variant="secondary"
          class="mt-1 gap-1"
          data-testid="guest-booking-vouchers"
        >
          <Ticket class="size-3.5" aria-hidden="true" />
          {{ t('guestSignup.list.vouchersBadge', { n: vouchers }, vouchers) }}
        </Badge>
      </div>
      <Badge v-if="cancelled" variant="outline" class="shrink-0">
        {{ t('guestSignup.manage.bookings.statusCancelled') }}
      </Badge>
      <Badge v-else-if="over" variant="secondary" class="shrink-0">
        {{ t('guestSignup.manage.bookings.statusOver') }}
      </Badge>
    </div>
    <!-- aria-disabled, not disabled, while it runs: the confirmation hands focus
         back here, and a disabled button would drop it. -->
    <Button
      v-if="!cancelled && booking.can_cancel"
      variant="outline"
      class="h-11 w-full aria-disabled:opacity-50 sm:w-auto"
      :aria-disabled="cancelling || undefined"
      :aria-describedby="`guest-booking-${booking.booking_id}`"
      :data-testid="`btn-guest-cancel-${booking.booking_id}`"
      @click="!cancelling && emit('cancel', booking)"
    >
      <LoaderIcon v-if="cancelling" class="size-4 animate-spin" aria-hidden="true" />
      {{ t('guestSignup.manage.bookings.cancel') }}
    </Button>
  </li>
</template>
