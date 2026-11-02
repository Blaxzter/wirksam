<script setup lang="ts">
/**
 * The volunteer's vouchers, beside the next shift.
 *
 * Purely presentational: the account comes from `useMyVoucherAccount` in the
 * page, which also decides whether this is mounted at all (the same rule as
 * `MyVouchersCard`: not in an event without vouchers). On desktop it is the
 * side card "Your vouchers" with what was earned and used; below `lg` it
 * shrinks to a tile next to the "Signed up" tile, with only the number and
 * the code button, because those are what you need at the stand.
 *
 * The code button stays when nothing is available, disabled, as on the
 * bookings page; the big "0 available" already says why. After the event it
 * goes, and the history link remains.
 */
import { computed } from 'vue'

import { QrCode, Ticket } from '@lucide/vue'
import { useI18n } from 'vue-i18n'

import { Button } from '@/components/ui/button'

import type { VoucherAccount } from '@/client/types.gen'
import { upcomingToday } from '@/lib/dashboard'

const props = defineProps<{
  account: VoucherAccount
  now: Date
  eventId: string
  expired: boolean
  canShowCode: boolean
}>()

const emit = defineEmits<{ showCode: [] }>()

const { t } = useI18n()

const summary = computed(() => props.account.summary)

/**
 * `summary.upcoming` counts every booked voucher shift that has not ended, on
 * any day. "+2 more after your shift today" is only true when all of them are
 * today, so the card says that only then and the plain line otherwise.
 */
const upcomingLine = computed(() => {
  const n = summary.value.upcoming
  const today = upcomingToday(props.account.shifts, props.now)
  if (today.vouchers > 0 && today.vouchers === n) {
    return today.shifts === 1
      ? t('dashboard.home.vouchers.upcomingTodayOne', { n }, n)
      : t('dashboard.home.vouchers.upcomingTodayMany', { n }, n)
  }
  return t('vouchers.upcoming', { n })
})

/** The phone tile has room for one line: "available, +2 to come". */
const availableShort = computed(() => {
  const available = t('dashboard.home.vouchers.available')
  const n = summary.value.upcoming
  if (n <= 0) return available
  return `${available}, ${t('dashboard.home.vouchers.upcomingShort', { n }, n)}`
})

const adjustedText = computed(() => {
  const a = summary.value.adjusted
  return a > 0 ? `+${a}` : String(a)
})
</script>

<template>
  <section
    data-testid="my-vouchers-card"
    aria-labelledby="dashboard-vouchers-title"
    class="flex min-w-0 flex-col rounded-2xl border bg-card p-4 text-card-foreground lg:gap-1.5 lg:rounded-[22px] lg:p-6"
  >
    <div class="flex items-center justify-between gap-2">
      <h2
        id="dashboard-vouchers-title"
        class="flex min-w-0 items-center gap-1.5 text-[13px] font-semibold text-muted-foreground lg:gap-2 lg:text-base lg:font-bold lg:text-card-foreground"
      >
        <Ticket class="size-4 shrink-0 lg:size-[18px]" aria-hidden="true" />
        <span class="truncate lg:hidden">{{ t('vouchers.title') }}</span>
        <span class="hidden truncate lg:inline">{{ t('dashboard.home.vouchers.title') }}</span>
      </h2>
      <RouterLink
        data-testid="btn-my-vouchers-details"
        :to="{ name: 'my-vouchers', params: { eventId } }"
        class="-my-2 shrink-0 py-2 text-[13px] font-semibold text-primary hover:underline lg:text-sm"
      >
        {{ t('dashboard.home.vouchers.history') }}
      </RouterLink>
    </div>

    <p class="mt-1.5 flex flex-col lg:mt-3.5 lg:flex-row lg:items-baseline lg:gap-2">
      <span
        data-testid="dashboard-voucher-available"
        class="text-[2rem] leading-none font-bold tabular-nums lg:text-[3.25rem]"
      >
        {{ summary.available }}
      </span>
      <span class="text-[13px] text-muted-foreground lg:text-[15px]">
        <span data-testid="dashboard-voucher-available-short" class="lg:hidden">
          {{ availableShort }}
        </span>
        <span class="hidden lg:inline">{{ t('dashboard.home.vouchers.available') }}</span>
      </span>
    </p>
    <p
      v-if="summary.upcoming > 0"
      data-testid="dashboard-voucher-upcoming"
      class="hidden text-sm text-muted-foreground lg:block"
    >
      {{ upcomingLine }}
    </p>

    <dl
      class="mt-3.5 hidden gap-2 lg:grid"
      :class="summary.adjusted !== 0 ? 'grid-cols-3' : 'grid-cols-2'"
    >
      <div class="rounded-xl bg-muted/60 px-3 py-2.5">
        <dt class="text-xs text-muted-foreground">{{ t('vouchers.earned') }}</dt>
        <dd class="mt-0.5 text-lg font-bold tabular-nums">{{ summary.earned }}</dd>
      </div>
      <div class="rounded-xl bg-muted/60 px-3 py-2.5">
        <dt class="text-xs text-muted-foreground">{{ t('vouchers.used') }}</dt>
        <dd class="mt-0.5 text-lg font-bold tabular-nums">{{ summary.redeemed }}</dd>
      </div>
      <div
        v-if="summary.adjusted !== 0"
        data-testid="dashboard-voucher-adjusted"
        class="rounded-xl bg-muted/60 px-3 py-2.5"
      >
        <dt class="text-xs text-muted-foreground">{{ t('vouchers.adjusted') }}</dt>
        <dd class="mt-0.5 text-lg font-bold tabular-nums">{{ adjustedText }}</dd>
      </div>
    </dl>

    <div class="mt-auto pt-3 lg:pt-4">
      <Button
        v-if="!expired"
        data-testid="btn-show-voucher-code"
        :disabled="!canShowCode"
        class="h-11 w-full rounded-lg text-sm font-semibold lg:h-[46px] lg:rounded-xl lg:font-bold"
        @click="emit('showCode')"
      >
        <QrCode aria-hidden="true" />
        {{ t('vouchers.showCode') }}
      </Button>
    </div>
  </section>
</template>
