<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import { MousePointerClick } from '@lucide/vue'
import { useI18n } from 'vue-i18n'

import { useFormatters } from '@/composables/useFormatters'

import HintTooltip from '@/components/utils/HintTooltip.vue'

const props = defineProps<{
  days: Date[]
  hours: number[]
  modelValue: Set<string>
}>()

const emit = defineEmits<{
  'update:modelValue': [value: Set<string>]
}>()

const { t, locale } = useI18n()
const { formatDateLabel } = useFormatters()

const cellKey = (d: number, h: number) => `${d}-${h}`

interface PaintState {
  adding: boolean
  pointerId: number
  // Accumulator mirrors the v-model set during the gesture, so consecutive
  // pointermove events don't overwrite each other when they fire faster than
  // Vue's reactivity flush (synchronous bursts).
  buffer: Set<string>
}
const paintRef = ref<PaintState | null>(null)
const lastTouchedRef = ref<string | null>(null)

// Mirror of the latest set we've handled locally — kept in sync with v-model
// but updated synchronously on emit so that consecutive paint strokes don't
// read stale prop values before Vue's reactivity has flushed.
let liveSet = new Set(props.modelValue)
watch(
  () => props.modelValue,
  (v) => {
    liveSet = new Set(v)
  },
)

const dayCount = (di: number): number =>
  props.hours.filter((h) => props.modelValue.has(cellKey(di, h))).length

function commitToggle(di: number, h: number, adding: boolean) {
  const k = cellKey(di, h)
  const target = paintRef.value?.buffer ?? new Set(liveSet)
  if (adding) target.add(k)
  else target.delete(k)
  liveSet = new Set(target)
  emit('update:modelValue', new Set(target))
}

function findCellAt(x: number, y: number): { di: number; h: number } | null {
  const el = document.elementFromPoint(x, y) as HTMLElement | null
  const cell = el?.closest('[data-cell]') as HTMLElement | null
  if (!cell) return null
  const di = Number(cell.dataset.day)
  const h = Number(cell.dataset.hour)
  if (Number.isNaN(di) || Number.isNaN(h)) return null
  return { di, h }
}

function onPointerDown(e: PointerEvent) {
  const cell = (e.target as HTMLElement | null)?.closest('[data-cell]') as HTMLElement | null
  if (!cell) return
  const di = Number(cell.dataset.day)
  const h = Number(cell.dataset.hour)
  if (Number.isNaN(di) || Number.isNaN(h)) return

  e.preventDefault()
  try {
    ;(e.currentTarget as HTMLElement).setPointerCapture?.(e.pointerId)
  } catch {
    // No active pointer (e.g. synthesized events) — capture isn't required.
  }

  const k = cellKey(di, h)
  const adding = !liveSet.has(k)
  paintRef.value = { adding, pointerId: e.pointerId, buffer: new Set(liveSet) }
  lastTouchedRef.value = k
  commitToggle(di, h, adding)
}

function onPointerMove(e: PointerEvent) {
  if (!paintRef.value || paintRef.value.pointerId !== e.pointerId) return
  const c = findCellAt(e.clientX, e.clientY)
  if (!c) return
  const k = cellKey(c.di, c.h)
  if (lastTouchedRef.value === k) return
  lastTouchedRef.value = k
  commitToggle(c.di, c.h, paintRef.value.adding)
}

function onPointerUp(e: PointerEvent) {
  if (!paintRef.value || paintRef.value.pointerId !== e.pointerId) return
  try {
    ;(e.currentTarget as HTMLElement).releasePointerCapture?.(e.pointerId)
  } catch {
    // Pointer wasn't captured — nothing to release.
  }
  paintRef.value = null
  lastTouchedRef.value = null
}

function toggleDay(di: number) {
  const next = new Set(liveSet)
  const allOn = props.hours.every((h) => next.has(cellKey(di, h)))
  for (const h of props.hours) {
    if (allOn) next.delete(cellKey(di, h))
    else next.add(cellKey(di, h))
  }
  liveSet = new Set(next)
  emit('update:modelValue', next)
}

