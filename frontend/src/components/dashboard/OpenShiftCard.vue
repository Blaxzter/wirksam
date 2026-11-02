<script setup lang="ts">
/**
 * One shift that still needs people, as a card you can sign up from.
 *
 * The badge in the corner answers "how urgent": "Nobody yet" in warning
 * colours, otherwise how many places are left. The bar shows how full the
 * shift is, but it is decoration; "1 of 3 filled" underneath is what a screen
 * reader hears and what a colour-blind eye reads.
 *
 * "Sign up" opens the shift's details rather than booking on the spot: that
 * is where you see who else is on it and where it is, and where a team or a
 * voucher rule can say no before you have promised anything.
 */
import { computed } from 'vue'

import { MapPin } from '@lucide/vue'
import { useI18n } from 'vue-i18n'

import { useFormatters } from '@/composables/useFormatters'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'

import type { DashboardOpenShift } from '@/client'
import { capitalizeFirst, dayOffset, fillPercent, shiftHeadline } from '@/lib/dashboard'

const props = defineProps<{
  shift: DashboardOpenShift
  now: Date
  /** Only with no event in view, where the cards come from several events. */
  showEventName: boolean
}>()

const emit = defineEmits<{ select: [shiftId: string] }>()

const { t, locale } = useI18n()
const { formatTimeRange, formatRelativeDay, formatDateLabel } = useFormatters()

const offset = computed(() => dayOffset(props.shift.date, props.now))
const cardDay = computed(() =>
  formatDateLabel(props.shift.date, { weekday: 'short', day: 'numeric', month: 'short' }),
)
/** "Today" / "Tomorrow" while there is such a word, then the date. */
const dayLabel = computed(() =>
  offset.value === 0 || offset.value === 1
    ? capitalizeFirst(formatRelativeDay(props.shift.date), locale.value)
    : cardDay.value,
)
const times = computed(() => formatTimeRange(props.shift.start_time, props.shift.end_time))
const heading = computed(() => shiftHeadline(props.shift.title, props.shift.task_name))
const fill = computed(() => fillPercent(props.shift.taken, props.shift.capacity))

/** Names the shift, and starts with the visible word "Sign up" (WCAG 2.5.3). */
const signUpLabel = computed(() => {
  const day = Math.abs(offset.value) <= 1 ? formatRelativeDay(props.shift.date) : cardDay.value
  return times.value
    ? t('dashboard.home.open.signUpLabel', {
        title: heading.value.headline,
        day,
        time: times.value,
      })
    : t('dashboard.home.open.signUpLabelNoTime', { title: heading.value.headline, day })
})
</script>

<template>
  <li data-testid="open-shift-card" :data-shift-id="shift.shift_id" class="min-w-0">
    <Card
      class="h-full gap-2 rounded-2xl px-4 py-3.5 shadow-none @4xl:gap-2.5 @4xl:rounded-[18px] @4xl:p-[18px]"
    >
      <div class="flex items-center justify-between gap-2">
        <span class="min-w-0 truncate text-[13px] text-muted-foreground tabular-nums">
          {{ dayLabel }}<template v-if="times"> · {{ times }}</template>
        </span>
        <Badge
          data-testid="open-shift-badge"
          :variant="shift.taken === 0 ? 'warning' : 'secondary'"
          class="rounded-full font-bold"
        >
          {{
            shift.taken === 0
              ? t('dashboard.home.open.nobodyYet')
              : t('dashboard.home.open.placesLeft', { count: shift.places_left }, shift.places_left)
          }}
        </Badge>
      </div>

      <div class="min-w-0">
        <p class="truncate text-base font-semibold @4xl:text-[17px]">{{ heading.headline }}</p>
        <p v-if="heading.taskLine" class="truncate text-[13px] text-muted-foreground">
          {{ heading.taskLine }}
        </p>
        <p
          v-if="shift.location"
          class="mt-0.5 flex min-w-0 items-center gap-1 text-[13px] text-muted-foreground"
        >
          <MapPin class="size-3.5 shrink-0" aria-hidden="true" />
          <span class="truncate">{{ shift.location }}</span>
        </p>
        <p
          v-if="showEventName && shift.event_name"
          data-testid="open-shift-event"
          class="truncate text-xs text-muted-foreground"
        >
          {{ shift.event_name }}
        </p>
      </div>

      <div class="flex items-center gap-3 @4xl:mt-auto">
        <div class="min-w-0 flex-1">
          <div aria-hidden="true" class="h-1.5 overflow-hidden rounded-full bg-muted">
            <div class="h-full rounded-full bg-staff-partial" :style="{ width: `${fill}%` }" />
          </div>
          <p class="mt-1 text-xs text-muted-foreground">
            {{ t('dashboard.home.open.filled', { taken: shift.taken, capacity: shift.capacity }) }}
          </p>
        </div>
        <Button
          variant="outline"
          data-testid="btn-open-shift-signup"
          :aria-label="signUpLabel"
          class="h-11 shrink-0 rounded-lg border-primary bg-card px-4 font-bold text-primary hover:bg-primary/10 hover:text-primary @4xl:h-10 dark:border-primary/60 dark:bg-card dark:hover:bg-primary/10"
          @click="emit('select', shift.shift_id)"
        >
          {{ t('dashboard.home.open.signUp') }}
        </Button>
      </div>
    </Card>
  </li>
</template>
