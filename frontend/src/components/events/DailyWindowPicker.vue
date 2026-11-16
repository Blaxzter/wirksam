<script setup lang="ts">
import { computed, ref } from 'vue'

import { useI18n } from 'vue-i18n'

import ScrollRow from '@/components/utils/ScrollRow.vue'

const props = defineProps<{
  days: Date[]
  from: number
  to: number
  excludedDays: Set<number>
}>()

const emit = defineEmits<{
  'update:from': [value: number]
  'update:to': [value: number]
  'update:excludedDays': [value: Set<number>]
}>()

const { t, locale } = useI18n()

const trackEl = ref<HTMLDivElement | null>(null)

const HMIN = 0
const HMAX = 24

const fromPct = computed(() => (props.from / HMAX) * 100)
const toPct = computed(() => (props.to / HMAX) * 100)
const enabledDayCount = computed(() => props.days.length - props.excludedDays.size)
const totalHours = computed(() => Math.max(0, props.to - props.from) * enabledDayCount.value)

function toggleDay(di: number) {
  const next = new Set(props.excludedDays)
  if (next.has(di)) next.delete(di)
  else next.add(di)
  emit('update:excludedDays', next)
}

const fmt = (h: number) => `${String(h).padStart(2, '0')}:00`

function handleDown(edge: 'from' | 'to', e: PointerEvent) {
  e.preventDefault()
  ;(e.target as Element).setPointerCapture?.(e.pointerId)

  const move = (ev: PointerEvent) => {
    const track = trackEl.value
    if (!track) return
    const r = track.getBoundingClientRect()
    const pct = Math.max(0, Math.min(1, (ev.clientX - r.left) / r.width))
    const h = Math.round(HMIN + pct * (HMAX - HMIN))
    if (edge === 'from') {
      emit('update:from', Math.min(h, props.to - 1))
    } else {
      emit('update:to', Math.max(h, props.from + 1))
    }
  }
  const up = () => {
    window.removeEventListener('pointermove', move)
    window.removeEventListener('pointerup', up)
  }
  window.addEventListener('pointermove', move)
  window.addEventListener('pointerup', up)
}

const ticks = [0, 3, 6, 9, 12, 15, 18, 21, 24]
</script>

<template>
  <div>
    <div class="mb-3 flex items-baseline justify-between">
      <div class="text-muted-foreground text-xs">
        <span>{{ t('duties.availability.fields.startTime') }}</span>
        <strong class="text-foreground mx-1.5 text-[15px] font-semibold">{{ fmt(from) }}</strong>
        <span>—</span>
        <strong class="text-foreground mx-1.5 text-[15px] font-semibold">{{ fmt(to) }}</strong>
      </div>
      <div class="text-muted-foreground text-[11px]">
        {{ t('duties.availability.dailyTotalHours', { count: totalHours }) }}
      </div>
    </div>

    <div
      ref="trackEl"
      class="bg-background border-border relative h-11 select-none rounded-md border"
    >
      <div
        v-for="h in ticks"
        :key="h"
        class="bg-border/70 absolute top-0 bottom-0 w-px"
        :style="{ left: `${(h / 24) * 100}%` }"
      >
        <div
          class="text-muted-foreground absolute -top-4 -translate-x-1/2 text-[9px] font-semibold"
        >
          {{ h }}
        </div>
      </div>

      <div
        class="bg-primary/90 absolute top-1 bottom-1 rounded"
        :style="{ left: `${fromPct}%`, width: `${toPct - fromPct}%` }"
      />

      <div
        class="absolute top-0 bottom-0 flex w-5 cursor-ew-resize items-center justify-center"
        :style="{ left: `${fromPct}%`, transform: 'translateX(-50%)' }"
        @pointerdown="(e) => handleDown('from', e)"
      >
        <div class="bg-foreground h-7 w-1 rounded-sm shadow-sm" />
      </div>
      <div
        class="absolute top-0 bottom-0 flex w-5 cursor-ew-resize items-center justify-center"
        :style="{ left: `${toPct}%`, transform: 'translateX(-50%)' }"
        @pointerdown="(e) => handleDown('to', e)"
      >
        <div class="bg-foreground h-7 w-1 rounded-sm shadow-sm" />
      </div>
    </div>

    <!-- Day chips: click to toggle availability for that day. Horizontally
         scrollable on small screens; flex-grow on wide screens so they fill. -->
    <ScrollRow class="mt-3" content-class="gap-2 py-1">
      <button
        v-for="(d, i) in days"
        :key="i"
        type="button"
        :data-testid="`daily-day-${i}`"
        :aria-pressed="!excludedDays.has(i)"
        class="flex min-w-[88px] shrink-0 grow basis-0 cursor-pointer flex-col items-center gap-0.5 rounded-lg border px-2 py-2.5 text-center transition-colors"
        :class="
          excludedDays.has(i)
            ? 'border-border bg-background text-muted-foreground/70 hover:border-primary/40'
            : 'border-primary bg-primary/10 text-primary hover:bg-primary/20'
        "
        @click="toggleDay(i)"
      >
        <span class="text-[10px] font-semibold uppercase tracking-wider">
          {{ d.toLocaleDateString(locale, { weekday: 'short' }) }}
        </span>
        <span class="text-[15px] font-semibold leading-none">{{ d.getDate() }}</span>
        <span class="text-[10px] font-medium opacity-75">
          {{ excludedDays.has(i) ? '—' : `${fmt(from)}–${fmt(to)}` }}
        </span>
      </button>
    </ScrollRow>
  </div>
</template>
