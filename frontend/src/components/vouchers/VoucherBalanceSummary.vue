<script setup lang="ts">
import { computed } from 'vue'

import { CalendarCheck, Clock, Scale, Ticket } from '@lucide/vue'
import { useI18n } from 'vue-i18n'

import type { VoucherBalance } from '@/client/types.gen'
import { signedVoucherAmount } from '@/lib/vouchers'

/**
 * One person's vouchers as one block, the same on "My vouchers", the bookings
 * page and an organiser's look at someone: what they can use now, large, what
 * their booked shifts will still bring, and three tiles saying where the
 * number comes from (earned, used, corrections).
 *
 * The tiles' icons are a phone's: there the labels sit in narrow tiles and the
 * icon finds the one you look for; wider, the words are enough.
 */
const props = defineProps<{
  summary: VoucherBalance
  /** The smaller number of a dialog. */
  compact?: boolean
  /** Someone else's balance (the organisers' view): says so when nothing more is booked. */
  other?: boolean
}>()

const { t } = useI18n()

const tiles = computed(() => [
  {
    key: 'earned',
    icon: CalendarCheck,
    label: t('vouchers.earned'),
    value: String(props.summary.earned),
    testid: 'voucher-earned',
  },
  {
    key: 'used',
    icon: Ticket,
    label: t('vouchers.used'),
    value: String(props.summary.redeemed),
    testid: 'voucher-used',
  },
  {
    key: 'adjusted',
    icon: Scale,
    label: t('vouchers.adjusted'),
    value: signedVoucherAmount(props.summary.adjusted),
    testid: 'voucher-adjusted',
  },
])
</script>

<template>
  <div data-testid="voucher-balance">
    <p class="flex items-baseline gap-2">
      <span
        class="leading-none font-bold tabular-nums"
        :class="compact ? 'text-[2.75rem]' : 'text-[3.25rem]'"
        data-testid="voucher-available"
      >
        {{ summary.available }}
      </span>
      <span class="text-[15px] text-muted-foreground">{{ t('vouchers.availableShort') }}</span>
    </p>

    <p
      v-if="summary.upcoming > 0"
      class="mt-1.5 flex items-center gap-1.5 text-sm text-foreground/80"
      data-testid="voucher-upcoming"
    >
      <Clock class="size-[15px] shrink-0" aria-hidden="true" />
      {{ t('vouchers.upcomingFromShifts', { n: summary.upcoming }, summary.upcoming) }}
    </p>
    <p v-else-if="other" class="mt-1.5 text-sm text-foreground/80" data-testid="voucher-upcoming">
      {{ t('vouchers.noMoreShifts') }}
    </p>

    <dl class="mt-3.5 grid grid-cols-3 gap-2">
      <div v-for="tile in tiles" :key="tile.key" class="min-w-0 rounded-xl bg-muted/60 px-3 py-2.5">
        <dt class="flex min-w-0 items-center gap-1.5 text-xs text-muted-foreground">
          <component :is="tile.icon" class="size-[13px] shrink-0 sm:hidden" aria-hidden="true" />
          <span class="truncate">{{ tile.label }}</span>
        </dt>
        <dd class="mt-0.5 text-xl font-bold tabular-nums" :data-testid="tile.testid">
          {{ tile.value }}
        </dd>
      </div>
    </dl>
  </div>
</template>