const dayHeaderShort = computed(
  () => (d: Date) => d.toLocaleDateString(locale.value, { weekday: 'short' }),
)

const dayHeaderNarrow = computed(
  () => (d: Date) => d.toLocaleDateString(locale.value, { weekday: 'narrow' }),
)

function dayLabel(d: Date) {
  return formatDateLabel(d.toISOString().slice(0, 10), {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
  })
}
</script>

<template>
  <div>
    <div class="mb-2 hidden items-center justify-between gap-2 sm:flex">
      <div class="text-muted-foreground inline-flex items-center gap-1.5 text-xs">
        <MousePointerClick class="size-3.5" />
        {{ t('duties.availability.paintHint') }}
      </div>
    </div>

    <div class="flex select-none gap-0">
      <!-- Hour gutter (desktop) -->
      <div class="hidden w-11 pt-[36px] sm:block">
        <div
          v-for="(h, i) in hours"
          :key="h"
          class="text-muted-foreground flex h-[26px] items-start justify-end pr-2 text-[10px] font-medium"
          :class="i > 0 && h % 3 === 0 ? 'border-border/50 border-t border-dashed' : ''"
        >
          <span v-if="h % 2 === 0">{{ String(h).padStart(2, '0') }}:00</span>
        </div>
      </div>

      <!-- Hour gutter (mobile, narrower) -->
      <div class="w-8 pt-11 sm:hidden">
        <div
          v-for="h in hours"
          :key="h"
          class="text-muted-foreground flex h-[30px] items-start justify-end pr-1.5 text-[10px] font-medium"
        >
          <span v-if="h % 2 === 0">{{ String(h).padStart(2, '0') }}</span>
        </div>
      </div>

      <!-- Day columns: scroll on mobile, fluid on desktop. Pointer events live
           on this scroll container so painting works for both mouse and touch. -->
      <div
        class="flex flex-1 gap-1 overflow-x-auto sm:gap-1.5"
        @pointerdown="onPointerDown"
        @pointermove="onPointerMove"
        @pointerup="onPointerUp"
        @pointercancel="onPointerUp"
      >
        <div
          v-for="(d, di) in days"
          :key="di"
          class="flex shrink-0 flex-col sm:shrink"
          :class="['min-w-11 sm:min-w-0 sm:flex-1']"
        >
          <HintTooltip :label="dayLabel(d)">
            <button
              type="button"
              :aria-label="dayLabel(d)"
              class="mb-1 flex h-10 flex-col items-center justify-center gap-0.5 rounded-md border px-1 text-center transition-colors sm:h-8"
              :class="
                dayCount(di) === hours.length
                  ? 'border-primary bg-primary text-primary-foreground'
                  : dayCount(di) > 0
                    ? 'border-primary bg-primary/10 text-primary'
                    : 'border-border bg-background text-muted-foreground hover:border-primary/40'
              "
              @click="toggleDay(di)"
            >
              <span
                class="text-[10px] font-semibold uppercase tracking-wider opacity-90 sm:text-[9px]"
              >
                <span class="hidden sm:inline">{{ dayHeaderShort(d) }}</span>
                <span class="sm:hidden">{{ dayHeaderNarrow(d) }}</span>
              </span>
              <span class="text-[13px] font-semibold leading-none sm:text-[12px]">{{
                d.getDate()
              }}</span>
            </button>
          </HintTooltip>

          <div
            v-for="h in hours"
            :key="h"
            data-cell
            :data-day="di"
            :data-hour="h"
            style="touch-action: none"
            class="mb-0.5 h-7 cursor-pointer rounded-sm border transition-colors sm:h-6"
            :class="
              modelValue.has(cellKey(di, h))
                ? 'border-primary bg-primary'
                : 'border-border/60 bg-background hover:border-primary/40'
            "
          />

          <div
            class="mt-1 text-center text-[11px] font-semibold sm:text-[10px]"
            :class="dayCount(di) > 0 ? 'text-primary' : 'text-muted-foreground'"
          >
            {{ dayCount(di) > 0 ? `${dayCount(di)}h` : '–' }}
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
