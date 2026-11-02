<script setup lang="ts">
/**
 * "Signed up: 8 h in 3 shifts", the phone's answer to "how much have I
 * promised", next to the voucher tile under the next shift.
 *
 * Phones only: on desktop the plan beside it says the same in its subtitle.
 * The button scrolls down to the plan rather than linking to `#dashboard-plan`,
 * because the page's router-view key is the full path, and a hash navigation
 * would remount the whole dashboard.
 *
 * Shifts without times count as no minutes, so when every booked shift is
 * untimed the tile counts shifts instead of claiming "0 h".
 */
import { CalendarCheck } from '@lucide/vue'
import { useI18n } from 'vue-i18n'

import { Button } from '@/components/ui/button'

import { hoursValue } from '@/lib/dashboard'

defineProps<{
  /** feed.my_minutes */
  minutes: number
  /** feed.my_shift_count */
  shiftCount: number
}>()

const emit = defineEmits<{ toPlan: [] }>()

const { t, locale } = useI18n()
</script>

<template>
  <section
    data-testid="dashboard-committed"
    aria-labelledby="dashboard-committed-title"
    class="flex min-w-0 flex-col rounded-2xl border bg-card p-4 text-card-foreground lg:hidden"
  >
    <h2
      id="dashboard-committed-title"
      class="flex items-center gap-1.5 text-[13px] font-semibold text-muted-foreground"
    >
      <CalendarCheck class="size-4 shrink-0" aria-hidden="true" />
      {{ t('dashboard.home.committed.title') }}
    </h2>
    <template v-if="minutes > 0">
      <p class="mt-1.5 text-[2rem] leading-none font-bold tabular-nums">
        {{ t('dashboard.home.committed.hours', { hours: hoursValue(minutes, locale) }) }}
      </p>
      <p class="text-[13px] text-muted-foreground">
        {{ t('dashboard.home.committed.inShifts', { count: shiftCount }, shiftCount) }}
      </p>
    </template>
    <p v-else class="mt-1.5 text-[2rem] leading-none font-bold tabular-nums">
      {{ t('dashboard.home.committed.shifts', { count: shiftCount }, shiftCount) }}
    </p>
    <div class="mt-auto pt-3">
      <Button
        variant="outline"
        data-testid="btn-to-plan"
        class="h-11 w-full rounded-lg bg-background text-sm font-semibold dark:bg-background"
        @click="emit('toPlan')"
      >
        {{ t('dashboard.home.committed.toPlan') }}
      </Button>
    </div>
  </section>
</template>
