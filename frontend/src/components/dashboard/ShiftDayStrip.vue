<script setup lang="ts">
/**
 * The next shift drawn on a bar of its day, with a marker for now when the
 * shift is today. Desktop only, inside `NextShiftHero`.
 *
 * It is a picture of facts the card already states in words (the times above
 * it, and the countdown chip), so the whole strip is `aria-hidden`. The
 * window and positions come from `dayStrip()` in `@/lib/dashboard`, which
 * also clamps an overnight shift at midnight.
 *
 * The hour labels follow the clock the times above use. On a 12-hour clock
 * each is a formatted hour ("8 AM", "4 PM") and the end of the day is "12 AM",
 * since there is no 24 o'clock there; on a 24-hour clock the ends are spelled
 * out ("8 Uhr", "24 Uhr") and the hours between are bare numbers.
 */
import { computed } from 'vue'

import { useI18n } from 'vue-i18n'

import { useFormatters } from '@/composables/useFormatters'

import { type DayStrip, twelveHourFormatter } from '@/lib/dashboard'

defineProps<{ strip: DayStrip }>()

const { t, locale } = useI18n()
const { hour12 } = useFormatters()

const twelveHour = computed(() => twelveHourFormatter(locale.value, hour12.value))

function tickLabel(tick: DayStrip['ticks'][number]): string {
  const fmt = twelveHour.value
  if (fmt) return fmt.format(new Date(2000, 0, 1, tick.hour % 24))
  return tick.edge ? t('dashboard.home.next.strip.hour', { hour: tick.hour }) : String(tick.hour)
}

/** Keep the "now" label inside the bar near either end. */
function nowLabelShift(at: number): string {
  if (at < 6) return ''
  if (at > 94) return '-translate-x-full'
  return '-translate-x-1/2'
}
</script>

<template>
  <div aria-hidden="true" data-testid="next-shift-day-strip" class="mt-[30px] pt-1">
    <div class="relative h-[26px] rounded-lg bg-primary-foreground/15">
      <div
        class="absolute inset-y-0 rounded-lg bg-hero-chip"
        :style="{
          left: `${strip.block.left}%`,
          width: `${strip.block.width}%`,
          minWidth: '4px',
        }"
      />
      <template v-if="strip.nowAt !== null">
        <div
          data-testid="next-shift-day-strip-now"
          class="absolute -inset-y-1.5 w-0.5 -translate-x-1/2 rounded-full bg-primary-foreground"
          :style="{ left: `${strip.nowAt}%` }"
        />
        <span
          class="absolute -top-6 text-[11px] font-bold whitespace-nowrap"
          :class="nowLabelShift(strip.nowAt)"
          :style="{ left: `${strip.nowAt}%` }"
        >
          {{ t('dashboard.home.next.strip.now') }}
        </span>
      </template>
    </div>
    <div class="relative mt-1.5 h-4 text-xs text-primary-foreground/85 tabular-nums">
      <span
        v-for="tick in strip.ticks"
        :key="tick.hour"
        data-testid="next-shift-day-strip-tick"
        class="absolute whitespace-nowrap"
        :class="
          tick.edge === 'start'
            ? ''
            : tick.edge === 'end'
              ? '-translate-x-full'
              : '-translate-x-1/2'
        "
        :style="{ left: `${tick.at}%` }"
      >
        {{ tickLabel(tick) }}
      </span>
    </div>
  </div>
</template>
