<script setup lang="ts">
/**
 * The next shift drawn on a bar of its day, with a marker for now when the
 * shift is today. Desktop only, inside `NextShiftHero`.
 *
 * It is a picture of facts the card already states in words (the times above
 * it, and the countdown chip), so the whole strip is `aria-hidden`. The
 * window and positions come from `dayStrip()` in `@/lib/dashboard`, which
 * also clamps an overnight shift at midnight.
 */
import { useI18n } from 'vue-i18n'

import type { DayStrip } from '@/lib/dashboard'

defineProps<{ strip: DayStrip }>()

const { t } = useI18n()

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
        {{ tick.edge ? t('dashboard.home.next.strip.hour', { hour: tick.hour }) : tick.hour }}
      </span>
    </div>
  </div>
</template>
